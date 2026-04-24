"""The three custom tools the Skill-Builder agent can call.

1. search_skills(query)       — find existing skills matching a topic
2. read_skill(name)           — load an existing skill's full markdown
3. create_skill(name, content)— write a new skill to disk

All tools return JSON strings so they drop straight into the conversation
history as tool-result messages.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths — default to ~/.claude/skills, overridable via SKILLS_DIR env.
# Plugin skills live under ~/.claude/plugins/marketplaces/*/<plugin>/skills/.
# ---------------------------------------------------------------------------


def _user_skills_dir() -> Path:
    override = os.getenv("SKILLS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "skills"


def _plugin_skills_roots() -> list[Path]:
    """All marketplace plugin roots we should scan for skills."""
    plugins_root = Path.home() / ".claude" / "plugins" / "marketplaces"
    if not plugins_root.exists():
        return []
    return [plugins_root]


# ---------------------------------------------------------------------------
# Frontmatter parsing — pull `name:` and `description:` from a SKILL.md head.
# Tolerant: handles single-line `description:` and `description: |` block form.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    path: Path

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "path": str(self.path),
        }


def _parse_frontmatter(markdown: str) -> dict[str, str]:
    """Return a flat dict from YAML-ish frontmatter at the top of a skill file.

    Not a real YAML parser — just covers the two forms observed in practice:
        name: foo
        description: one liner
    and:
        description: |
          multi
          line
    """
    if not markdown.startswith("---"):
        return {}

    # End of frontmatter: either a `---` on its own line followed by more
    # content, or `---` at the very end of the string. Accept both.
    end_match = re.search(r"\n---\s*(?:\n|\Z)", markdown)
    if not end_match:
        return {}

    body = markdown[3 : end_match.start()].strip()
    out: dict[str, str] = {}
    current_key: str | None = None
    block_lines: list[str] = []

    for raw_line in body.split("\n"):
        line = raw_line.rstrip()
        # Block scalar open: `key: |`
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*\|\s*$", line)
        if m:
            if current_key is not None:
                out[current_key] = "\n".join(block_lines).strip()
                block_lines = []
            current_key = m.group(1)
            continue
        # Inline scalar: `key: value`
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if m and not line.startswith(" "):
            if current_key is not None:
                out[current_key] = "\n".join(block_lines).strip()
                block_lines = []
                current_key = None
            key, value = m.group(1), m.group(2).strip()
            if value:
                out[key] = value
            else:
                current_key = key
            continue
        # Continuation of a block scalar
        if current_key is not None:
            block_lines.append(raw_line.lstrip(" "))

    if current_key is not None:
        out[current_key] = "\n".join(block_lines).strip()

    return out


def _iter_skill_files() -> list[Path]:
    """Every SKILL.md we know about — user-scope plus plugin-scope."""
    found: list[Path] = []
    user_dir = _user_skills_dir()
    if user_dir.exists():
        # Modern dir form: <skills_dir>/<name>/SKILL.md
        found.extend(user_dir.glob("*/SKILL.md"))
        # Legacy flat form: <skills_dir>/<name>.md
        for md in user_dir.glob("*.md"):
            if md.name not in {"README.md", "LICENSE.md"}:
                found.append(md)
    for root in _plugin_skills_roots():
        found.extend(root.glob("*/*/SKILL.md"))
        found.extend(root.glob("*/*/skills/*/SKILL.md"))
    return found


def _load_skill_info(path: Path) -> SkillInfo | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    front = _parse_frontmatter(text)
    name = front.get("name") or path.parent.name or path.stem
    description = front.get("description", "").strip().replace("\n", " ")
    return SkillInfo(name=name, description=description, path=path)


# ---------------------------------------------------------------------------
# Tool 1: search_skills
# ---------------------------------------------------------------------------


def search_skills(query: str, limit: int = 8) -> str:
    """Find existing skills whose name or description matches the query.

    Args:
        query: free-form topic or keyword.
        limit: max results to return.

    Returns:
        JSON string with {"matches": [{name, description, path}]} or {"error"}.
    """
    q = (query or "").strip().lower()
    if not q:
        return json.dumps({"error": "query is empty"})

    tokens = [t for t in re.split(r"\s+", q) if t]
    scored: list[tuple[int, SkillInfo]] = []

    for path in _iter_skill_files():
        info = _load_skill_info(path)
        if info is None:
            continue
        haystack = f"{info.name} {info.description}".lower()
        score = sum(haystack.count(tok) for tok in tokens)
        # Boost: exact name match wins
        if info.name.lower() == q:
            score += 100
        if score > 0:
            scored.append((score, info))

    scored.sort(key=lambda x: -x[0])
    matches = [info.to_dict() for _, info in scored[:limit]]

    return json.dumps(
        {
            "query": query,
            "match_count": len(matches),
            "matches": matches,
            "note": (
                "No matches — safe to create a new skill."
                if not matches
                else f"Review these {len(matches)} existing skill(s) before creating. "
                "Avoid duplicating their scope."
            ),
        }
    )


# ---------------------------------------------------------------------------
# Tool 2: read_skill
# ---------------------------------------------------------------------------


def _find_skill_path(name: str) -> Path | None:
    """Locate an existing skill by name across user + plugin scopes."""
    name = name.strip()
    candidates: list[Path] = []
    user_dir = _user_skills_dir()
    if user_dir.exists():
        candidates.extend(
            [
                user_dir / name / "SKILL.md",
                user_dir / f"{name}.md",
            ]
        )
    for info_path in _iter_skill_files():
        info = _load_skill_info(info_path)
        if info and info.name == name:
            candidates.append(info_path)
    for cand in candidates:
        if cand.exists():
            return cand
    return None


def read_skill(name: str, max_chars: int = 6000) -> str:
    """Read the full markdown of an existing skill.

    Truncates to `max_chars` to keep the LLM context under control.
    """
    path = _find_skill_path(name)
    if path is None:
        return json.dumps(
            {
                "error": f"skill '{name}' not found",
                "hint": "Run search_skills first to discover valid names.",
            }
        )
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return json.dumps({"error": f"read failed: {exc}"})

    truncated = len(text) > max_chars
    body = text[:max_chars]
    return json.dumps(
        {
            "name": name,
            "path": str(path),
            "truncated": truncated,
            "content": body,
        }
    )


# ---------------------------------------------------------------------------
# Tool 3: create_skill
# ---------------------------------------------------------------------------


_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


def create_skill(name: str, content: str, overwrite: bool = False) -> str:
    """Write a new skill to ~/.claude/skills/<name>/SKILL.md.

    The file MUST start with YAML frontmatter containing at least
    `name:` and `description:`. Refuses to overwrite by default.
    """
    name = (name or "").strip()
    if not _SLUG_RE.match(name):
        return json.dumps(
            {
                "error": (
                    f"invalid skill name '{name}'. Must be kebab-case, "
                    "2–64 chars, lowercase, starting with a letter."
                )
            }
        )

    if not content.startswith("---"):
        return json.dumps(
            {
                "error": "content must start with YAML frontmatter (---).",
                "hint": "Include at least `name:` and `description:` fields.",
            }
        )

    front = _parse_frontmatter(content)
    missing = [k for k in ("name", "description") if not front.get(k)]
    if missing:
        return json.dumps(
            {"error": f"frontmatter missing required keys: {missing}"}
        )

    if front.get("name") != name:
        return json.dumps(
            {
                "error": (
                    f"frontmatter name '{front.get('name')}' does not match "
                    f"create_skill name '{name}'."
                )
            }
        )

    skills_dir = _user_skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)
    skill_dir = skills_dir / name
    skill_path = skill_dir / "SKILL.md"

    if skill_path.exists() and not overwrite:
        return json.dumps(
            {
                "error": f"skill '{name}' already exists at {skill_path}",
                "hint": "Pass overwrite=true to replace, or pick a different name.",
            }
        )

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(content, encoding="utf-8")

    return json.dumps(
        {
            "created": True,
            "name": name,
            "path": str(skill_path),
            "bytes": len(content.encode("utf-8")),
            "hint": (
                "Open a fresh Claude Code session to invoke. "
                "The description you wrote is what Claude will match against."
            ),
        }
    )


# ---------------------------------------------------------------------------
# Registry — dispatched by name from the agent loop.
# ---------------------------------------------------------------------------

TOOLS = {
    "search_skills": search_skills,
    "read_skill": read_skill,
    "create_skill": create_skill,
}
