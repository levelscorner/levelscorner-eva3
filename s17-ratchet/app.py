"""Ratchet — the service.

    GET  /                 the single page client
    POST /run              {"bug": "...", "target": "relative/path.py"} -> {"runId"}
    GET  /stream/{runId}   text/event-stream
    GET  /health           {"ok": true}

The SSE contract is fixed and this file is the only place it is written:

    event: phase   data: {"phase":"author_test"|"red"|"fix"|"green"|"failed","note":"..."}
    event: node    data: {"id":"...","label":"...","state":"running"|"ok"|"fail","detail":"..."}
    event: cmd     data: {"cmd":"...","exit":0,"output":"..."}
    event: diff    data: {"path":"...","patch":"..."}
    event: proof   data: {"testPath":"...","sha256Before":"...","sha256After":"...","unchanged":true}
    event: done    data: {"ok":true,"summary":"..."}

A stream replays from the beginning whichever moment a client connects, so the
receipt is never lost to a refreshed tab, and a run that fails is streamed with
exactly the same machinery as one that succeeds. There is no path through this
file that reports a failure as a success.
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

# Importing the package runs ratchet/__init__.py, which puts S17CODE_ROOT on
# sys.path before ratchet.runner reaches for s17code.
from ratchet.runner import Config, Engine, RatchetRun, new_run_id, target_problems

HERE = Path(__file__).resolve().parent
KEEPALIVE_SECONDS = 15.0


class Stream:
    """One run's event tape: append-only, replayable, with a `done` terminator."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.finished = False
        self._waiters: list[asyncio.Future] = []

    async def emit(self, event: str, data: dict) -> None:
        self.events.append((event, data))
        if event == "done":
            self.finished = True
        for waiter in self._waiters:
            if not waiter.done():
                waiter.set_result(None)
        self._waiters.clear()

    async def wait(self) -> None:
        waiter = asyncio.get_running_loop().create_future()
        self._waiters.append(waiter)
        await waiter


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = Config.from_env()
    app.state.config = config
    app.state.engine = Engine.open(config)
    app.state.streams = {}
    # One workspace, one git checkout, one set of files: two Ratchet runs at once
    # would interleave their edits and neither receipt would mean anything. A
    # second run is refused rather than silently corrupted. This is a plain flag
    # rather than a lock because it is claimed synchronously inside the POST
    # handler: an asyncio.Lock is only held once the background task starts, and
    # a second POST arriving in that gap would slip past a `locked()` check.
    app.state.active_run = None
    app.state.tasks = {}
    try:
        yield
    finally:
        for task in app.state.tasks.values():
            task.cancel()
        await app.state.engine.close()


app = FastAPI(title="Ratchet", version="1.0.0", lifespan=lifespan)


class RunRequest(BaseModel):
    bug: str = Field(min_length=1, max_length=20_000)
    target: str = Field(min_length=1, max_length=500)


@app.get("/health")
async def health(request: Request) -> dict:
    config: Config = request.app.state.config
    engine: Engine = request.app.state.engine
    try:
        await engine.gateway.health()
        gateway_ok = True
    except Exception:
        gateway_ok = False
    return {
        "ok": True,
        "workspace": str(config.workspace),
        "workspaceIsGit": engine.workspace.is_git(),
        "gatewayReachable": gateway_ok,
        "gatewayBaseUrl": engine.gateway.base_url,
        "maxAttempts": config.max_attempts,
        "busy": request.app.state.active_run is not None,
    }


@app.post("/run")
async def start_run(body: RunRequest, request: Request) -> dict:
    engine: Engine = request.app.state.engine
    problem = target_problems(engine.workspace, body.target.strip())
    if problem:
        raise HTTPException(422, problem)
    if request.app.state.active_run is not None:
        raise HTTPException(409, "a run is already in flight; Ratchet takes one bug at a time")

    run_id = new_run_id()
    request.app.state.active_run = run_id
    stream = Stream()
    request.app.state.streams[run_id] = stream

    run = RatchetRun(run_id=run_id, bug=body.bug, target=body.target.strip(),
                     engine=engine, config=request.app.state.config, emit=stream.emit)

    async def execute() -> None:
        try:
            await run.execute()
        except asyncio.CancelledError:
            await stream.emit("done", {"ok": False, "summary": "the run was cancelled"})
            raise
        except Exception as error:
            # The orchestrator itself broke. Say so; never let the stream end
            # without a terminal `done`, and never let it end optimistically.
            await stream.emit("phase", {"phase": "failed",
                                        "note": f"{type(error).__name__}: {error}"})
            await stream.emit("done", {"ok": False,
                                       "summary": f"ratchet failed: {type(error).__name__}: {error}"})
        finally:
            request.app.state.tasks.pop(run_id, None)
            request.app.state.active_run = None

    request.app.state.tasks[run_id] = asyncio.create_task(execute())
    return {"runId": run_id}


@app.get("/stream/{run_id}")
async def stream_run(run_id: str, request: Request) -> StreamingResponse:
    stream: Stream | None = request.app.state.streams.get(run_id)
    if stream is None:
        raise HTTPException(404, "unknown run")

    async def generate():
        cursor = 0
        while True:
            while cursor < len(stream.events):
                event, data = stream.events[cursor]
                cursor += 1
                yield sse(event, data)
            if stream.finished:
                return
            if await request.is_disconnected():
                return
            try:
                await asyncio.wait_for(stream.wait(), timeout=KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": keepalive\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


# --------------------------------------------------------------------------
# the client
# --------------------------------------------------------------------------

FALLBACK_CLIENT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ratchet</title>
<style>
  :root{--bg:#0d0f12;--panel:#14181d;--line:#242a31;--ink:#e6e9ec;--dim:#8b959f;
        --ok:#4ade80;--fail:#f87171;--run:#fbbf24;color-scheme:dark}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:14px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace}
  header{padding:20px 24px;border-bottom:1px solid var(--line)}
  h1{margin:0;font-size:20px;letter-spacing:.02em}
  p.tag{margin:6px 0 0;color:var(--dim)}
  main{display:grid;grid-template-columns:340px 1fr;gap:0;min-height:calc(100vh - 84px)}
  form{padding:20px 24px;border-right:1px solid var(--line);display:flex;flex-direction:column;gap:12px}
  label{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
  input,textarea{background:var(--panel);border:1px solid var(--line);color:var(--ink);
                 padding:9px 11px;border-radius:6px;font:inherit;width:100%}
  textarea{min-height:180px;resize:vertical}
  button{background:var(--ink);color:#0d0f12;border:0;padding:10px;border-radius:6px;
         font:inherit;font-weight:600;cursor:pointer}
  button:disabled{opacity:.4;cursor:not-allowed}
  #feed{padding:20px 24px;overflow-x:auto}
  .phase{margin:18px 0 8px;padding:8px 12px;background:var(--panel);border-left:3px solid var(--run);
         border-radius:0 6px 6px 0}
  .phase b{text-transform:uppercase;letter-spacing:.1em;font-size:12px}
  .phase.green{border-color:var(--ok)} .phase.failed{border-color:var(--fail)}
  .node{padding:3px 0;color:var(--dim)}
  .node .s{display:inline-block;width:9ch;font-weight:600}
  .running .s{color:var(--run)} .ok .s{color:var(--ok)} .fail .s{color:var(--fail)}
  .node .lbl{color:var(--ink)}
  pre{background:var(--panel);border:1px solid var(--line);border-radius:6px;
      padding:12px;overflow-x:auto;white-space:pre;margin:8px 0}
  .proof{border:1px solid var(--line);border-radius:6px;padding:14px;margin:14px 0;background:var(--panel)}
  .proof.same{border-color:var(--ok)} .proof.moved{border-color:var(--fail)}
  .proof code{word-break:break-all}
  .done{margin:16px 0;padding:12px;border-radius:6px;font-weight:600}
  .done.ok{background:rgba(74,222,128,.12);color:var(--ok)}
  .done.no{background:rgba(248,113,113,.12);color:var(--fail)}
</style></head><body>
<header><h1>Ratchet</h1>
<p class="tag">The agent cannot mark its own homework — and you can verify that rather than trust it.</p></header>
<main>
<form id="f">
  <div><label for="target">target file</label><input id="target" value="" placeholder="pkg/module.py" required></div>
  <div><label for="bug">bug report</label><textarea id="bug" placeholder="Describe what goes wrong." required></textarea></div>
  <button id="go" type="submit">Start the run</button>
</form>
<div id="feed"></div>
</main>
<script>
const feed = document.getElementById('f') && document.getElementById('feed');
const add = el => { feed.appendChild(el); el.scrollIntoView({block:'end'}); };
const node = (tag, cls, text) => { const e = document.createElement(tag);
  if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };

document.getElementById('f').addEventListener('submit', async ev => {
  ev.preventDefault();
  const go = document.getElementById('go');
  go.disabled = true; feed.textContent = '';
  let res;
  try {
    res = await fetch('/run', {method:'POST', headers:{'content-type':'application/json'},
      body: JSON.stringify({bug: document.getElementById('bug').value,
                            target: document.getElementById('target').value})});
  } catch (e) { add(node('div','done no','network error: ' + e)); go.disabled = false; return; }
  if (!res.ok) { add(node('div','done no', 'rejected: ' + (await res.text()))); go.disabled = false; return; }
  const {runId} = await res.json();
  const es = new EventSource('/stream/' + runId);

  es.addEventListener('phase', e => { const d = JSON.parse(e.data);
    const box = node('div', 'phase ' + d.phase);
    box.appendChild(node('b', '', d.phase.replace('_',' ')));
    box.appendChild(node('div', '', d.note));
    add(box); });

  es.addEventListener('node', e => { const d = JSON.parse(e.data);
    const line = node('div', 'node ' + d.state);
    line.appendChild(node('span','s', d.state));
    line.appendChild(node('span','lbl', d.label + ' '));
    line.appendChild(node('span','', d.detail || ''));
    add(line); });

  es.addEventListener('cmd', e => { const d = JSON.parse(e.data);
    add(node('pre','', '$ ' + d.cmd + '\\n[exit ' + d.exit + ']\\n' + (d.output || ''))); });

  es.addEventListener('diff', e => { const d = JSON.parse(e.data);
    add(node('pre','', d.patch)); });

  es.addEventListener('proof', e => { const d = JSON.parse(e.data);
    const box = node('div', 'proof ' + (d.unchanged ? 'same' : 'moved'));
    box.appendChild(node('b','', d.unchanged
      ? 'RECEIPT: the judge did not move' : 'RECEIPT: the judge MOVED — this run is void'));
    box.appendChild(node('div','', d.testPath));
    box.appendChild(node('div','', 'before  ' + d.sha256Before));
    box.appendChild(node('div','', 'after   ' + d.sha256After));
    add(box); });

  es.addEventListener('done', e => { const d = JSON.parse(e.data);
    add(node('div', 'done ' + (d.ok ? 'ok' : 'no'), (d.ok ? 'PASS  ' : 'FAIL  ') + d.summary));
    es.close(); go.disabled = false; });

  es.onerror = () => { es.close(); go.disabled = false; };
});
</script></body></html>
"""


@app.get("/", response_class=HTMLResponse)
async def client() -> HTMLResponse:
    """Serve a real client if one has been built, otherwise the reference one.

    ``RATCHET_CLIENT``, then ``client/index.html``, then ``static/index.html``,
    so a proper frontend drops in without touching this file. The fallback below
    is not a placeholder: it speaks the full contract, including the receipt.
    """
    configured = os.getenv("RATCHET_CLIENT", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates += [HERE / "client" / "index.html", HERE / "static" / "index.html"]
    for candidate in candidates:
        if candidate.is_file():
            return HTMLResponse(candidate.read_text(encoding="utf-8"))
    return HTMLResponse(FALLBACK_CLIENT)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("RATCHET_HOST", "127.0.0.1"),
                port=int(os.getenv("RATCHET_PORT", "8117")))
