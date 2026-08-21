# Ratchet

A ratchet turns one way only. You hand it a bug report; it turns the code from
red to green and can never turn back, because the thing that judges it is a test
the coding agent is physically unable to edit.

**The agent cannot mark its own homework — and you can verify that rather than
trust it.**

The engine is [S17Code](../../../../S17Code). Ratchet imports it. Nothing about
the coding loop, the guard, the anchor-based editor or the bounded command runner
is reimplemented here.

## The run

| Phase | What it is | Write authority |
|---|---|---|
| `author_test` | **the grader** — one S17Code run whose only job is to write a pytest that fails because of the reported bug | `create_file` only, and only to an unprotected staging path |
| `red` | the harness runs that test. It must exit 1 (an assertion failed). Anything else means the grader did not capture the bug and the run stops | none — no agent runs the judge |
| `fix` | **the coder** — a *separate* S17Code run per attempt: own `run_id`, own graph, own `EditLedger`, own memory tenant, own gateway session. It is handed the failing output as text and nothing else | `edit_code`, `create_file` — both through `guard.py` |
| `green` / `failed` | the harness re-runs the test, and re-hashes it | none |

Between the phases sits the receipt. The authored test is promoted into
`tests/` — which `s17code/coding/guard.py` protects by default — and hashed the
moment it lands. At the end it is hashed again. Same sha256 means the green suite
was earned. A different sha256 means the run is reported **void**, whatever the
exit code said.

Two decisions are load-bearing and deliberate:

- **The harness runs the judge, not the agent.** Neither phase is granted
  `run_command` authority, so S17Code's planner never even sees it advertised.
  Ratchet runs pytest itself through `s17code.coding.exec.run_command` — the same
  allowlist, no shell, workspace-confined, timeout-bounded.
- **The guard is never relaxed, not even for the grader.** The grader creates its
  test at `.ratchet/<run>/authored_case.py`, which no protected pattern matches;
  the harness moves it into `tests/`. At no point does any agent hold write
  authority over a test path.

A failing run is a first-class outcome. If the coder cannot turn it green inside
the attempt budget, the stream carries `phase: failed` with the last red output
and `done` with `ok: false`. If the coder reaches for the test file, the
`GuardError` is streamed as a `node` with `state: "fail"` — that refusal is the
product demo, so it is shown, not swallowed.

## Endpoints

```
GET  /                 the single page client
POST /run              {"bug": "...", "target": "relative/path.py"} -> {"runId"}
GET  /stream/{runId}   text/event-stream
GET  /health           {"ok": true, ...}
```

## The SSE contract

```
event: phase   data: {"phase":"author_test"|"red"|"fix"|"green"|"failed","note":"..."}
event: node    data: {"id":"...","label":"...","state":"running"|"ok"|"fail","detail":"..."}
event: cmd     data: {"cmd":"...","exit":0,"output":"...tail of stdout/stderr..."}
event: diff    data: {"path":"...","patch":"...unified diff..."}
event: proof   data: {"testPath":"...","sha256Before":"...","sha256After":"...","unchanged":true}
event: done    data: {"ok":true,"summary":"..."}
```

A stream replays from the beginning at whatever moment a client connects, so a
refreshed tab never loses the receipt.

## Running it

Ratchet needs S17Code importable and S17Code's gateway (`GLC_BASE_URL`, default
`http://127.0.0.1:8111`) reachable, because that is where the models live.

```bash
cd s17-ratchet

S17CODE_ROOT=/path/to/S17Code \
RATCHET_WORKSPACE=/path/to/repo/under/repair \
RATCHET_PYTEST="/path/to/repo/.venv/bin/python -m pytest -q" \
/path/to/S17Code/.venv/bin/python -m uvicorn app:app --port 8117
```

`RATCHET_PYTEST` should name an interpreter that can import the repository under
repair; commands run with a minimal environment, so an absolute path is safest.
Its `argv[0]` basename must be on S17Code's allowlist (`python` is).

### Environment

| Variable | Default | Meaning |
|---|---|---|
| `RATCHET_WORKSPACE` | *required* | the git repository under repair |
| `S17CODE_ROOT` | — | S17Code checkout, put on `sys.path` if set |
| `RATCHET_PYTEST` | `python -m pytest -q` | how the harness runs the judge |
| `RATCHET_MAX_ATTEMPTS` | `3` | coder attempts before the run is declared failed |
| `RATCHET_PHASE_TIMEOUT` | `600` | seconds before an agent run is abandoned |
| `RATCHET_TEST_TIMEOUT` | `120` | seconds before pytest is killed |
| `RATCHET_POLL_SECONDS` | `0.25` | how often the engine's journal is drained for `node` events |
| `RATCHET_CLIENT` | `client/index.html`, then `static/index.html` | the client served at `/`; a reference one is built into `app.py` as a fallback |
| `RATCHET_HOST` / `RATCHET_PORT` | `127.0.0.1` / `8117` | only used by `python app.py` |
| `S17_DATA_DIR` | `~/.ratchet` | kept separate from a running S17Code service's `~/.s17code` |
| `GLC_BASE_URL` | `http://127.0.0.1:8111` | S17Code's model gateway |
| `S17_GATEWAY_PROVIDER` | `gemini` | which gateway provider plans the runs; if this names a provider the gateway does not serve, every run fails at the planner and the stream says so |
