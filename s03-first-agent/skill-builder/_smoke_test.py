"""End-to-end smoke test with a stubbed LLM. Gitignored; not for CI.

Run: python _smoke_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Stub the LLMClient BEFORE skill_builder imports it.
import llm as llm_mod  # noqa: E402

SKILL_CONTENT = """---
name: code-haiku-smoke
description: |
  Use when the user asks to generate a haiku about code, a function, a file,
  or a pull request. Triggers on phrasings like "write a haiku",
  "code haiku", or "5-7-5 about this".
---

# Code Haiku

## Use when
User asks for a haiku about source code, a file, a diff, or a software concept.

## How
1. Read the subject (file, function, or short prose).
2. Extract the dominant idea in one sentence.
3. Render exactly three lines: 5 syllables, then 7, then 5.
4. Keep words concrete. Avoid cliches (flowing rivers, quiet winds).
5. Return only the haiku.

## Red flags
- If asked for a limerick, sonnet, or other form, decline and redirect.
- Do not summarize the code.
- Do not explain the haiku.
"""


def _build_create_call(content: str) -> str:
    """Produce a valid JSON string for the create_skill tool call.

    We build it with json.dumps to guarantee all escapes are correct —
    avoids the shell-escape traps of hand-written fixtures.
    """
    import json as J

    return J.dumps(
        {
            "tool_name": "create_skill",
            "tool_arguments": {
                "name": "code-haiku-smoke",
                "content": content,
            },
        }
    )


CANNED = [
    '{"tool_name": "search_skills", "tool_arguments": {"query": "haiku code"}}',
    '{"tool_name": "read_skill", "tool_arguments": {"name": "python-patterns"}}',
    # Wrap the create call in markdown fences to exercise the fence-stripping
    # parser path — a common real-world Gemini output style.
    "```json\n" + _build_create_call(SKILL_CONTENT) + "\n```",
    '{"answer": "Created skill code-haiku-smoke at ~/.claude/skills/code-haiku-smoke/SKILL.md. Open a fresh Claude session and ask for a haiku to trigger it."}',
]

_idx = [0]


class _StubLLM:
    def __init__(self, *a, **kw):
        pass

    def generate(self, prompt: str) -> str:
        resp = CANNED[_idx[0]]
        _idx[0] += 1
        return resp


llm_mod.LLMClient = _StubLLM


def main() -> int:
    td = tempfile.mkdtemp(prefix="skill-builder-smoke-")
    os.environ["SKILLS_DIR"] = td
    os.environ["GEMINI_API_KEY"] = "stub-key-not-used"

    from skill_builder import run_agent

    rc = run_agent(
        "Build me a skill for writing haikus about my code",
        max_iterations=6,
    )
    if rc != 0:
        print(f"FAIL: agent returned {rc}", file=sys.stderr)
        return 1

    skill_path = os.path.join(td, "code-haiku-smoke", "SKILL.md")
    if not os.path.exists(skill_path):
        print(f"FAIL: skill not written to {skill_path}", file=sys.stderr)
        return 2

    written = open(skill_path, "r", encoding="utf-8").read()
    if not written.startswith("---") or "code-haiku-smoke" not in written:
        print(f"FAIL: content mismatch in {skill_path}", file=sys.stderr)
        return 3

    print()
    print(f"SMOKE GREEN — skill written to {skill_path}")
    print(f"SMOKE GREEN — {len(written)} bytes, starts with frontmatter")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
