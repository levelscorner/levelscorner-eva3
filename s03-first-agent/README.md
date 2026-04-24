# S03 — First Agent (Chrome Agentic Plugin v3)

Session 3 of EAG V3. The step from "LLM" to "Agent."

**Assignment target:** Chrome extension that runs a real agent loop — ≥ 3 custom tools, full-history context carry across turns, reasoning chain rendered in the UI, YouTube demo + LLM logs as deliverables.

> 👉 **Ready to ship?** Follow [`RUNBOOK.md`](RUNBOOK.md) — step-by-step from API key to submitted in Canvas (~45 min).

Full repo context: [`../docs/KNOWLEDGE.md`](../docs/KNOWLEDGE.md)
Course-content digest (auto-memory): `~/.claude/projects/-Users-level-ws-projects-levelscorner-eva3/memory/s3_notes.md`

---

## Status

Two sub-projects, both satisfy the S03 rubric. `mini-perplexity/` graduated to its own repo on 2026-04-24 — kept here as a pointer.

| Item | mini-perplexity ⭐ primary (extracted) | `skill-builder/` |
|------|-----------------------------------------|-------------------|
| Repo | <https://github.com/levelscorner/mini-perplexity> (`~/ws/projects/mini-perplexity`) | this folder |
| Concept | Mini Perplexity — search, read, cite | Meta agent — builds Claude Code skills |
| 3 tools | `web_search` · `fetch_page` · `save_answer` | `search_skills` · `read_skill` · `create_skill` |
| External APIs | DuckDuckGo (free, no key) | Local filesystem only |
| Reasoning-chain UI | ✅ `rich` terminal panels | ✅ same |
| Log persistence | ✅ `logs/run-*.json` | ✅ same |
| Stubbed smoke test | ✅ `_smoke_test.py` green | ✅ `_smoke_test.py` green |
| Live run with Gemini | ⬜ needs `GEMINI_API_KEY` | ⬜ same |
| YouTube demo + logs | ⬜ pending live run | ⬜ pending live run |

**Recommendation:** ship `mini-perplexity` (own repo) as the primary submission. Build walkthrough lives at [`mini-perplexity/docs/WALKTHROUGH.md`](https://github.com/levelscorner/mini-perplexity/blob/main/docs/WALKTHROUGH.md). `skill-builder/` stays here as a second, meta-agentic exploration.

---

## Reference code (`reference/`)

Verbatim course code from the session zip. Read top-to-bottom to internalize the progression from debug primitives → agent loop.

| # | File | Purpose | Key takeaway |
|---|------|---------|--------------|
| 01 | `01_code_interact_basic.py` | `code.interact()` intro | Ctrl+D continues script; `exit()` terminates |
| 02 | `02_code_interact_agent.py` | Guided tour of freezing an agent mid-loop | In the shell you can inspect `llm_response`, `conversation`, even **call tools manually** (`tools["get_weather"]("Delhi")`) |
| 03 | `03_pdb_basic.py` | `breakpoint()` (Python 3.7+) | Modern form of `pdb.set_trace()`. Commands: `p`/`pp`, `s` step-into, `n` next, `c` continue, `b N` breakpoint, `q` quit |
| 04 | `04_async_blocking.py` | Baseline: sequential `time.sleep(2)` × 2 = 4s | Motivates async |
| 05 | `05_async_nonblocking.py` | `asyncio.gather(say_hello(), say_good_bye())` = 2s | Use `asyncio.gather` for concurrent LLM/tool calls |
| 06 | `06_async_common_mistake.py` | Calling `call_llm(...)` without `await` returns a **coroutine object**, not the response | The bug you will hit |
| 07 | `07_python_essentials.py` | `try/except` for markdown-fenced JSON, `@dataclass` tool contracts, decorator-based tool registry (`TOOLS[fn.__name__]=fn`), dynamic system-prompt build via f-strings | Foundation patterns — used in every later file |
| 08 | `08_llm_basic.py` | Raw Gemini call via `google-genai` (**note: `from google import genai`, not `google.generativeai`**). Model default `gemini-3.1-flash-lite-preview`; throttle `time.sleep(10)` before each call to respect free-tier 15 RPM / 500 RPD | Shows LLMs hallucinate on real-time data + math |
| 09 | `09_llm_with_system_prompt.py` | Same model + a system prompt that enforces JSON-contract output (`tool_name`/`tool_arguments` xor `answer`) | Converting LLM → agent is just constraining the output format |
| 10 | **`10_full_agent.py`** | **The canonical full agent.** System prompt + 3 tools (`calculate`, `get_weather`, `search_notes`) + robust parser (strip ``` fences → direct `json.loads` → regex `\{.*\}` fallback) + bounded loop (`max_iterations=5`) with `messages=[system,user,assistant,tool,…]` history-carry. Five example queries at the bottom. | **Reference implementation for the assignment.** |
| 11 | `11_fake_agent.py` | "Arcturus Jr." — a regex-router posing as an agent. Real API calls to wttr.in, Wikipedia, dictionary API, DuckDuckGo, jokes, cat/dog facts, ZenQuotes, Frankfurter currency, ipapi. Fails on any query outside its regex patterns. | **Lesson:** agent = router + tools. The router is the only difference between regex and LLM. Brittle patterns are exactly why LLMs matter. |
| 12 | `12_full_agent_ollama.py` | Byte-for-byte identical to `10_full_agent.py` **except** `call_llm` hits local Ollama (`POST /api/generate`, `format:"json"`, `temperature:0.1`) instead of Gemini | Router can be cloud or local — the agent architecture is backend-agnostic. Default model `gemma4:26b`, configurable via `OLLAMA_HOST` / `OLLAMA_MODEL` env |

---

## The canonical loop (from file 10)

```
User query
   │
   ▼
messages = [system, user]
   │
   ├─► loop (max_iterations=5):
   │     prompt = flatten(messages)
   │     response_text = call_llm(prompt)
   │     parsed = parse_llm_response(response_text)   # fence-strip → json → regex fallback
   │     if "answer" in parsed:  return parsed["answer"]
   │     if "tool_name" in parsed:
   │         tool_result = tools[parsed["tool_name"]](**parsed["tool_arguments"])
   │         messages += [assistant(response_text), tool(tool_result)]
   │     else: ask LLM to retry with valid JSON
   ▼
Final answer  OR  "Max iterations reached"
```

**Output contract (enforced by system prompt):**
- Tool call: `{"tool_name": "<name>", "tool_arguments": {"<arg>": "<value>"}}`
- Final answer: `{"answer": "<text>"}`
- No markdown, no prose, JSON only.

---

## Running the reference code

```bash
# 1. venv (per-session, not repo-wide)
cd s03-first-agent
uv venv
source .venv/bin/activate

# 2. deps (superset — individual files need a subset)
uv pip install google-genai python-dotenv requests

# 3. API key (only for 08/09/10)
cat > reference/.env <<'EOF'
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.5-flash-lite
EOF

# 4. Run any file
python reference/01_code_interact_basic.py       # debug primer
python reference/10_full_agent.py                 # canonical agent
python reference/11_fake_agent.py                 # interactive regex agent
python reference/11_fake_agent.py demo            # canned-queries demo
python reference/12_full_agent_ollama.py          # needs `ollama serve` + model pulled
```

`.env` is covered by the repo-root `.gitignore` — never commit the key.

---

## Gotchas observed in the reference

1. **Import is `from google import genai`**, not `import google.generativeai as genai`. Course materials mix both; this zip uses the new `google-genai` SDK.
2. **Throttling is mandatory on the free tier** — the reference sleeps 10s before every call. Don't strip that blindly unless you have a paid key.
3. **Model names in the course text are aspirational** — `gemini-3.1-flash-lite-preview` is the default in the code but may not exist by grading time. Fall back to `gemini-2.5-flash-lite` via env.
4. **`eval()` in `calculate()` is sandboxed** — pass `{"__builtins__": {}}` as globals and an explicit allow-list (`math`, `abs`, `round`, `pow`, `sum`, `min`, `max`, `range`, `list`). Do not relax this in the extension build; treat LLM output as untrusted.
5. **`parse_llm_response` is resilient but not infallible** — the retry path on `ValueError`/`JSONDecodeError` asks the LLM to re-emit JSON. Keep that branch; LLMs drift on long runs.
6. **File 11's regex order is intentional** — small-talk first, then more-specific-tool patterns before general ones. When porting to LLM routing this reverses: let the LLM decide; the regex precedence problem disappears.

---

## What to build (the assignment)

Port `10_full_agent.py`'s loop into a Chrome MV3 extension where:

1. **≥ 3 custom tools** in a unique domain (not `calculate` / `get_weather` / `search_notes`). Pick something you'd use. Ideas: stock-quote + news-search + portfolio-math; YouTube-search + transcript-extract + sentiment-score; recipe-search + pantry-check + grocery-list-add.
2. **Conversation persistence** across popup opens — `chrome.storage.local` for `messages`.
3. **Reasoning chain UI** — render every `{role, content}` in a scrollable pane. Tool calls get a different style from user/assistant. Minimum: show the JSON of each tool call and its raw result.
4. **LLM key UX** — settings page with `chrome.storage.local` stash; never hardcode.
5. **Bounded loop** — `max_iterations=5` cap; surface the "max reached" state in the UI.
6. **Logs paste** — console.log every `(iteration, role, content)` tuple so you can copy/paste into the submission doc.

**Deliverables:** YouTube demo + raw LLM logs + this folder's code + updated root README entry.

---

## Deliverables (both Python CLIs)

The curriculum explicitly allows this: *"'Chrome Plugin' is a suggestion, if you want to make something complex its totally fine."* Each sub-project satisfies the rubric (loop + ≥3 tools + full-history carry + reasoning-chain display) on its own.

### ⭐ mini-perplexity — primary (moved to own repo)

> Extracted on 2026-04-24 to <https://github.com/levelscorner/mini-perplexity> (local: `~/ws/projects/mini-perplexity`). Kept here as a pointer so the S03 story stays coherent.

Mimics the Perplexity core loop. Given a question, it searches the web, reads the top 2–3 results, synthesizes an answer with inline citations, and saves it to `answers/<slug>.md`.

| Tool | Purpose |
|------|---------|
| `web_search(query, n=5)` | DuckDuckGo via `duckduckgo-search`. Free, no API key. |
| `fetch_page(url)` | `requests.get` + `trafilatura.extract` for clean main-article text. |
| `save_answer(question, answer, sources)` | Persists numbered-citation markdown to `answers/<slug>.md`. |

**Flow:** `web_search` → `fetch_page` ×2–3 → `save_answer` → final. Typical run: 5 iterations, 8-iter safety cap.

Full build walkthrough: [`mini-perplexity/docs/WALKTHROUGH.md`](https://github.com/levelscorner/mini-perplexity/blob/main/docs/WALKTHROUGH.md).

### [`skill-builder/`](skill-builder/) — secondary (meta-agentic exploration)

An agent that writes Claude Code skills. The meta-demo: watch Claude fire a skill another agent just wrote.

| Tool | Purpose |
|------|---------|
| `search_skills(query)` | Scan `~/.claude/skills/` + plugin skill dirs. |
| `read_skill(name)` | Load one existing skill as a structural reference. |
| `create_skill(name, content)` | Write `~/.claude/skills/<name>/SKILL.md`. |

**Flow:** `search_skills` → `read_skill` → `create_skill` → final. Typical run: 4 iterations, 6-iter safety cap.

---

## Shared architecture

Both sub-projects ship the same scaffolding. `parser.py`, `llm.py`, and `ui.py` started as identical copies so each sub-project runs independently without cross-imports. Mini-perplexity now lives in its own repo but keeps the same layout.

```
sub-project/
├── README.md            # sub-project-specific
├── pyproject.toml       # sub-project-specific (deps differ)
├── .env.example
├── .gitignore
├── system_prompt.md     # sub-project-specific
├── <name>.py            # entrypoint + agent loop
├── tools.py             # 3 tools — sub-project-specific
├── llm.py               # shared: Gemini + throttle
├── parser.py            # shared: fence-strip → json.loads → regex fallback
├── ui.py                # shared: rich panels + log writer
├── _smoke_test.py       # stubs LLM + network, verifies end-to-end
└── logs/                # gitignored
```

---

## Next actions

- [ ] Add `GEMINI_API_KEY` to `~/ws/projects/mini-perplexity/.env` (and/or `skill-builder/.env`)
- [ ] Run live: `cd ~/ws/projects/mini-perplexity && python mini_perplexity.py "What's new in Claude 4.7?"`
- [ ] Confirm artifact in `~/ws/projects/mini-perplexity/answers/<slug>.md`
- [ ] Record YouTube demo (terminal session)
- [ ] Paste `logs/run-<ts>.json` into submission doc
- [ ] Update root `README.md` + `docs/KNOWLEDGE.md` §5 with shipped status + video link
