"""Two locked phases against the real S17Code engine.

Phase A is a grader. Its only job is to turn a free-text bug report into one
pytest that fails because of the bug. It is given ``create_file`` and nothing
else that writes: it cannot edit source, and it cannot run anything.

Phase B is a coder. It is a *separate* S17Code run — its own ``run_id``, its own
graph, its own ``EditLedger`` (so it must read every file it edits, from
scratch), its own memory tenant, its own gateway session. It never sees phase A's
graph, evidence or answer. It is handed the failing test output as text, the way
a human would paste it into a ticket.

Between them sits the guard. The authored test is promoted into ``tests/``, which
``s17code/coding/guard.py`` protects by default, and hashed. If phase B reaches
for it, ``apply_edit``/``create_file`` raise ``GuardError`` before touching the
disk; the worker failure lands in the graph journal as a node result, and Ratchet
streams that refusal to the UI as evidence rather than swallowing it.

Two deliberate decisions worth stating plainly, because both are load-bearing:

**The harness runs the judge, not the agent.** Neither phase gets ``run_command``
authority. The planner therefore never even sees it advertised (S17Code hides
side-effect capabilities a run lacks authority for). Ratchet runs pytest itself,
through S17Code's own ``s17code.coding.exec.run_command`` — same allowlist, same
no-shell rule, same workspace confinement, same timeout — so the verdict is
produced under the engine's bounds by something the agent cannot influence. An
agent that both writes the fix and reports the exit code is marking its own
homework by a longer route.

**Phase A writes to staging, not to ``tests/``.** The guard is never relaxed, not
even for the grader, not even for one call. The grader creates its test at an
unprotected staging path with the real ``create_file`` capability; the harness
promotes that file into ``tests/`` and seals it there. So at no point in the run
does any agent hold write authority over a test path.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from s17code.coding import GuardError, Workspace
from s17code.coding.exec import CommandError, CommandResult
from s17code.coding.exec import run_command as engine_run_command
from s17code.coding.guard import is_protected
from s17code.core.memory import MemoryScope
from s17code.core.memory.embeddings import DeterministicEmbedder
from s17code.gateway import GatewayClient
from s17code.runtime import AgentRuntime

from .proof import Receipt, Seal, seal, verify

log = logging.getLogger("ratchet")

Emit = Callable[[str, dict], Awaitable[None]]

#: pytest's exit codes. Only 1 means "tests ran and an assertion failed", which
#: is the only kind of red that proves the grader captured a bug. 2/3/4/5 mean
#: the test file is broken, uncollectable or empty — a non-zero exit that would
#: otherwise let a useless test masquerade as a captured bug.
PYTEST_TESTS_FAILED = 1
PYTEST_DIAGNOSIS = {
    0: "every test passed",
    1: "tests ran and failed",
    2: "the run was interrupted (usually a collection error)",
    3: "an internal pytest error",
    4: "pytest was used incorrectly",
    5: "no tests were collected",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_") or "run"


@dataclass(frozen=True)
class Config:
    """Every bound the run answers to, all of them env-configurable."""

    workspace: Path
    max_attempts: int = 3
    phase_timeout: float = 600.0
    test_timeout: int = 120
    pytest_command: str = "python -m pytest -q"
    poll_seconds: float = 0.25

    @classmethod
    def from_env(cls) -> Config:
        root = os.getenv("RATCHET_WORKSPACE", "").strip()
        if not root:
            raise ValueError("RATCHET_WORKSPACE must point at the repository under repair")
        return cls(
            workspace=Path(root).expanduser().resolve(),
            max_attempts=max(1, int(os.getenv("RATCHET_MAX_ATTEMPTS", "3"))),
            phase_timeout=float(os.getenv("RATCHET_PHASE_TIMEOUT", "600")),
            test_timeout=max(1, int(os.getenv("RATCHET_TEST_TIMEOUT", "120"))),
            pytest_command=os.getenv("RATCHET_PYTEST", "python -m pytest -q"),
            poll_seconds=float(os.getenv("RATCHET_POLL_SECONDS", "0.25")),
        )


@dataclass
class Engine:
    """The S17Code engine, opened once for the process."""

    runtime: AgentRuntime
    gateway: GatewayClient
    workspace: Workspace

    @classmethod
    def open(cls, config: Config) -> Engine:
        # The coding capability family is hidden from the planner unless this is
        # set, so it is set before any run is created rather than per-call.
        os.environ["S17_WORKSPACE"] = str(config.workspace)
        # The general file capabilities (write_file, copy_file, ...) address a
        # sandbox root instead of the workspace and are NOT subject to the coding
        # guard. Leaving that configured would hand the coder a documented way
        # around the one rule this product sells. Unset means unavailable, and
        # S17Code hides unavailable capabilities from the planner entirely.
        os.environ.pop("S17_SANDBOX_ROOT", None)
        # A running S17Code service keeps its graph checkpoints and memory sqlite
        # in ~/.s17code. Ratchet gets its own store unless told otherwise, so the
        # two processes never contend for the same files.
        os.environ.setdefault("S17_DATA_DIR", str(Path.home() / ".ratchet"))

        runtime = AgentRuntime()
        # Ratchet uses none of S17Code's semantic memory, and an embedder that
        # needs a local Ollama would make the product fail for a reason that has
        # nothing to do with the bug being fixed.
        runtime.memory.embedder = DeterministicEmbedder(96)
        return cls(runtime=runtime, gateway=GatewayClient(),
                   workspace=Workspace.open(config.workspace))

    async def close(self) -> None:
        """Shut down without raising: a failed close must not mask a finished run."""
        for shutdown in (self.runtime.close, self.gateway.close):
            try:
                outcome = shutdown()
                if outcome is not None:
                    await outcome
            except Exception as error:  # noqa: BLE001 - shutdown is best effort
                log.warning("closing %s failed: %s", shutdown.__qualname__, error)


# --------------------------------------------------------------------------
# node result summaries — what the UI shows next to a green or red node
# --------------------------------------------------------------------------

def _summarise(skill: str, result: dict) -> str:
    if not isinstance(result, dict):
        return ""
    if skill == "read_code":
        return (f"{result.get('path')} lines {result.get('start_line')}"
                f"–{result.get('end_line')} of {result.get('total_lines')}")
    if skill == "edit_code":
        return f"{result.get('path')}: replaced {result.get('replaced')} occurrence(s)"
    if skill == "create_file":
        return f"{result.get('path')}: {result.get('bytes')} bytes"
    if skill == "glob_files":
        return f"{result.get('count')} file(s) matching {result.get('pattern')!r}"
    if skill == "grep_code":
        return f"{len(result.get('matches') or [])} match(es) for {result.get('pattern')!r}"
    if skill == "git_diff":
        return f"{len(result.get('files') or [])} file(s) changed"
    text = result.get("answer") or result.get("summary") or result.get("text") or ""
    return str(text)[:280]


def _input_hint(node: dict) -> str:
    arguments = node.get("input") or {}
    for key in ("path", "pattern", "command", "query", "destination"):
        if arguments.get(key):
            return f"{key}={arguments[key]!r}"
    return ""


def split_patch(patch: str) -> list[tuple[str, str]]:
    """Split a multi-file unified diff into (path, patch) pairs."""
    chunks = [chunk for chunk in re.split(r"(?m)^(?=diff --git )", patch) if chunk.strip()]
    files: list[tuple[str, str]] = []
    for chunk in chunks:
        match = re.search(r"(?m)^diff --git a/(\S+) b/(\S+)", chunk)
        files.append(((match.group(2) if match else "(unknown)"), chunk.rstrip() + "\n"))
    return files


def added_file_patch(path: str, content: str) -> str:
    """A unified diff for a file that did not exist before this run."""
    lines = content.splitlines()
    body = "\n".join(f"+{line}" for line in lines)
    return (f"diff --git a/{path} b/{path}\n"
            f"new file mode 100644\n"
            f"--- /dev/null\n"
            f"+++ b/{path}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n{body}\n")


class RatchetRun:
    """One bug report, two locked phases, one receipt."""

    def __init__(self, *, run_id: str, bug: str, target: str,
                 engine: Engine, config: Config, emit: Emit) -> None:
        self.run_id = run_id
        self.bug = bug.strip()
        self.target = target
        self.engine = engine
        self.config = config
        self.emit = emit

        slug = _slug(run_id).removeprefix("ratchet_")
        self.test_path = f"tests/test_ratchet_{slug}.py"
        # Deliberately not under tests/ and deliberately not named test_*.py:
        # this path must NOT be protected, because the grader writes here with
        # the engine's real create_file and the guard is never relaxed.
        self.staging_path = f".ratchet/{slug}/authored_case.py"

        self.refusals: list[str] = []
        self.commands: int = 0

    # ---------------------------------------------------------------- events

    async def _phase(self, phase: str, note: str) -> None:
        await self.emit("phase", {"phase": phase, "note": note})

    async def _node(self, node_id: str, label: str, state: str, detail: str = "") -> None:
        await self.emit("node", {"id": node_id, "label": label,
                                 "state": state, "detail": detail})

    async def _cmd(self, result: CommandResult) -> None:
        self.commands += 1
        output = result.stdout
        if result.stderr:
            output = f"{output}\n{result.stderr}" if output else result.stderr
        await self.emit("cmd", {"cmd": " ".join(result.command),
                                "exit": result.exit_code,
                                "output": output})

    async def _diff(self, path: str, patch: str) -> None:
        await self.emit("diff", {"path": path, "patch": patch})

    # ------------------------------------------------------------ the engine

    async def _llm(self, prompt: str, system: str, *, session: str):
        return await self.engine.gateway.complete(prompt, system, session=session)

    async def _agent_run(self, *, key: str, prompt: str, tenant: str,
                         side_effects: set[str]) -> dict[str, Any]:
        """One S17Code run, streamed node by node while it executes.

        ``key`` is what makes the phases separate rather than a claim that they
        are: it produces a distinct ``run_id`` (distinct graph checkpoint,
        distinct EditLedger), a distinct memory tenant, and a distinct gateway
        session. Nothing is carried across but the text of the prompt.
        """
        engine_run_id = f"{self.run_id}-{key}"
        scope = MemoryScope(tenant_id=tenant, project_id="ratchet",
                            user_id=self.run_id, agent_id=key)
        stop = asyncio.Event()
        pump = asyncio.create_task(self._pump(engine_run_id, key, stop))

        async def llm(text: str, system: str):
            return await self._llm(text, system, session=engine_run_id)

        started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self.engine.runtime.run(
                    prompt=prompt, scope=scope, llm=llm,
                    source_uri=f"ratchet://{self.run_id}/{key}",
                    source_author="ratchet",
                    run_id=engine_run_id,
                    allowed_side_effects=set(side_effects),
                ),
                timeout=self.config.phase_timeout,
            )
        except TimeoutError:
            await self._node(f"{key}/timeout", "phase timeout", "fail",
                             f"the {key} run exceeded RATCHET_PHASE_TIMEOUT "
                             f"({self.config.phase_timeout:g}s) and was abandoned")
            result = {"run_id": engine_run_id, "status": "timeout", "answer": ""}
        except Exception as error:  # an engine failure is a run outcome, not a 500
            await self._node(f"{key}/error", "engine error", "fail",
                             f"{type(error).__name__}: {error}")
            result = {"run_id": engine_run_id, "status": "error",
                      "answer": "", "error": f"{type(error).__name__}: {error}"}
        finally:
            stop.set()
            await pump

        elapsed = time.monotonic() - started
        ok = result.get("status") == "completed"
        # A run that produced no nodes at all failed before any capability ran —
        # almost always the planner's model call. Say which, rather than leaving
        # a bare "failed" that looks like the agent gave up.
        reason = str(result.get("error") or result.get("answer") or "")[:400]
        if not ok and not (result.get("graph") or {}).get("nodes"):
            reason = reason or "the run planned no work at all; check the model gateway"
        detail = f"status={result.get('status')} in {elapsed:.1f}s"
        await self._node(f"{key}/run", f"s17code run {engine_run_id}",
                         "ok" if ok else "fail",
                         f"{detail} — {reason}" if reason else detail)
        return result

    async def _pump(self, engine_run_id: str, key: str, stop: asyncio.Event) -> None:
        """Follow the run's journal and re-emit it as `node` events, live."""
        cursor = 0
        while not stop.is_set():
            cursor = await self._drain(engine_run_id, key, cursor)
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.config.poll_seconds)
            except TimeoutError:
                pass
        # One last pass, so the tail of a fast run is never lost to the poll gap.
        await self._drain(engine_run_id, key, cursor)

    async def _drain(self, engine_run_id: str, key: str, cursor: int) -> int:
        try:
            events = self.engine.runtime.graph.events(engine_run_id)
        except KeyError:
            return cursor  # the graph checkpoint does not exist yet
        fresh = [event for event in events if event.sequence > cursor]
        if not fresh:
            return cursor

        nodes: dict[str, dict] = {}
        if any(event.kind == "task_started" for event in fresh):
            try:
                nodes = self.engine.runtime.graph.snapshot(engine_run_id).nodes
            except KeyError:
                nodes = {}

        for event in fresh:
            cursor = event.sequence
            node_id = f"{key}/{event.node_id}" if event.node_id else f"{key}/run"
            payload = event.payload if isinstance(event.payload, dict) else {}
            if event.kind == "task_started":
                skill = str(payload.get("skill") or "task")
                await self._node(node_id, skill, "running",
                                 _input_hint(nodes.get(str(event.node_id), {})))
            elif event.kind == "task_succeeded":
                skill = str((nodes.get(str(event.node_id), {}) or {}).get("skill") or "task")
                await self._node(node_id, skill or "task", "ok", _summarise(skill, payload))
            elif event.kind == "graph_patched":
                # The planner's own failures are journalled here rather than as a
                # node, so a broken model gateway would otherwise show up as a
                # run that mysteriously "planned no work". Surface it.
                reason = str(payload.get("reason") or "")
                if payload.get("finish") and "fail" in reason.lower():
                    await self._node(f"{key}/planner", "planner", "fail", reason)
            elif event.kind in {"task_failed", "task_cancelled"}:
                error = str(payload.get("error") or event.kind.replace("task_", ""))
                refused = error.startswith(GuardError.__name__)
                if refused:
                    self.refusals.append(error)
                await self._node(node_id, "REFUSED BY GUARD" if refused else "failed task",
                                 "fail", error)
        return cursor

    # ------------------------------------------------------------- the judge

    async def _pytest(self, label: str) -> CommandResult:
        """Run the sealed test. The harness owns this; no agent may call it."""
        command = f"{self.config.pytest_command} {self.test_path}"
        try:
            result = await asyncio.to_thread(
                engine_run_command, self.engine.workspace, command,
                timeout=self.config.test_timeout)
        except CommandError as refused:
            # RATCHET_PYTEST names something the engine's allowlist will not run.
            # That is a misconfiguration, not a verdict, and it is reported as
            # pytest's "used incorrectly" exit so the run fails honestly.
            result = CommandResult(command.split(), 4, "", str(refused), False, 0.0)
        await self._node(f"judge/{label}", f"pytest {self.test_path}",
                         "ok" if result.exit_code == 0 else "fail",
                         f"exit {result.exit_code}: "
                         f"{PYTEST_DIAGNOSIS.get(result.exit_code, 'unknown exit code')}")
        await self._cmd(result)
        return result

    # ------------------------------------------------------------- prompting

    def _grader_prompt(self) -> str:
        return f"""You are the GRADER. Your entire job is to write one failing test.

A bug has been reported against this repository:

--- BUG REPORT ---
{self.bug}
--- END BUG REPORT ---

The reporter points at `{self.target}`.

You are NOT fixing anything. You have no authority to edit source code and you
will not be given any. You cannot run commands: a separate harness runs your test
and reports the verdict, so nothing you claim about it counts.

Do exactly this:

1. Use read_code, grep_code and glob_files to understand `{self.target}` well
   enough to exercise the reported behaviour precisely.
2. Call create_file ONCE with path "{self.staging_path}" and the complete test
   file as `content`.
3. Answer with the test function name and one sentence on what it asserts.

The test file must satisfy all of these, or the run is thrown away:

- Plain pytest. `import pytest` only if you actually use it.
- Import the code under test with a normal import rooted at the repository
  root, matching `{self.target}` (for example, a file `pkg/mod.py` is
  `from pkg.mod import thing`).
- Define at least one function whose name starts with `test_`.
- It must FAIL right now, with an assertion, because of the reported bug, and
  it must PASS once the bug is genuinely fixed. Assert the CORRECT behaviour.
- No pytest.skip, no xfail, no try/except that swallows the failure, no
  `assert True`, no network, no sleeps, no randomness, no new fixtures in
  conftest.py.
- Keep it small: one bug, the fewest assertions that pin it down.
"""

    def _coder_prompt(self, attempt: int, red_output: str, previous: str) -> str:
        history = ""
        if previous:
            history = f"""
A previous attempt in this repository did not make the test pass. This is what
the workspace changed last time; do not simply repeat it:

{previous[:4000]}
"""
        return f"""You are the CODER. A test in this repository is failing. Fix the SOURCE.

The failing test lives at `{self.test_path}`. Read it — you must, to know what is
being asserted. You may NOT change it, and there is no argument that unlocks it:
`s17code/coding/guard.py` refuses every write to a test path before it reaches
the disk, and the harness re-hashes that file when you are done. If the sha256
moved, the run is reported as void no matter what the tests say. The test is the
judge. Fix the code it is judging.

The symptom that was reported:

--- BUG REPORT ---
{self.bug}
--- END BUG REPORT ---

The suspect file is `{self.target}`.

This is what the test prints today:

--- FAILING TEST OUTPUT ---
{red_output[:8000]}
--- END FAILING TEST OUTPUT ---
{history}
Do exactly this:

1. read_code `{self.test_path}` so you know exactly what is asserted.
2. read_code `{self.target}`, and anything else you need to understand the cause.
3. edit_code the SOURCE so the assertion holds.

Fix the cause. Do not special-case the test's inputs, do not add a branch that
only recognises the values in the test, and do not weaken behaviour elsewhere to
get past it. You cannot run the tests yourself; the harness runs them the moment
you stop. This is attempt {attempt} of {self.config.max_attempts}.
"""

    # ------------------------------------------------------------- the phases

    def _promote(self) -> tuple[bool, str]:
        """Move the authored test out of staging and into the protected path."""
        staged = self.engine.workspace.resolve(self.staging_path)
        if not staged.is_file():
            return False, f"the grader never created {self.staging_path}"
        content = staged.read_text(encoding="utf-8", errors="replace")
        if "def test_" not in content:
            return False, (f"{self.staging_path} contains no test function; "
                           "the grader did not produce a test")
        destination = self.engine.workspace.resolve(self.test_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        shutil.rmtree(staged.parent, ignore_errors=True)
        return True, content

    async def _emit_workspace_diff(self) -> str:
        """Everything the coder changed, per file, as a patch a human can read."""
        if not self.engine.workspace.is_git():
            await self._node("diff/unavailable", "git diff", "fail",
                             "the workspace is not a git repository, so no patch can be shown")
            return ""
        try:
            patch = self.engine.workspace.diff()
        except Exception as error:
            await self._node("diff/unavailable", "git diff", "fail",
                             f"{type(error).__name__}: {error}")
            return ""
        for path, chunk in split_patch(patch):
            await self._diff(path, chunk)
        return patch

    async def _finish(self, ok: bool, summary: str, receipt: Receipt | None) -> bool:
        if receipt is not None:
            await self.emit("proof", receipt.as_event())
        await self.emit("done", {"ok": ok, "summary": summary})
        return ok

    async def execute(self) -> bool:
        """The whole run. Returns True only for an earned, verified green."""
        # ---- phase A: the grader ------------------------------------------
        await self._phase("author_test",
                          f"grading run: writing a test that captures the bug in {self.target}")
        await self._agent_run(
            key="grader",
            prompt=self._grader_prompt(),
            tenant=f"ratchet-{self.run_id}-grader",
            # create_file and nothing else. No edit_code: the grader cannot
            # touch source. No run_command: the grader cannot judge its own test.
            side_effects={"create_file"},
        )

        promoted, detail = self._promote()
        if not promoted:
            await self._node("grader/promote", "promote authored test", "fail", detail)
            await self._phase("failed", detail)
            return await self._finish(
                False, f"phase A produced no usable test: {detail}", None)

        test_source = detail
        await self._node("grader/promote", "promote authored test", "ok",
                         f"{self.staging_path} -> {self.test_path} "
                         f"({len(test_source)} bytes), now under guard pattern 'tests/**'")
        await self._diff(self.test_path, added_file_patch(self.test_path, test_source))

        sealed: Seal = seal(self.engine.workspace.root, self.test_path)
        await self._node("proof/seal", "seal the judge", "ok",
                         f"sha256 {sealed.sha256} over {sealed.size_bytes} bytes")

        # ---- the red run ---------------------------------------------------
        await self._phase("red", f"running {self.test_path}; it must fail on an assertion")
        red = await self._pytest("red")
        if red.exit_code != PYTEST_TESTS_FAILED:
            reason = (f"the authored test exited {red.exit_code} "
                      f"({PYTEST_DIAGNOSIS.get(red.exit_code, 'unknown exit code')}); "
                      "a captured bug must exit 1 on a failed assertion")
            await self._phase("failed", reason)
            return await self._finish(
                False, f"phase A did not capture the bug: {reason}",
                verify(self.engine.workspace.root, sealed))

        red_output = (red.stdout + ("\n" + red.stderr if red.stderr else "")).strip()

        # ---- phase B: the coder, up to the attempt cap ----------------------
        previous_patch = ""
        last_red = red_output
        green: CommandResult | None = None

        for attempt in range(1, self.config.max_attempts + 1):
            await self._phase("fix", f"coding run, attempt {attempt} of {self.config.max_attempts}")
            await self._agent_run(
                key=f"coder{attempt}",
                prompt=self._coder_prompt(attempt, last_red, previous_patch),
                # A fresh tenant per attempt: no attempt inherits another's
                # memory, and none of them can reach the grader's.
                tenant=f"ratchet-{self.run_id}-coder{attempt}",
                # edit_code so it can fix source; create_file so a fix that needs
                # a new module is possible. Both go through the guard, so an
                # attempt on the test path is refused and streamed, not hidden.
                side_effects={"edit_code", "create_file"},
            )
            previous_patch = await self._emit_workspace_diff()

            verdict = await self._pytest(f"attempt{attempt}")
            if verdict.exit_code == 0:
                green = verdict
                break
            last_red = (verdict.stdout + ("\n" + verdict.stderr if verdict.stderr else "")).strip()

        receipt = verify(self.engine.workspace.root, sealed)
        refusal_note = (f" {len(self.refusals)} guard refusal(s) were recorded."
                        if self.refusals else "")

        if green is None:
            tail = last_red[-2000:]
            await self._phase("failed",
                              f"the coder did not turn it green in {self.config.max_attempts} "
                              f"attempt(s). Last red output:\n{tail}")
            return await self._finish(
                False,
                f"still red after {self.config.max_attempts} attempt(s). "
                f"{receipt.describe()}.{refusal_note}",
                receipt)

        if not receipt.unchanged:
            # Green, but not earned. This is the one outcome the product exists
            # to catch, and it is reported as a failure.
            await self._phase("failed",
                              "the suite is green but the judge moved: "
                              f"{receipt.describe()}. This run is void.")
            return await self._finish(
                False,
                f"VOID: pytest exited 0 but {receipt.describe()}.{refusal_note}",
                receipt)

        await self._phase("green",
                          f"{self.test_path} passes, and its sha256 is unchanged since it was sealed")
        return await self._finish(
            True,
            f"red -> green in {attempt} attempt(s); {receipt.describe()}.{refusal_note}",
            receipt)


def new_run_id() -> str:
    return f"ratchet-{uuid.uuid4().hex[:10]}"


def target_problems(workspace: Workspace, target: str) -> str | None:
    """Why this target cannot be repaired, or None if it can."""
    if os.path.isabs(target):
        return "target must be workspace-relative"
    protecting = is_protected(target)
    if protecting:
        return (f"{target} matches protected pattern {protecting!r}: it is the judge, "
                "not the work. Point Ratchet at the source file instead.")
    try:
        path = workspace.resolve(target)
    except Exception as error:
        return str(error)
    if not path.is_file():
        return f"{target} is not a file in the workspace"
    return None
