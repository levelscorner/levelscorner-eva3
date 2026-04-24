# Skill Builder — S03 Submission

An agent that builds Claude Code skills. Single-agent loop, three custom tools, reasoning chain rendered to the terminal in real time and persisted to `logs/` for submission.

> **Meta-demo:** Claude uses skills. This agent writes more skills. Watch an agent extend Claude's own extensibility system.

---

## The three tools

| Tool | Purpose |
|------|---------|
| `search_skills(query)` | Find existing skills matching a topic (user + plugin scopes). Agent uses this to avoid duplicates and discover prior art. |
| `read_skill(name)` | Load the full markdown of one existing skill. Agent studies structure before drafting its own. |
| `create_skill(name, content)` | Write `~/.claude/skills/<name>/SKILL.md`. Validates kebab-case name, required frontmatter (`name:` + `description:`), and refuses to overwrite. |

The agent's system prompt (`system_prompt.md`) enforces a `search → read → create → answer` flow. Max 6 iterations.

---

## Setup

```bash
cd s03-first-agent/skill-builder

# Virtualenv (uv recommended)
uv venv
source .venv/bin/activate
uv pip install -e .
# or: pip install -e .

# API key
cp .env.example .env
$EDITOR .env   # fill in GEMINI_API_KEY
```

Free Gemini key: <https://aistudio.google.com/apikey>
Default model: `gemini-2.5-flash-lite` (cheap, fast). Override via `GEMINI_MODEL`.

---

## Run

```bash
python skill_builder.py "I want a skill that generates haikus about code"
```

The terminal prints the full reasoning chain as it streams:

- **You** — the query
- **Iteration N** — LLM thought (raw + parsed JSON) · tool call · tool result
- **Final answer** — path to the new skill and how to invoke it

Every event is also persisted to `logs/run-<timestamp>.json` for the YouTube-submission log paste.

### Sandbox mode (no changes to `~/.claude/skills/`)

```bash
SKILLS_DIR=/tmp/skill-sandbox python skill_builder.py "Your query"
```

Reads + writes go through `SKILLS_DIR` instead of the real skills directory. Plugin skills are still searched for prior art.

---

## Example queries

Each one exercises a different part of the loop:

```bash
# Clean case — no existing skill, agent finds related, drafts, creates
python skill_builder.py "Build me a skill that turns meeting notes into action-item JSON"

# Overlap case — agent finds dupes and declines
python skill_builder.py "A skill for enforcing TDD workflow"

# Domain-specific
python skill_builder.py "A skill that reviews database migrations for unsafe operations"
```

---

## How the demo maps to the S03 rubric

| S03 Requirement | Where it lives |
|-----------------|----------------|
| Agentic loop calling LLM multiple times | `skill_builder.py` → `run_agent()` |
| Each query carries all past interaction | `_render_conversation()` flattens the full `messages[]` history every iteration |
| ≥ 3 custom tool functions | `tools.py` — `search_skills`, `read_skill`, `create_skill` |
| Display the reasoning chain | `ui.py` — `ReasoningChainUI` panels per step |
| YouTube demo + LLM logs | Record terminal session; paste `logs/run-*.json` into submission doc |

---

## Layout

```
skill-builder/
├── README.md            # this file
├── pyproject.toml       # package metadata + deps
├── .env.example         # copy to .env and fill GEMINI_API_KEY
├── system_prompt.md     # the agent's instructions (external for readability)
├── skill_builder.py     # entrypoint + agent loop
├── llm.py               # Gemini client with free-tier throttling
├── parser.py            # fence-stripping + regex-fallback JSON parser
├── tools.py             # the 3 tools + frontmatter parser + skill finder
├── ui.py                # rich-based reasoning-chain renderer + log writer
└── logs/                # run transcripts (gitignored via repo root)
```

---

## Meta-demo for the YouTube submission

1. Open a terminal — make it big so the panels render nicely.
2. Run `python skill_builder.py "a skill that generates haikus about code"`.
3. Watch the agent: search → finds no haiku skills → reads `python-patterns` for structure reference → drafts → creates `code-haiku`.
4. `cat ~/.claude/skills/code-haiku/SKILL.md` — show the artifact.
5. Open a **new** Claude Code session. Prompt: *"Write me a haiku about the skill_builder.py file."*
6. Claude fires the `code-haiku` skill the agent just wrote.
7. Submission is the video + the `logs/run-*.json` paste.

This closes the Inception loop: an agent built a skill that teaches another agent (Claude itself) to act differently.
