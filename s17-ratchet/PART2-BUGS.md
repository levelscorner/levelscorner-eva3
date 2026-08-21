# Session 17, Part 2 — two real bugs in S17Code

Repository: `https://github.com/theschoolofai/S17Code` (local clone `/Users/level/ws/projects/S17Code`, `15ab9c7`)
Baseline before and after: **484 passed, 1 skipped**. With the new tests and the fix: **488 passed, 1 skipped**.

Neither of these is one the lesson already discloses. Section 15 names four:
the dedupe rule, `lstrip("./")` in the path guard, `git -c` as an allowlisted
escape hatch, and the four ways the browser verification lied. The guard's
`lstrip` is already fixed in the tree (`guard.py:44-49` carries the "NB: not
`lstrip("./")`" comment), and `git -c` is already refused in
`exec.py:115`. Both bugs below are separate holes in the *same two* refusals,
reached by a different door.

The theme is the one the lesson itself sets up: **a refusal that lives in one
capability and not the one beside it is not a refusal.**

---

## Bug 1 — `copy_code_file` writes protected paths, so the agent can delete its own judge

**File:** `s17code/coding/edit.py`, `copy_within_workspace`, line 147 (the function starts at line 131).

**What the code does.** `apply_edit` calls `guard_path(relative, action="edit")` on
its first line. `create_file` calls `guard_path(relative, action="create")` on its
first line. `copy_within_workspace` — the third capability in the same module that
writes bytes to a workspace path — calls `workspace.resolve()` and goes
straight to `shutil.copyfile`. It never calls `guard_path` at all.

**What it should do.** Guard the *destination*. The source needs no guard (reading
is not the concern), but the destination is a write, and `guard.py`'s whole
premise is that writes to `tests/**`, `conftest.py`, `.github/**` and friends are
refused in code rather than asked for in a prompt.

**Why it is reachable, not theoretical.** `copy_within_workspace` is the handler
for the `copy_code_file` capability that the agent is offered by name:

- `s17code/capabilities.py:394` — `Capability("copy_code_file", ...)`, `families=("coding",)`
- `s17code/runtime.py:453` — `"copy_code_file": partial(coding_workers.copy_code_file_worker, ctx)`
- `s17code/workers/coding.py:47` — passes `source`, `destination`, `overwrite` through unchanged

So the model supplies `destination` directly. Two moves, both using capabilities
it already has, destroy the judge:

1. `create_file(path="blank.py", content="")` — not protected, allowed.
2. `copy_code_file(source="blank.py", destination="tests/test_divide.py", overwrite=True)` — allowed.

`overwrite=True` is not even required to do damage: a *new* `conftest.py` in the
workspace root containing `collect_ignore_glob = ['*']` turns the whole suite
green without touching a single test file, and `conftest.py` is in
`DEFAULT_PROTECTED` precisely to stop that.

This is the exact failure `guard.py`'s docstring says it exists to prevent:

> "Given a failing test and an instruction to make the suite green, a model will
> find the cheap route unless something stops it. Delete the test."

Here is the cheap route, run against the unmodified tree:

```
edit_code    -> GuardError: refusing to edit tests/test_divide
create_file  -> GuardError: refusing to create tests/test_divide
copy_code_file -> {'copied': True, 'source': 'blank.py', 'destination': 'tests/test_divide.py', 'bytes': 0}
judge is now: ''
```

Two capabilities refuse. The third does it.

The existing `tests/test_copy_capability.py` covers clobbering, a missing source,
self-copy, and workspace escape on both ends. It never asserts the guard, which
is why the hole survived a green suite.

---

## Bug 2 — `python -cCODE` defeats the "python -c is refused" check

**File:** `s17code/coding/exec.py`, `_check`, lines 102–104.

```python
    for argument in argv[1:]:
        # `python -c "..."` is a shell by another name.
        if program.startswith("python") and argument == "-c":
            raise CommandError("python -c is refused: it is an unbounded shell")
```

**What the code does.** It compares the argument to the literal string `"-c"`.
CPython accepts the flag with its value fused onto it — `python -cprint(1)` is
identical to `python -c "print(1)"` — and a fused token is not equal to `"-c"`,
so the check never fires.

**What it should do.** Refuse any argument on a Python interpreter that *starts
with* `-c`.

**Why the metacharacter screen does not save it.** `SHELL_METACHARACTERS` blocks
`;`, `&&`, `||`, `|`, backtick, `$(`, `>`, `<` and newline. Python needs none of
them: `__import__('os')` and `.` chaining are enough. Against the unmodified tree:

```
plain -c  -> CommandError: python -c is refused: it is an unbounded shell
fused -c  -> exit 0 stderr: ''
wrote /tmp/s17_pwned outside the workspace: uid=501(level) gid=20(staff) groups=20(staff),...
```

The argv used was:

```python
["python3", "-c__import__('pathlib').Path('/tmp/s17_pwned').write_text(__import__('os').popen('id').read())"]
```

That is one call that (a) runs `os.popen`, i.e. an actual shell, inside a module
whose docstring says **"There is no shell to interpret `;`, `&&`, backticks or
`rm -rf ~`, because no shell is ever involved"**, and (b) writes a file outside
the workspace, defeating the `Workspace.resolve` containment that every other
write capability goes through. Once there is a Python interpreter under the
agent's control, every other bound in this module — the allowlist, the git
subcommand list, the output cap — is advisory.

**Second route, same root cause.** `uv` is on `DEFAULT_ALLOWLIST` and
`FORBIDDEN_ARGS` uses the same exact-equality test at line 106
(`if argument in FORBIDDEN_ARGS and program in {"pip", "uv"}`):

```
['uv', 'run', 'python', '-c', 'print(1)'] -> refused: '-c' is refused for uv
['uv', 'run', 'python', '-cprint(1)']     -> ALLOWED exit 0 1
```

The fix covers both, otherwise closing one door leaves the other open.

`tests/test_coding_surface.py:131-133` asserts exactly the two spaced forms and
nothing else, which is why this survived a green suite too.

---

## The test

New file, `tests/test_guard_bypasses.py`:

```python
"""Two ways the coding surface's own refusals can be walked around."""
from __future__ import annotations

import pytest

from s17code.coding.edit import EditLedger, copy_within_workspace, create_file
from s17code.coding.exec import CommandError, run_command
from s17code.coding.guard import GuardError
from s17code.coding.workspace import Workspace


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("S17_WORKSPACE", str(tmp_path))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_bug.py").write_text("def test_bug():\n    assert divide(1, 0) == 0\n")
    return Workspace.from_env(), EditLedger()


def test_copy_may_not_overwrite_a_protected_test_file(ws) -> None:
    """The judge must survive copy_code_file, not just edit_code/create_file."""
    workspace, ledger = ws
    create_file(workspace, ledger, "blank.py", content="")
    with pytest.raises(GuardError):
        copy_within_workspace(workspace, ledger, "blank.py",
                              "tests/test_bug.py", overwrite=True)
    assert "divide" in (workspace.root / "tests" / "test_bug.py").read_text()


def test_copy_may_not_create_a_new_file_under_a_protected_path(ws) -> None:
    workspace, ledger = ws
    create_file(workspace, ledger, "blank.py", content="collect_ignore_glob = ['*']\n")
    with pytest.raises(GuardError):
        copy_within_workspace(workspace, ledger, "blank.py", "conftest.py")


def test_fused_python_dash_c_is_refused(ws) -> None:
    """`python -c` is refused; `python -cCODE` is the same unbounded shell."""
    workspace, _ = ws
    with pytest.raises(CommandError):
        run_command(workspace, ["python3", "-cprint(1)"])


def test_fused_python_dash_c_under_uv_is_refused(ws) -> None:
    workspace, _ = ws
    with pytest.raises(CommandError):
        run_command(workspace, ["uv", "run", "python", "-cprint(1)"])
```

### Before the fix — 4 failed

```
$ .venv/bin/python -m pytest tests/test_guard_bypasses.py -q -p no:randomly
FFFF                                                                     [100%]
=================================== FAILURES ===================================
______________ test_copy_may_not_overwrite_a_protected_test_file _______________

    def test_copy_may_not_overwrite_a_protected_test_file(ws) -> None:
        """The judge must survive copy_code_file, not just edit_code/create_file."""
        workspace, ledger = ws
        create_file(workspace, ledger, "blank.py", content="")
>       with pytest.raises(GuardError):
             ^^^^^^^^^^^^^^^^^^^^^^^^^
E       Failed: DID NOT RAISE GuardError

tests/test_guard_bypasses.py:24: Failed
__________ test_copy_may_not_create_a_new_file_under_a_protected_path __________

    def test_copy_may_not_create_a_new_file_under_a_protected_path(ws) -> None:
        workspace, ledger = ws
        create_file(workspace, ledger, "blank.py", content="collect_ignore_glob = ['*']\n")
>       with pytest.raises(GuardError):
             ^^^^^^^^^^^^^^^^^^^^^^^^^
E       Failed: DID NOT RAISE GuardError

tests/test_guard_bypasses.py:33: Failed
_____________________ test_fused_python_dash_c_is_refused ______________________

    def test_fused_python_dash_c_is_refused(ws) -> None:
        """`python -c` is refused; `python -cCODE` is the same unbounded shell."""
        workspace, _ = ws
>       with pytest.raises(CommandError):
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       Failed: DID NOT RAISE CommandError

tests/test_guard_bypasses.py:40: Failed
_________________ test_fused_python_dash_c_under_uv_is_refused _________________

    def test_fused_python_dash_c_under_uv_is_refused(ws) -> None:
        workspace, _ = ws
>       with pytest.raises(CommandError):
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       Failed: DID NOT RAISE CommandError

tests/test_guard_bypasses.py:46: Failed
=========================== short test summary info ============================
FAILED tests/test_guard_bypasses.py::test_copy_may_not_overwrite_a_protected_test_file
FAILED tests/test_guard_bypasses.py::test_copy_may_not_create_a_new_file_under_a_protected_path
FAILED tests/test_guard_bypasses.py::test_fused_python_dash_c_is_refused - Fa...
FAILED tests/test_guard_bypasses.py::test_fused_python_dash_c_under_uv_is_refused
4 failed in 0.09s
```

All four fail as `DID NOT RAISE`, which is the right reason: the refusal is
absent, not misworded.

---

## The fix

```diff
diff --git a/s17code/coding/edit.py b/s17code/coding/edit.py
index 0b605e1..5230a72 100644
--- a/s17code/coding/edit.py
+++ b/s17code/coding/edit.py
@@ -144,6 +144,9 @@ def copy_within_workspace(workspace, ledger, source: str, destination: str,
     workspace and it still refuses to clobber, because silently replacing a file
     is the thing read-before-edit exists to prevent.
     """
+    # Copying is exempt from read-before-edit, but not from the guard: writing
+    # a protected path is writing it, whatever the bytes came from.
+    guard_path(destination, action="copy to")
     src = workspace.resolve(source)
     dst = workspace.resolve(destination)
     if not src.is_file():
diff --git a/s17code/coding/exec.py b/s17code/coding/exec.py
index ff77488..ab949c5 100644
--- a/s17code/coding/exec.py
+++ b/s17code/coding/exec.py
@@ -99,9 +99,14 @@ def _check(argv: list[str]) -> None:
             f"{program!r} is not an allowed command. Allowed: {', '.join(allowlist())}. "
             "The agent runs the tests; it does not get a shell."
         )
+    # `python -c "..."` is a shell by another name, and so is `-cCODE`: the same
+    # flag with its value fused on, which no separate token check ever sees.
+    runs_python = program.startswith("python") or (
+        program in {"uv", "uvx"}
+        and any(os.path.basename(a).startswith("python") for a in argv[1:])
+    )
     for argument in argv[1:]:
-        # `python -c "..."` is a shell by another name.
-        if program.startswith("python") and argument == "-c":
+        if runs_python and argument.startswith("-c"):
             raise CommandError("python -c is refused: it is an unbounded shell")
         if argument in FORBIDDEN_ARGS and program in {"pip", "uv"}:
             raise CommandError(f"{argument!r} is refused for {program}")
```

`guard_path` is already imported in `edit.py` and `os` is already imported in
`exec.py`, so the diff is three lines plus a comment in one file and six in the
other.

### After the fix — the new tests plus every neighbouring suite

```
$ .venv/bin/python -m pytest tests/test_guard_bypasses.py tests/test_copy_capability.py \
      tests/test_coding_surface.py tests/test_coding_loop_controls.py -q -p no:randomly
...................................................s                     [100%]
51 passed, 1 skipped in 1.13s
```

### After the fix — the whole suite, no regressions

```
$ .venv/bin/python -m pytest -q -p no:randomly
........................................................................ [ 88%]
.........................................................                [100%]
488 passed, 1 skipped, 1 warning in 45.50s
```

484 before, 488 after — the four new tests, nothing else moved. In particular
`tests/test_copy_capability.py` (6 tests) and `tests/test_coding_surface.py`
still pass unchanged: the guard only rejects destinations that were always meant
to be rejected, and the `-c` prefix check does not touch `pytest -c pytest.ini`
or any other allowlisted program.

---

## Notes for the reviewer

- **Scope of the `-c` fix.** `runs_python` deliberately also covers `uv run
  python ...`, because fixing only the `program.startswith("python")` branch
  leaves the `uv` door standing and a partial fix here is worse than none. It
  does not attempt to cover fused *combined* short flags (`python -Ic...`);
  `argument.startswith("-c")` catches the realistic form and the combined form
  is worth a follow-up if the maintainer wants belt and braces.
- **`node` has no equivalent check at all.** `node -e` and `node -p` are
  unbounded in exactly the same way and `node` is on `DEFAULT_ALLOWLIST`. I did
  not fix that here because, unlike `-c`, there is no existing refusal being
  walked around — it is a missing feature rather than a broken check, and it
  belongs in its own change.
- **Working tree.** `/Users/level/ws/projects/S17Code` has been restored to a
  clean `15ab9c7` (`git status --porcelain` is empty, suite back to 484 passed /
  1 skipped). The test file is saved beside this report as
  `test_guard_bypasses.py` and the patch as `s17code-guard-bypasses.diff`; both
  need to be re-applied on the PR branch.
