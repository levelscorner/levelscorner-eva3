# levelscorner-eva3 — Knowledge Base

> Single-source context document for agents and humans working in this repo. Read this before any assignment work.

**Repo:** `~/ws/projects/levelscorner-eva3`
**GitHub:** `git@github.com:levelscorner/levelscorner-eva3.git`
**Purpose:** Weekly assignment submissions for **EAG V3** ("EVA3") — The School of AI's course on building autonomous, interoperable, production-ready agentic AI platforms.
**Status:** Act 1 in progress. S01 shipped (Chrome+LLM). S02 committed. S03 (first agent) — course content learned, assignment pending.

---

## 1. Three-Repo Mental Model

This repo doesn't stand alone. It's one of three tightly coupled workspaces:

| Repo | Path | Role |
|------|------|------|
| **levelscorner-eva3** (this) | `~/ws/projects/levelscorner-eva3` | **Submission repo** — code, deliverables, YouTube demo links per session. Public. |
| **EVA3** (study) | `~/ws/projects/EVA3` | **Study / notes workspace** — curriculum docs, assignment tracker, ideas backlog, reference materials (`docs/curriculum/`, `docs/reference/assignments.md`, `docs/reference/protocols.md`, `docs/Ideas/`). |
| **leveldb** (brain) | `~/ws/projects/leveldb` | **Config + research brain** — `.claude/` snapshot of full Claude Code environment + `mycdb/` project findings. Project pointer for this repo lives at `mycdb/projects/levelscorner-eva3/`. |

**Rule:** Implementation → this repo. Notes & curriculum study → EVA3. Cross-project decisions, competitive research, research-brain entries → leveldb/mycdb.

**Curriculum source:** <https://s3.us-east-1.amazonaws.com/theschoolof.ai/EAGV3Curriculum.html>

---

## 2. The Course Arc — 19 Sessions + Capstone

### Protocol Stack (everything ladders up to this)

```
A2UI / AG-UI    agent ↔ user interface   (generative UI)   — S14
      ↑
     A2A        agent ↔ agent            (federation)      — S13
      ↑
     MCP        agent ↔ tool             (tool protocol)   — S04
      ↑
 Agent Loop     LLM ↔ tools + memory                       — S03  ← we are here
```

### Act Breakdown

| Act | Sessions | Theme | Key Deliverables |
|-----|----------|-------|-------|
| **1 — Foundations** | S01–04 | Transformers, LLMs, dev basics, MCP | Chrome ext → +LLM → +agent → +MCP server |
| **2 — Intelligence** | S05–08 | Planning, reasoning, memory, multi-agent | Multi-step agent, 4-module cognitive pipeline, 3-tier memory, DAG executor |
| **3 — Capabilities** | S09–12 | Browser, desktop, channels, safety | Web research agent, desktop vision agent, channel adapter, container isolation + circuit breaker |
| **4 — Interoperability** | S13–15 | A2A, A2UI/AG-UI, routing, observability | A2A-compliant agent, dynamic UI generator, model router w/ cost dashboard |
| **5 — Autonomy & Production** | S16–20 | Event streams, agentic coding, eval, capstone | Event-driven agent (≥1hr autonomous), coding agent, eval harness (20+ cases), capstone pitch |

Full tracker: `~/ws/projects/EVA3/docs/reference/assignments.md`.

---

## 3. Recurring Architectural Motifs (teach-forward)

These patterns recur across sessions. Implement them consistently:

- **Agent loop (S3):** `LLM decides → Tool executes → Result feeds back → LLM decides again`. JSON-contract output: `{"tool_name", "tool_arguments"}` xor `{"answer"}`. Full conversation history carried each turn. `max_iterations` safety.
- **MCP servers (S4):** stdio or SSE transport, JSON-RPC. Python (`mcp` SDK) and TypeScript variants. Wrap a real API — pick something unique per student.
- **4-layer cognitive pipeline (S6):** Perception → Memory → Decision → Action. Typed with **Pydantic**.
- **3-tier memory (S7):** REMME (preferences) / Episodic (recipes) / Factual (knowledge). Hybrid retrieval = semantic + BM25 + **RRF** (Reciprocal Rank Fusion).
- **Graphs not loops (S8):** NetworkX `DiGraph`, topological sort, blackboard via shared session state.
- **Safety (S12):** JSON repair pipeline, circuit breaker state machine (`CLOSED → OPEN → HALF_OPEN`), Docker isolation.
- **A2A (S13):** Agent Cards (JSON capability adverts), JSON-RPC 2.0, sync / SSE / async-push modes.
- **Agentic coding (S17):** Draft → Verify → Refine loop. `GenericSkill` reads `SKILL.md`.

---

## 4. Repo Layout Convention

**Polyglot.** Python for agent pipelines and MCP servers; Node.js/TypeScript/React for extensions and UIs.

Expected layout (session-scoped folders, created as assignments ship):

```
levelscorner-eva3/
├── README.md                 # Index of shipped assignments + YouTube links
├── CLAUDE.md                 # Root agent instructions (read on every invocation)
├── AGENTS.md                 # Codex-equivalent of CLAUDE.md
├── docs/
│   └── KNOWLEDGE.md          # This file
├── s01-chrome-llm/           # ← pattern: sNN-short-slug/
├── s02-streaming-chat/
├── s03-first-agent/          # ← next
├── s04-mcp-weather/
├── s08-dag-executor/
└── ...
```

### Per-Session Rules

1. Each session folder is an **independent mini-project** with its own deps and entrypoint (`package.json`, `pyproject.toml`, `requirements.txt`, `README.md`).
2. Read the session's own docs before generalizing from a sibling.
3. Do **not** promote shared code to a root package unless explicitly asked. Assignments are graded individually.
4. Every session folder MUST contain:
   - `README.md` — what it does, how to run, YouTube demo link, LLM logs paste (per curriculum submission rule).
   - Entrypoint or install script.
   - If containing secrets → `.env.example` only; real `.env` in `.gitignore` (already configured globally).

### Build & Run

**No top-level build system.** Everything is per-session. Check the session's `README.md` first.

---

## 5. Shipped / Current Status

| Session | Status | Deliverable | Notes |
|---------|--------|-------------|-------|
| S01 | ✅ Shipped | Chrome extension + LLM API | Demo: <https://youtu.be/ZVxP6whDLqc> |
| S02 | ✅ Committed | Streaming chat extension | `Session2Assignment.md` — commits `cf28d8a`, `a581ea5`, `fa577bc` |
| S03 | 🟢 Built (2 sub-projects), pending live run + demo | **Mini Perplexity** (primary) + Skill Builder (secondary) | Both Python CLIs, 3 tools each, `rich` reasoning-chain UI, stubbed smoke tests green. **Mini Perplexity extracted 2026-04-24** to standalone repo <https://github.com/levelscorner/mini-perplexity> (local `~/ws/projects/mini-perplexity`) — build walkthrough in `docs/WALKTHROUGH.md`. Skill Builder: `search_skills` / `read_skill` / `create_skill` at `s03-first-agent/skill-builder/`. Needs `GEMINI_API_KEY` to go live. |
| S04+ | ⬜ Pending | — | — |

---

## 6. S03 Assignment Spec (current focus)

**Deliverable:** Chrome **Agentic AI** Plugin — the v3 of the S01→S02→S03 plugin arc.

**Requirements:**

1. Agent loops the LLM with **≥ 3 custom tool functions** (unique per student; not copies of course examples).
2. Each query carries the **full prior interaction history** (`Q1 → LLM → ToolCall → ToolResult → Q2(with all past) → …`).
3. Extension UI must **display the reasoning chain** — every tool call + result visible, not only the final answer.
4. Submission: YouTube demo + paste raw LLM logs in the assignment write-up.

**Example use-cases** (pick one domain unique to you):

- Math/compute: "Sum of exponential values of the first 6 Fibonacci numbers"
- External tool + channel: "Find top OTT series this week → send to Telegram/Email"
- Monitoring: "Alert me when stock X crosses price Y" (continuous)
- Multi-step research: "Search news about Ola last 30 days → correlate with stock moves on those dates"

**Core pattern to burn in:**

```
LLM decides  →  Tool executes  →  Result feeds back  →  LLM decides again
```

Tools dict = action space. System prompt + conversation history = state. Parser must strip markdown fences and fall back to regex `{.*}`. Wrap in a loop with `max_iterations`.

**Full content notes:** `memory/s3_notes.md` (6-part breakdown: debug tools, emergence, agent definition, 2026 landscape, 7-step build, code-without-AI discipline).

---

## 7. Coding Conventions for This Repo

Follows `~/.claude/CLAUDE.md` (global) + this project's `CLAUDE.md`.

**Python:**

- Use `uv venv` + `uv pip install` when possible.
- Type hints everywhere. Dataclasses for simple tool contracts; Pydantic from S06 onward.
- `try/except json.JSONDecodeError` wrapping all LLM output parsing. Strip markdown fences. Regex fallback.
- Decorator tool registry (`TOOLS[fn.__name__] = fn`) — foundation pattern, do not hand-maintain lists.
- `async def` + `await` for LLM calls. `asyncio.gather` for parallel tool invocation.
- Debugging: `breakpoint()` (3.7+) or `code.interact(local=locals())` to inspect agent state mid-loop. **No `print`-driven debugging in agent code.**

**TypeScript/React (extensions):**

- Chrome extensions follow Manifest V3.
- Message passing between popup/content/background scripts — keep handlers typed.
- Stream LLM responses when the provider supports it (Gemini, Claude via SSE).

**Security (from global rules):**

- API keys only via `chrome.storage.local` or env — **never** hardcoded in source.
- Validate LLM output before executing tools. Treat model output as untrusted input.
- Bounded `max_iterations` on every agent loop. No unbounded `while True`.

**Git:**

- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `perf:`, `ci:`.
- One session = one feature branch when it's more than a single-sitting change.
- Commit attribution disabled globally via `~/.claude/settings.json`.

---

## 8. Cross-Reference Cheat-Sheet

When you need…

- **Exact assignment scope** → `~/ws/projects/EVA3/docs/reference/assignments.md`
- **Session-level teaching detail** → `~/ws/projects/EVA3/docs/curriculum/`
- **Protocol stack deep-dive** → `~/ws/projects/EVA3/docs/reference/protocols.md`
- **Glossary / tech list** → `~/ws/projects/EVA3/docs/reference/{glossary,technologies}.md`
- **Ideas backlog** → `~/ws/projects/EVA3/docs/Ideas/`
- **S03 architecture pattern** → [`S03-ARCHITECTURE.md`](S03-ARCHITECTURE.md)
- **S03 ship playbook** → [`../s03-first-agent/RUNBOOK.md`](../s03-first-agent/RUNBOOK.md)
- **Competitive / research findings** → `~/ws/projects/leveldb/mycdb/projects/levelscorner-eva3/`
- **Dated S03 build log** → `~/ws/projects/leveldb/mycdb/projects/levelscorner-eva3/2026-04-24-s03-build-log.md`
- **Claude Code agent/skill/hook definitions** → `~/ws/projects/leveldb/.claude/` (authoritative copy; lives under `~/.claude/`)
- **Per-session memory (auto-loaded)** → `~/.claude/projects/-Users-level-ws-projects-levelscorner-eva3/memory/`

---

## 9. Operating Model for Agents

1. **Start every assignment by reading:**
   - This file.
   - The session's curriculum doc at `~/ws/projects/EVA3/docs/curriculum/sNN-*.md` (if present).
   - The assignment entry in `~/ws/projects/EVA3/docs/reference/assignments.md`.
   - Memory index at `~/.claude/projects/-Users-level-ws-projects-levelscorner-eva3/memory/MEMORY.md`.

2. **Before implementing**, confirm: which session? which tools? which submission artifacts (YouTube, logs, README)?

3. **Per-session discipline:** scaffold `sNN-short-slug/` with its own `README.md` + entrypoint + `.gitignore` additions if needed. Keep dependencies local to that folder.

4. **After shipping**, update:
   - Root `README.md` — add row to "Assignments" list with YouTube link.
   - `§5` of this file — status row for the session.
   - `~/ws/projects/leveldb/mycdb/projects/levelscorner-eva3/` — add a dated findings doc if there was anything learned worth remembering across sessions.
   - Assignment tracker in `~/ws/projects/EVA3/docs/reference/assignments.md` — tick the box.

5. **Auto-memory** (at `~/.claude/projects/-Users-level-ws-projects-levelscorner-eva3/memory/`) is managed by the Claude Code memory subsystem. Don't edit it by hand unless fixing stale entries. Current entries: `project_context.md`, `s3_notes.md`, `MEMORY.md` index.

---

*Last updated: 2026-04-23. Keep this file terse and current. When a section stops being true, fix it in the same commit that breaks it.*
