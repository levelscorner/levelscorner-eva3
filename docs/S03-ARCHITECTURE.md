# S03 — Architecture Reference

> The architectural pattern behind the S03 assignment. Distinct from `RUNBOOK.md` (user-facing action list) and the per-agent READMEs (sub-project docs). This file explains **what we built and why it's shaped that way**, so it can be ported, extended, or remixed later.

**Status:** Two sibling sub-projects — **mini-perplexity** (primary, extracted 2026-04-24 to its own repo at <https://github.com/levelscorner/mini-perplexity> / `~/ws/projects/mini-perplexity`) and `skill-builder/` (secondary, still under `s03-first-agent/`). Both implement the same agent-loop architecture. Both pass stubbed end-to-end smoke tests. Both pending live Gemini runs.

Related docs:
- [`KNOWLEDGE.md`](KNOWLEDGE.md) — repo-wide context and the three-repo mental model
- [`../s03-first-agent/README.md`](../s03-first-agent/README.md) — session overview
- [`../s03-first-agent/RUNBOOK.md`](../s03-first-agent/RUNBOOK.md) — step-by-step ship instructions
- [`../s03-first-agent/reference/`](../s03-first-agent/reference/) — verbatim course Python (files 01–12)

---

## 1. The S03 Pattern — One Picture

```
                    ┌────────────────────────────────────────┐
                    │   system_prompt.md                     │
                    │   (role, tool schemas, JSON contract)  │
                    └────────────────┬───────────────────────┘
                                     │
User query ──────────────────────────▼──────────────────────────┐
                                                                │
              ┌─────────────────────────────────────────┐       │
              │   messages = [{role: user, content}]    │◄──────┘
              └───────────────────┬─────────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │   for iteration in 1..max_iter:   │
                │                                   │
                │     prompt = flatten(messages)    │
                │     raw    = llm.generate(prompt) │────────► Gemini
                │     parsed = parse(raw)           │
                │                                   │
                │     if parsed has "answer":       │
                │         return parsed.answer      ├─────────► Final
                │                                   │
                │     if parsed has "tool_name":    │
                │         result = TOOLS[name](args)│────────► Side effect
                │         messages.append(assistant, tool)
                │         continue                  │
                │                                   │
                │     else: ask model to retry      │
                └───────────────────────────────────┘
```

The core insight (from `reference/10_full_agent.py`): **an agent is an LLM in a loop whose output is constrained to a JSON contract of either `{tool_name, tool_arguments}` or `{answer}`.** Everything else — MCP, multi-agent, DAGs, memory, browser agents — is sophistication bolted onto this loop.

---

## 2. Layered File Structure

Every sub-project under `s03-first-agent/` follows the same layout. Files shared across both sub-projects are **copied, not imported** — enforces the "each session folder is an independent mini-project" rule from `CLAUDE.md`.

```
<sub-project>/
├── README.md            # what this agent is, how to run, example queries
├── pyproject.toml       # deps (core + agent-specific)
├── .env.example         # GEMINI_API_KEY + knobs
├── .gitignore           # logs/, .venv/, __pycache__/
├── system_prompt.md     # agent role, tool schemas, workflow, quality bar
├── <agent>.py           # entrypoint + run_agent() loop
├── tools.py             # 3 custom tools + TOOLS registry
├── llm.py               # ★ shared — Gemini wrapper + throttle
├── parser.py            # ★ shared — robust JSON parser
├── ui.py                # ★ shared — rich panels + log writer
├── _smoke_test.py       # stubs LLM + network, verifies end-to-end
├── answers/ | logs/     # runtime artifacts (gitignored)
└── .venv/               # per sub-project, gitignored
```

★ = identical across sub-projects. If you change one, mirror to the others.

---

## 3. The Five Load-Bearing Modules

### 3.1 `system_prompt.md` — external, tunable

Kept as a plain markdown file (not a Python string) so:
- Edits don't require a re-import or restart during development.
- Diffs read cleanly in git.
- Future A/B testing can load two prompts and compare.

**Must contain:**
1. Agent role in one sentence.
2. Exact schema of each tool (`name(arg: type)`, return shape).
3. The JSON response contract — *"Respond with exactly one JSON object, no prose, no fences."*
4. Required workflow order (e.g., `search → read → create → answer`).
5. Quality bar — what separates a good output from a shipped output.
6. Recovery guidance — what to do when a tool returns `{"error": ...}`.

### 3.2 `<agent>.py` — the loop

Single entrypoint. `run_agent(query, max_iterations)` returns 0 on success, 2 on iteration exhaustion, 1 on infrastructure failure.

**Conversation format (matches `reference/10_full_agent.py`):**

Messages are stored as a list of `{role, content}` dicts and flattened into a single prompt string every iteration via `_render_conversation`. The rendered prompt looks like:

    <system_prompt>

    User: <user query>

    Assistant: <prior LLM JSON response>

    Tool Result: <prior tool JSON output>

    Assistant: <next LLM JSON response>

    Tool Result: <next tool JSON output>

    ...

    Assistant:

The trailing `Assistant:` primes the next generation. Every iteration carries the **full history** — this is the "Query3 stores all past interaction" rule from the S03 spec.

**Iteration budget:** mini-perplexity uses 8, skill-builder 6. Picked so a happy path fits with headroom for one retry after a parse failure.

### 3.3 `tools.py` — the 3 custom tools

**Contract:** each tool function:
1. Takes keyword arguments matching the LLM's `tool_arguments` keys.
2. Returns a JSON **string** (not a dict) — callers splice it straight into `messages` as `{role: "tool", content: <returned string>}`.
3. Never raises; any internal failure returns `json.dumps({"error": ..., "hint": ...})` so the agent can recover on the next iteration.
4. Validates inputs at the boundary (URL scheme, slug regex, required args).

**Registry pattern:** a module-level `TOOLS = {"name": fn, ...}` dict dispatched by the loop. Matches the decorator pattern in `reference/07_python_essentials.py`.

### 3.4 `parser.py` — the resilient JSON parser

Ported from `reference/10_full_agent.py`. Three-tier strategy:

1. Strip markdown code fences (```` ``` ```` or ```` ```json ````).
2. Try `json.loads` on what's left.
3. Fall back to regex `\{.*\}` across the whole response (DOTALL flag).
4. Raise `ValueError` with the first 200 chars for diagnostics.

**Why this exists:** Gemini and friends randomly wrap JSON in fences, sometimes add trailing prose, occasionally add a leading "Here's the JSON:". The parser is the only thing standing between the model's drift and a crashed agent loop.

**Gotcha found during build:** the frontmatter parser in `skill-builder/tools.py` initially required a trailing newline after the closing `---`. Fixed by accepting `\Z` as an alternative terminator. Tests caught this — see `_smoke_test.py` step 8.

### 3.5 `ui.py` — the reasoning-chain renderer

Uses `rich.Panel` to render each event as a bordered box with a colored label. Also writes every event to `logs/run-<timestamp>.json` as a structured list — the submission's log paste comes straight out of that file.

**Event kinds:** `user`, `llm`, `tool_call`, `tool_result`, `final`, `error`, `system`. Each has its own border color so scanning the terminal history is easy.

**Why external log:** the stdout rendering is ephemeral and doesn't copy cleanly. The JSON log is machine-readable and pastes straight into the submission doc.

---

## 4. The Two Sub-Projects — Side by Side

| Dimension | `mini-perplexity/` | `skill-builder/` |
|-----------|---------------------|-------------------|
| Concept | Mimics Perplexity — search, read, cite | Meta agent — writes Claude Code skills |
| Tool 1 | `web_search(query, n)` — DuckDuckGo via `duckduckgo-search` | `search_skills(query)` — scans `~/.claude/skills/` + plugins |
| Tool 2 | `fetch_page(url)` — `requests.get` + `trafilatura.extract` | `read_skill(name)` — loads full SKILL.md |
| Tool 3 | `save_answer(q, md, sources)` — writes `answers/<slug>.md` | `create_skill(name, content)` — writes `~/.claude/skills/<name>/SKILL.md` |
| External network | yes (DuckDuckGo + arbitrary URLs) | no (local filesystem only) |
| Artifact | Markdown file with numbered citations | Claude Code skill, firable from a new session |
| Extra deps | `duckduckgo-search`, `trafilatura`, `requests` | *(none beyond core)* |
| Typical run | 5 iterations (1 search + 2–3 fetches + 1 save + 1 final) | 4 iterations (1 search + 1 read + 1 create + 1 final) |
| Meta-demo | Compare answer against the actual source pages | Fresh Claude session fires the skill the agent just wrote |

Both share `llm.py`, `parser.py`, `ui.py` verbatim.

---

## 5. Testing Strategy — Stubbed End-to-End

Each sub-project ships `_smoke_test.py` that stubs **both** the LLM and the network, then runs `run_agent` end-to-end. Result: the full loop exercises in ~1 second, zero API quota burned, zero network flakiness.

**What gets stubbed:**

| Dependency | Stubbing technique |
|------------|---------------------|
| `LLMClient.generate` | Replace `llm.LLMClient` with a class that returns canned responses from a list, indexed by iteration. |
| `duckduckgo_search.DDGS` | Replace with a context-manager class whose `.text()` returns fixtures. |
| `requests.get` | Monkey-patch `requests.get` to return a fake response with canned HTML bodies keyed by URL. |

**What gets asserted:**

- Agent returns 0 (success exit code).
- The artifact (`answers/*.md` or `~/.claude/skills/<name>/SKILL.md`) exists on disk in the sandbox dir.
- The artifact content contains expected markers (citation numbers, frontmatter).

**Why stub both layers:** the rubric cares about the **loop**, not the quality of real Gemini output. Stubbed smokes prove the loop works; live runs prove the prompt works.

---

## 6. Deliberate Non-Goals

Things intentionally **not** done in this build:

- **No shared Python package.** `llm.py` / `parser.py` / `ui.py` are copied across sub-projects. Matches the repo rule "each session folder is an independent mini-project."
- **No streaming.** The loop is request/response per iteration. Streaming is a V2 concern (S05+ where planning and intermediate feedback matter).
- **No tool schemas advertised to the model via a tool-calling API.** Everything goes through the system prompt and JSON-contract output. Matches the course pedagogy: you learn the raw pattern before MCP hides it (S04).
- **No retries beyond one.** If `parse_llm_response` fails, the loop asks the LLM to try again once and moves on if it fails again. Don't over-engineer; the rubric accepts `Max iterations reached`.
- **No multi-threading / asyncio.** The reference code uses async (files 04–06) to motivate the concept; actual S03 canonical agent (file 10) is synchronous. We match that. Async is a later-session optimization.

---

## 7. Extending the Pattern

If you want to add a 4th tool, remix for S04, or port to another backend:

### Add a new tool

1. Write the function in `tools.py`. Must be keyword-args, must return `json.dumps({...})`.
2. Add it to the `TOOLS` registry dict.
3. Document it in `system_prompt.md` with its exact signature.
4. Add a canned response for it in `_smoke_test.py`.

### Swap the LLM backend

Only `llm.py` changes. Keep the `LLMClient.generate(prompt: str) -> str` shape. See `reference/12_full_agent_ollama.py` for the local-Ollama reference.

### Wrap it in an HTTP UI

The loop in `<agent>.py` doesn't know it's in a terminal. A FastAPI wrapper can call `run_agent` and push UI events over SSE — reuse the event format from `ui.ReasoningChainUI` (each `_emit` call becomes an SSE frame).

### Port to MCP (S04 preview)

Each tool function in `tools.py` maps cleanly to an MCP tool. The MCP server exposes them; the agent calls them via MCP instead of a local registry. The loop is unchanged.

---

## 8. Decisions Log (dated)

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-23 | Python CLI instead of Chrome extension | Curriculum permits; skills + Perplexity both better-suited to CLI form; terminal records cleanly |
| 2026-04-23 | Two sub-projects, both self-contained | Explored skill-builder first, then pivoted to mini-perplexity. Kept both; each is independently runnable and gradable |
| 2026-04-23 | Copy shared files, don't factor out | Repo rule "each session folder is independent" — cross-folder imports discouraged |
| 2026-04-23 | Stubbed smoke tests at both LLM and network layers | Keeps CI-friendly, zero API quota burn, survives network flakes |
| 2026-04-23 | `system_prompt.md` external, not inline string | Easier to diff, edit, A/B test later |
| 2026-04-23 | `rich` + persistent JSON log, not just stdout | Stdout is ephemeral; submission needs copy-pasteable log |
| 2026-04-23 | DuckDuckGo for search, not Google / Tavily / Brave | Free, no API key, good enough for demo |
| 2026-04-23 | `trafilatura` for article extraction, not Readability | More robust on modern JS-heavy sites, actively maintained |
| 2026-04-23 | mini-perplexity primary, skill-builder secondary | Perplexity is more recognizable; external-network demos have more signal |

---

## 9. Future Moves Seeded Here

These patterns seed later-session work. Keep the pointers alive:

- **S04 — MCP**: wrap `tools.py` functions as an MCP server. The agent becomes the first MCP client.
- **S06 — Cognitive pipeline**: separate the loop into Perception → Memory → Decision → Action stages with Pydantic types at each boundary.
- **S07 — Memory**: add a persistent store (SQLite + embeddings) so answers from past runs can be re-cited.
- **S08 — DAG**: turn a multi-tool sequence into an explicit DAG; schedule `fetch_page` calls in parallel.
- **S14 — A2UI / AG-UI**: replace the `rich` terminal renderer with a browser-side interactive reasoning chain.
- **Chotu crossover**: the single-agent loop we built is the missing piece for Chotu's `tool_agent` node type (v1.1+ backlog). When Chotu picks this up, port `tools.py` + `parser.py` to Go and embed the loop inside a DAG node.
