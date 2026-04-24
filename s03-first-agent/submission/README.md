# Session 3 — Submission

**Student:** Rabhinav &lt;rabhinavcs@gmail.com&gt;
**Date:** 2026-04-24
**Assignment:** Build your first agent — ≥3 custom tools, full-history carry, reasoning chain displayed, YouTube demo + LLM logs.

## Video

▶️ **CLI demo:** <https://youtu.be/w-UFTm1Vivw>

## What I built

**Mini Perplexity** — a research agent that takes a free-form question, searches the web, reads the 2–3 most relevant pages, synthesizes an answer with inline citations, and persists it to disk as markdown.

### Three custom tools

| Tool | What it does |
|------|--------------|
| `web_search(query, n)` | DuckDuckGo via `ddgs` (no API key). Returns ranked `{title, url, snippet}` results. |
| `fetch_page(url)` | `requests.get` + `trafilatura.extract` for clean main-article text. Truncated to 5000 chars. |
| `save_answer(question, answer, sources)` | Persists a markdown answer with numbered `[1]`, `[2]` citations to `answers/<slug>.md`. |

### The loop

```
User query
    │
    ▼
messages = [{role: user, content}]
    │
    ├─► for iter in 1..max_iterations:
    │       prompt = flatten(system + messages)          # full history every turn
    │       raw    = LLMClient.generate(prompt)
    │       parsed = parse_llm_response(raw)             # fence-strip → json.loads → raw_decode → regex
    │       if "answer" in parsed: return parsed["answer"]
    │       if "tool_name" in parsed:
    │           result = TOOLS[parsed.tool_name](**parsed.tool_arguments)
    │           messages += [assistant(raw), tool(result)]
    ▼
Final answer  OR  "Max iterations reached"
```

**LLM backend:** Gemini 2.5 Pro via the new `google-genai` SDK, with `stop_sequences = ["\nTool Result:", "\nUser:", "\nSystem:"]` to prevent prompt-continuation drift.

**Reasoning chain:** every event — user query, LLM thought, tool call, tool result, final answer, error — rendered in real time as a colored `rich` panel AND persisted to `logs/run-<timestamp>.json`. See the log files next to this README.

## LLM logs

Three representative clean runs (5 iterations each, 0 parse errors, final answer produced):

| Question | Log | Events |
|----------|-----|--------|
| "How does MCP (Model Context Protocol) work and who uses it?" | [`logs/run-20260424T162536Z.json`](logs/run-20260424T162536Z.json) | 15 |
| "What's new in Claude 4.7?" | [`logs/run-20260424T161643Z.json`](logs/run-20260424T161643Z.json) | 9 |
| "What is the status of the Artemis Mission?" | [`logs/run-20260424T163631Z.json`](logs/run-20260424T163631Z.json) | 15 |

Each log captures every `ChainEvent` in order: `user → llm → tool_call → tool_result → … → final`.

## How the build maps to the S3 rubric

| S3 requirement | Where it lives |
|----------------|----------------|
| Agentic loop calling LLM multiple times | `mini_perplexity.py` → `run_agent()` |
| Each query carries all past interaction | `_render_conversation()` flattens the full `messages[]` history every iteration |
| ≥ 3 custom tool functions | `tools.py` → `web_search`, `fetch_page`, `save_answer` |
| Display the reasoning chain | `ui.py` → `ReasoningChainUI` (rich panels in the terminal, JSON log on disk) |
| YouTube demo + LLM logs | Video above + `logs/` in this folder |

## Repos

- **Mini Perplexity (primary submission — standalone repo)**
  <https://github.com/levelscorner/mini-perplexity>
- **EAG V3 course submissions (this repo)**
  <https://github.com/levelscorner/levelscorner-eva3> → [`s03-first-agent/`](..)

