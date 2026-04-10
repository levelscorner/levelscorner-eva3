# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

**Assignment submission repo** for **EAG V3** ("EVA3") — a course from The School of AI on building autonomous, interoperable, production-ready agentic AI platforms. Weekly assignment code and deliverables are pushed here.

The companion study/notes workspace lives at `~/ws/projects/EVA3/` — that repo has the full curriculum docs, assignment tracker, ideas backlog, and reference materials. When working on an assignment, consult `~/ws/projects/EVA3/docs/reference/assignments.md` for the exact scope and `~/ws/projects/EVA3/docs/curriculum/` for session-level detail.

Curriculum source: <https://s3.us-east-1.amazonaws.com/theschoolof.ai/EAGV3Curriculum.html>

## Course context — the protocol stack

Everything in EVA3 ladders up to one integrated stack:

```
A2UI / AG-UI   ← agent ↔ user interface (generative UI)
     ↑
    A2A        ← agent ↔ agent (federation, discovery, delegation)
     ↑
    MCP        ← agent ↔ tool (the tool protocol)
```

## Repo structure

Expect session-scoped subfolders (e.g., `s04-mcp-weather/`, `s08-dag-executor/`). This is a polyglot repo: Python for agent pipelines and MCP servers, Node.js/TypeScript/React for extensions, UIs, and some MCP servers.

Each session folder is an **independent mini-project** with its own dependencies and entrypoint:
- Read its own `README.md` / `package.json` / `pyproject.toml` first — do not generalize from a sibling.
- Only promote shared code out of a session folder when explicitly asked.

## Assignment arc (19 sessions + capstone)

| Act | Sessions | Theme |
|-----|----------|-------|
| 1 — Foundations | S1–4 | Transformers, LLMs, dev basics, MCP |
| 2 — Intelligence | S5–8 | Planning, reasoning, memory, multi-agent DAGs |
| 3 — Capabilities | S9–12 | Browser agents, desktop control, channels, safety |
| 4 — Interoperability | S13–15 | A2A, A2UI/AG-UI, model routing, observability |
| 5 — Autonomy & Production | S16–20 | Event-driven agents, agentic coding, eval, capstone |

## Recurring architectural motifs

These patterns are explicitly taught by the curriculum — follow them when implementing assignments:

- **MCP servers (S4):** stdio or SSE transport, JSON-RPC, Python and TypeScript variants
- **4-layer cognitive pipeline (S6):** Perception → Memory → Decision → Action, typed with Pydantic
- **3-tier memory (S7):** REMME preferences, Episodic recipes, Factual knowledge; hybrid retrieval = semantic + BM25 + RRF
- **Graphs not loops (S8):** NetworkX DiGraph, topological sort, blackboard via shared session state
- **Safety (S12):** JSON repair pipeline, circuit breaker (CLOSED → OPEN → HALF_OPEN), Docker isolation
- **A2A (S13):** Agent Cards (JSON capability adverts), JSON-RPC 2.0, sync / SSE / async push modes
- **Agentic coding (S17):** Draft → Verify → Refine loop; GenericSkill reads SKILL.md

## Build & Run

_Per-session — check each session folder for its own setup. No top-level build system._
