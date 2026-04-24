# S03 Runbook — Ship the Assignment

A step-by-step playbook. Follow top to bottom. Each step has a copy-pasteable command and a clear **Done when** signal.

Total time end-to-end: **~45 minutes** (pre-flight 5 min → run 5 min → demo 20 min → write-up 15 min).

---

## Step 0 — Pick which agent to ship

Two working agents from this session:

- ⭐ **mini-perplexity** (extracted to its own repo on 2026-04-24: <https://github.com/levelscorner/mini-perplexity>, local `~/ws/projects/mini-perplexity`) — searches the web, reads top sources, cites — *recommended, uses this runbook's example commands*
- `skill-builder/` (still in this folder) — writes Claude Code skills (meta demo)

Rest of this runbook assumes **mini-perplexity**. For skill-builder, swap the path to `~/ws/projects/levelscorner-eva3/s03-first-agent/skill-builder` and the script name to `skill_builder.py`.

---

## Step 1 — Get a Gemini API key

1. Open <https://aistudio.google.com/apikey>
2. Sign in with your Google account.
3. Click **"Create API key"** → copy the key (starts with `AIza...`).

**Done when:** you have a string that looks like `AIzaSyX...` on your clipboard.

Cost: free tier gives 15 requests/minute, 500/day. Enough for the demo.

---

## Step 2 — Drop the key into `.env`

```bash
cd ~/ws/projects/mini-perplexity
cp .env.example .env
```

Open `.env` in your editor and fill in:

```env
GEMINI_API_KEY=AIzaSyX...paste-your-key-here...
GEMINI_MODEL=gemini-2.5-flash-lite
THROTTLE_SECONDS=4
SEARCH_MAX_RESULTS=5
FETCH_MAX_CHARS=5000
ANSWERS_DIR=
```

`ANSWERS_DIR=` blank means answers go to `./answers/` inside the sub-project.

**Done when:** `.env` exists with your real key. It's gitignored (repo root `.gitignore` line 138), so it won't commit.

---

## Step 3 — Activate the venv

The venv was created during build. Reactivate it:

```bash
cd ~/ws/projects/mini-perplexity
source .venv/bin/activate
```

**Done when:** your prompt shows `(mini-perplexity)` or similar, and `which python` returns a path inside `.venv/`.

If `.venv/` doesn't exist (fresh clone / you deleted it):

```bash
uv venv --python 3.14
source .venv/bin/activate
uv pip install -e .
```

---

## Step 4 — Dry-run the smoke test (no network, no key needed)

Verify everything is wired before burning API quota:

```bash
python _smoke_test.py
```

**Done when:** you see `SMOKE GREEN — answer at ...` and `SMOKE GREEN — ... bytes, citations present` at the bottom, and no traceback.

If it fails, fix that before moving on. Re-activate the venv if imports are missing.

---

## Step 5 — First live run (the one you'll record)

Pick a question that is:

- **Time-sensitive** — something the LLM can't know without searching. "What's new in X this month?" works.
- **Multi-source-worthy** — an answer a sensible person would want 2–3 sources for.
- **Not embarrassing on camera** — no personal data, no politics, no niche jokes.

Strong picks (pick one):

```bash
python mini_perplexity.py "What's new in the latest Gemini release?"
python mini_perplexity.py "What are the main features of Anthropic's Claude 4.7?"
python mini_perplexity.py "How does MCP (Model Context Protocol) work and who uses it?"
python mini_perplexity.py "What's the current price of Bitcoin and what moved it this week?"
```

**Watch the terminal as it runs.** You should see roughly this sequence:

1. `Iteration 1` → LLM thought (JSON) → `web_search` tool call → tool result (list of URLs)
2. `Iteration 2` → LLM thought → `fetch_page` tool call → tool result (extracted text)
3. `Iteration 3` → LLM thought → `fetch_page` tool call → tool result
4. *(optional)* `Iteration 4` → another `fetch_page` if the agent wants a third source
5. `Iteration N-1` → LLM thought → `save_answer` tool call → tool result (`saved: true`, `path: ...`)
6. `Iteration N` → **Final answer** — one sentence + the path

At the bottom: `Full reasoning chain saved to logs/run-<timestamp>.json`

**Done when:**

- Final answer panel rendered (green border).
- `answers/<slug>.md` exists and contains your answer with `[1]`, `[2]` citations.
- `logs/run-<timestamp>.json` exists.

If the agent hits `Max iterations reached without a final answer`, re-run once — LLM drift happens. If it fails repeatedly, check **Troubleshooting** below.

---

## Step 6 — Verify the artifact

```bash
ls answers/
cat answers/*.md
```

**Done when:** the markdown has:

- A question heading
- An answer body with inline `[1]`, `[2]`, `[3]` markers
- A `## Sources` section with numbered links matching the markers

If citations are sparse or sources look garbage, try a different question — some topics don't search well on DuckDuckGo.

---

## Step 7 — Record the YouTube demo

**Setup:**

1. Make your terminal window **big** — at least 100 chars wide. `rich` panels look bad when wrapped.
2. Use a light background if possible (clearer on YouTube's compression).
3. Close anything with notifications (Slack, Mail, Messages).

**Record:**

Use the built-in macOS tool — `Cmd+Shift+5` → "Record Selected Portion" → select your terminal window.

Or use **OBS** if you have it (free, `brew install --cask obs`).

**Script (aim for 3–4 minutes):**

1. **(20 sec)** Briefly state what you built. Example:
   > "I built a Mini Perplexity agent for EAG V3 Session 3. It takes a question, searches the web, reads the top sources, and synthesizes an answer with citations. Three tools — web_search, fetch_page, save_answer — in a bounded agent loop."

2. **(10 sec)** Show the code layout briefly: `ls mini-perplexity/`. Call out `tools.py`, `mini_perplexity.py`, `system_prompt.md`.

3. **(2–3 min)** Run the agent live:
   ```bash
   python mini_perplexity.py "What are the main features of Anthropic's Claude 4.7?"
   ```
   Let it play out. Let each panel render — the reasoning chain is the whole point of the demo. Narrate each step briefly:
   - *"Here's the LLM's first thought — it decides to call `web_search`."*
   - *"Tool result — five URLs, ranked."*
   - *"Now the LLM picks the most relevant URL and fetches it."*
   - *"...etc."*

4. **(30 sec)** Show the artifact:
   ```bash
   cat answers/*.md
   ```

5. **(20 sec)** Close with a one-line summary:
   > "That's the S03 pattern — LLM decides, tool executes, result feeds back, LLM decides again, bounded by max iterations."

**Done when:** you have an MP4 / MOV of 3–4 min and it plays back cleanly.

---

## Step 8 — Upload to YouTube

1. Go to <https://studio.youtube.com>.
2. **Upload video** → drop the file.
3. **Title:** `EAG V3 S03 — Mini Perplexity Agent (Rabhinav)`
4. **Description:** paste the "Description template" from Step 9 below.
5. **Visibility:** **Unlisted** (link-share with the graders, not public).
6. Copy the video URL.

**Done when:** you have a `youtu.be/<id>` link in your clipboard.

---

## Step 9 — Write the submission

The assignment wants: **YouTube video + pasted LLM logs**. Create `s03-first-agent/SUBMISSION.md`:

```markdown
# Session 3 Assignment — Submission

**Student:** Rabhinav (rabhinavcs@gmail.com)
**Date:** <today>

## Video

<paste YouTube URL here>

## What I built

Mini Perplexity — a research agent that takes a free-form question, searches the
web, reads the 2–3 most relevant pages, synthesizes an answer with inline
citations, and persists it to disk.

**Three tools:**
1. `web_search(query, n)` — DuckDuckGo, no API key.
2. `fetch_page(url)` — requests + trafilatura for clean article text.
3. `save_answer(question, answer, sources)` — persists markdown with numbered
   citations to `answers/<slug>.md`.

**The loop:** `LLM decides → tool executes → result feeds back → LLM decides again`,
capped at 8 iterations, with the full conversation history carried every turn.

**Repos:**
- Agent: <https://github.com/levelscorner/mini-perplexity> (standalone)
- Course submission shell: <https://github.com/levelscorner/levelscorner-eva3> → `s03-first-agent/` (runbook, arch doc, skill-builder, reference code)

## LLM logs

<paste the contents of logs/run-<timestamp>.json here>
```

To grab the log:

```bash
cat logs/run-*.json | pbcopy      # macOS — puts the latest run in your clipboard
```

*(If you have multiple runs, pick the one you recorded.)*

**Description template for the YouTube upload:**

```
EAG V3 Session 3 assignment — a Mini Perplexity agent built in Python.

Given a question, it:
  1. Searches the web via DuckDuckGo (no API key)
  2. Reads the top 2–3 results with trafilatura
  3. Synthesizes a cited markdown answer
  4. Persists it to disk

Three custom tools (web_search, fetch_page, save_answer) in a bounded
LLM-in-a-loop pattern with full conversation history carried every turn.

Code: https://github.com/levelscorner/levelscorner-eva3
```

**Done when:** `SUBMISSION.md` exists, YouTube URL is in it, log JSON is pasted.

---

## Step 10 — Commit and push

```bash
cd ~/ws/projects/levelscorner-eva3
git status
git add s03-first-agent/ docs/ README.md
git status                          # sanity check — no .env, no logs/, no .venv/
git commit -m "feat(s03): mini-perplexity agent + runbook + submission"
git push
```

Check `git status` between the add and commit — you should NOT see:

- `.env`
- `.venv/`
- `logs/`
- `__pycache__/`

All are gitignored. If any show up, something's off — do not commit them.

**Done when:** `git push` succeeds and the new files show up on <https://github.com/levelscorner/levelscorner-eva3>.

---

## Step 11 — Submit in Canvas

Paste into the assignment submission box:

- YouTube link
- Repo link (GitHub)
- The `SUBMISSION.md` content (or attach it)

**Done when:** Canvas shows submitted, with a timestamp before the deadline.

---

## Troubleshooting

### `GEMINI_API_KEY not set`
`.env` didn't load. Check: (a) file named exactly `.env` not `.env.txt`, (b) you're in `mini-perplexity/` when running, (c) no quotes around the key value.

### `429 Too Many Requests`
Free-tier rate limit hit. `THROTTLE_SECONDS=4` helps but isn't bulletproof. Bump to `THROTTLE_SECONDS=8` in `.env` and re-run.

### `search failed: ... Ratelimit` / empty search results
DuckDuckGo got grumpy. Wait 60 seconds and re-run, or switch to a different question.

### Agent hits `Max iterations reached`
LLM drifted. Bump `--max-iterations 12`:
```bash
python mini_perplexity.py --max-iterations 12 "Your question"
```
Or re-run — responses aren't deterministic.

### `ModuleNotFoundError: No module named 'duckduckgo_search'`
Venv not active. Run `source .venv/bin/activate` from inside `mini-perplexity/`.

### `fetch_page` returns HTTP 403 or empty text
Some sites block `requests` user-agent. That's expected — the agent should move to the next source. If every source fails, pick a different question (news sites, docs, blog posts work best).

### Citations don't match sources
The LLM miscounted. Not a code bug — re-run the query. If it happens often, that's a prompt-engineering improvement for v2.

### Terminal `rich` panels look garbled
Your terminal is too narrow, or is monochrome-only. Widen to 100+ cols, use a true-color terminal (iTerm2, Alacritty, modern Terminal.app).

---

## Stretch goals (if you have time)

None of these are required to ship S03. They're fun follow-ups:

- [ ] Swap the LLM backend — add an Ollama path (copy the `12_full_agent_ollama.py` pattern from `reference/`).
- [ ] Add a 4th tool: `summarize_page(url, style)` that does a second LLM call on a fetched page.
- [ ] Wrap the CLI in a tiny FastAPI + HTML SSE viewer so the reasoning chain renders in a browser instead of a terminal.
- [ ] Port the tools into an MCP server (S04 preview).
- [ ] Record a second demo for `skill-builder/` and submit both.

---

*Last updated on creation. Keep this file accurate — if a step breaks, fix the step in the same sitting.*
