"""Atlas: an agent that may only answer in interfaces.

Every turn goes model -> declarative surface -> injection wall -> render. The
model never writes markup, never names a component that does not exist, and
never emits an action the server did not register. What it produces is a JSON
description of an interface, checked before a pixel is drawn.

The gateway (glc_v3) owns the provider keys. This app holds none, and talks to
it over ordinary authenticated HTTP, exactly the S13/S14 seam.

    GLC_BASE_URL=http://127.0.0.1:8111 uv run python app.py
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

HERE = Path(__file__).parent
GLC = os.getenv("GLC_BASE_URL", "http://127.0.0.1:8111").rstrip("/")
PROVIDER = os.getenv("ATLAS_PROVIDER", "ollama")

# --------------------------------------------------------------------------
# 1. The catalog. A closed set: a type that does not exist cannot be named.
# --------------------------------------------------------------------------
CATALOG: dict[str, dict[str, str]] = {
    "Column":       {"children": "ref"},
    "Row":          {"children": "ref"},
    "Heading":      {"text": "text"},
    "Text":         {"text": "text"},
    "Notice":       {"text": "text", "tone": "enum:neutral,good,warn,bad"},
    "KeyValue":     {"pairs": "data"},
    "DataTable":    {"columns": "text", "rows": "data"},
    "BarChart":     {"title": "text", "data": "data"},
    "Sparkline":    {"data": "data", "tone": "enum:neutral,good,warn,bad"},
    "StatTile":     {"label": "text", "value": "text", "unit": "text",
                     "tone": "enum:neutral,good,warn,bad"},
    "Timeline":     {"title": "text", "events": "data"},
    "Checklist":    {"title": "text", "items": "data"},
    "EvidenceCard": {"claim": "text", "stance": "enum:stated,derived,inferred",
                     "sources": "sources"},
    "Choice":       {"label": "text", "options": "data", "onPick": "action"},
    "Button":       {"label": "text", "onPress": "action"},
}
ACTIONS = frozenset({"refine", "compare", "drill_down", "approve", "reject"})

# Same wall as S14Code: markup, script URLs, handler-shaped keys, bad schemes.
_MARKUP = re.compile(r"<[a-z!/][^>]*>|</[a-z]+>", re.I)
_JS_URL = re.compile(r"^\s*(javascript|data|vbscript):", re.I)
_HANDLER = re.compile(r"^on[a-z]+$", re.I)
_SAFE_URI = re.compile(r"^(https?|file|mailto):", re.I)


def _markup(v: Any) -> bool:
    return isinstance(v, str) and bool(_MARKUP.search(v))


def _deep_bad(v: Any) -> str | None:
    """Markup or a script URL anywhere inside bound data, at any depth."""
    if isinstance(v, str):
        if _MARKUP.search(v):
            return "value carries markup"
        if _JS_URL.match(v):
            return "value is a script or data URL"
        return None
    if isinstance(v, dict):
        for k, item in v.items():
            if _HANDLER.match(str(k)):
                return f"event-handler key {k!r} is never allowed"
            bad = _deep_bad(item)
            if bad:
                return bad
        return None
    if isinstance(v, list):
        for item in v:
            bad = _deep_bad(item)
            if bad:
                return bad
    return None


def validate(surface: dict) -> tuple[list[dict], list[dict]]:
    """Return (accepted, rejections). One poisoned node never blanks the screen."""
    accepted: list[dict] = []
    rejections: list[dict] = []

    for comp in surface.get("components", []):
        cid = comp.get("id", "<no id>")
        ctype = comp.get("type")
        if ctype not in CATALOG:
            rejections.append({"id": cid, "field": "type", "invariant": "catalog",
                               "reason": f"unknown component type {ctype!r}"})
            continue

        spec = CATALOG[ctype]
        bad = None
        for field, value in comp.items():
            if field in ("id", "type"):
                continue
            if field not in spec:
                bad = {"id": cid, "field": field, "invariant": "data-not-code",
                       "reason": ("event-handler property is never allowed"
                                  if _HANDLER.match(field) else
                                  f"unknown property {field!r} on {ctype}")}
                break

            kind = spec[field]
            if kind == "text" and _markup(value):
                bad = {"id": cid, "field": field, "invariant": "data-not-code",
                       "reason": "value carries markup"}
                break
            if kind.startswith("enum:") and value not in kind[5:].split(","):
                bad = {"id": cid, "field": field, "invariant": "data-not-code",
                       "reason": f"{value!r} is not one of {kind[5:]}"}
                break
            if kind == "action":
                name = value.get("action") if isinstance(value, dict) else value
                if name not in ACTIONS:
                    bad = {"id": cid, "field": field, "invariant": "event",
                           "reason": f"unregistered action {name!r}"}
                    break
            if kind == "sources":
                if not isinstance(value, list):
                    bad = {"id": cid, "field": field, "invariant": "data-not-code",
                           "reason": "sources must be a list"}
                    break
                for rec in value:
                    uri = rec.get("uri") if isinstance(rec, dict) else None
                    if not isinstance(uri, str) or not _SAFE_URI.match(uri):
                        bad = {"id": cid, "field": field, "invariant": "data-not-code",
                               "reason": f"source uri {uri!r} is not an allowed scheme"}
                        break
                if bad:
                    break
            reason = _deep_bad(value)
            if reason:
                bad = {"id": cid, "field": field, "invariant": "data-not-code", "reason": reason}
                break

        if bad:
            rejections.append(bad)
        else:
            accepted.append(comp)

    return accepted, rejections


# --------------------------------------------------------------------------
# 2. The instruction. The model is told the shape, not asked to behave.
# --------------------------------------------------------------------------
def system_prompt() -> str:
    lines = [f"- {name}({', '.join(props)})" for name, props in CATALOG.items()]
    return (
        "You compose user interfaces. You reply with ONE JSON object and nothing else.\n"
        "No prose, no markdown fence, no explanation outside the JSON.\n\n"
        "Shape:\n"
        '{"root":"<id>","components":[{"id":"<id>","type":"<Type>", ...props}]}\n\n'
        "Rules that are enforced by code, not by trust:\n"
        "1. Use ONLY these component types and properties. Anything else is discarded:\n"
        + "\n".join(lines) + "\n"
        "2. Never emit HTML, markdown tags, script or javascript: urls. Text is text.\n"
        f"3. Actions may only be one of: {', '.join(sorted(ACTIONS))}.\n"
        "4. 'children' is a list of component ids. The root is usually a Column.\n\n"
        "Choose the component that fits the DATA, not the one that is easiest:\n"
        "- numbers over categories -> BarChart      - a trend -> Sparkline\n"
        "- one headline figure -> StatTile          - rows and columns -> DataTable\n"
        "- ordered happenings -> Timeline           - steps to do -> Checklist\n"
        "- a sourced claim -> EvidenceCard (set stance honestly:\n"
        "    stated = a source says it, derived = computed from stated values,\n"
        "    inferred = you are connecting dots the source does not state)\n"
        "- a caveat or limitation -> Notice(tone=warn)\n"
        "- offer the user a next step -> Choice or Button with a registered action\n\n"
        "Always end with a Choice or Button so the conversation can continue.\n\n"
        "REQUIRED: use at least FOUR different component types, and at least one\n"
        "that is not Heading, Text, Notice or Choice. A wall of Text scores nothing.\n"
        "If the question involves any quantity, comparison, sequence or claim, there\n"
        "is a specific component for it above. Use it.\n\n"
        "Shape hints the renderer accepts:\n"
        '  DataTable  columns:"A,B,C"  rows:[{"A":1,"B":2,"C":3}]\n'
        '  BarChart   data:[{"label":"x","value":12}]\n'
        '  Sparkline  data:[1,4,3,7]\n'
        '  Timeline   events:[{"label":"first this"}]\n'
        '  Checklist  items:[{"label":"do this","done":false}]\n'
        '  KeyValue   pairs:[{"key":"Latency","value":"12ms"}]\n'
        '  EvidenceCard sources:[{"uri":"https://...","label":"name"}]\n'
        '  Choice     options:[{"label":"Ask this next"}]\n\n'
        "tone is ONLY one of: neutral, good, warn, bad. Not positive, not info,\n"
        "not success, not error. A tone outside that list is discarded by the wall\n"
        "and your component disappears, so use the four words exactly.\n"
        "stance is ONLY one of: stated, derived, inferred."
    )


class Turn(BaseModel):
    prompt: str
    history: list[str] = []


app = FastAPI(title="Atlas")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (HERE / "client.html").read_text(encoding="utf-8")


@app.get("/catalog")
async def catalog() -> dict:
    return {"components": CATALOG, "actions": sorted(ACTIONS)}


@app.get("/healthz")
async def healthz() -> dict:
    out: dict[str, Any] = {"ok": True, "gateway": GLC, "provider": PROVIDER}
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            out["glc"] = (await c.get(f"{GLC}/healthz")).json()
    except Exception as exc:  # the app is useless without the gateway; say so
        out["ok"] = False
        out["glc_error"] = str(exc)[:200]
    return out


@app.post("/turn")
async def turn(body: Turn) -> dict:
    """One turn: model -> surface -> wall -> render payload."""
    context = ""
    if body.history:
        context = ("Earlier in this conversation the user asked:\n"
                   + "\n".join(f"- {h}" for h in body.history[-4:])
                   + "\nBuild on that; do not repeat an identical interface.\n\n")

    payload = {
        "messages": [{"role": "user", "content": context + body.prompt}],
        "system": system_prompt(),
        # Reasoning models spend the budget thinking before they emit a token.
        # kimi-k3 burns ~2700 output tokens on a surface of this size, so a
        # 1400 cap returns stop_reason=max_tokens with an empty string: a
        # correct request that looks like a broken model. Budget for the think.
        "max_tokens": int(os.getenv("ATLAS_MAX_TOKENS", "6000")),
        "temperature": 0,
        "agent": "atlas_compose",
        "provider": PROVIDER,
    }
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(f"{GLC}/v1/chat", json=payload)
    if resp.status_code >= 400:
        return {"error": f"gateway {resp.status_code}", "detail": resp.text[:300]}

    body_json = resp.json()
    raw = body_json.get("text", "")
    surface = _extract_json(raw)
    if surface is None:
        # An honest failure is still an interface, never a raw dump.
        return {
            "surface": {"root": "e", "components": [
                {"id": "e", "type": "Notice", "tone": "warn",
                 "text": "The model did not return a valid interface for that. Try rephrasing."}]},
            "rejections": [], "provider": body_json.get("provider"),
            "model": body_json.get("model"), "parse_failed": True,
        }

    accepted, rejections = validate(surface)
    return {
        "surface": {"root": surface.get("root"), "components": accepted},
        "rejections": rejections,
        "provider": body_json.get("provider"),
        "model": body_json.get("model"),
        "component_types": sorted({c["type"] for c in accepted}),
    }


class RawSurface(BaseModel):
    surface: dict


@app.post("/turn_raw")
async def turn_raw(body: RawSurface) -> dict:
    """Push a surface straight at the wall, skipping the model.

    This is how the adversarial case is demonstrated honestly: the hostile
    surface is not something the model was talked into producing, it is handed
    to the identical validator the model's output goes through. The safe part
    still renders, which is the property worth showing.
    """
    accepted, rejections = validate(body.surface)
    return {"surface": {"root": body.surface.get("root"), "components": accepted},
            "rejections": rejections}


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model reply, fence or not."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text, flags=re.I | re.S)
    start = text.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    return obj if isinstance(obj, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("ATLAS_PORT", "8120")))
