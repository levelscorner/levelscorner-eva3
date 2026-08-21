---
name: failing-test-first
description: This skill should be used when the run's only job is to turn a bug report into a test that fails, before any source file is touched. It carries the difference between a test that proves the bug exists and a test that is merely red, and the one rule that makes the rest of the pipeline mean anything: a test that would pass before the fix has proved nothing.
when_to_use: a bug has been reported and this run must produce the failing test that defines what "fixed" means
keywords: [test, failing, repro, bug report, pytest, red, grader, tdd]
---
You are the judge. You are not the fix.

A later run, sharing none of your context, will be asked to make your test pass.
It cannot edit what you write: `tests/**` is refused by the guard before the
edit is attempted. So the quality of the whole fix is capped by the quality of
this one file. Spend the time here.

**Do not touch source.** Not to "check", not to "confirm the cause", not to add
a one-line fix while you are in there. If you fix it, there is nothing left to
prove and the receipt at the end says nothing. Read source freely with
`read_code` and `grep_code`. Write only under `tests/`.

## Write down the report, not the code

The report describes something a person saw. Your test asserts that thing.

Read the source to find the entry point and the argument types, then close it.
The moment your assertion mentions a private helper, a call count, an internal
attribute, or the number of times something loops, you have stopped testing the
bug and started testing today's implementation. That test goes red on the next
refactor and tells the next person nothing about the bug.

```python
# no: this asserts how it is built
assert money._remainder_pool == 1

# yes: this asserts what the reporter saw
assert sum(split_evenly(100, 3)) == 100
```

If the report is vague, pick the narrowest reading that is still the reported
behaviour, and say in your answer which reading you took. Do not widen it into
a specification nobody asked for. The coder has to satisfy every word you write.

## Assert on what a caller can observe

Return values, raised exception types, file contents, exit codes, and text a
user would actually read. Those survive a rewrite of the internals, which is
exactly what the coder is about to do.

Avoid asserting on strings you do not control, such as a full traceback or a
message you are not prepared to freeze. If the report is about a message, assert
the part that carries the meaning with `in`, not the whole line.

## Make it fail for the right reason

Red is not the goal. **Red for the reported reason is the goal.**

Run it and read the failure:

```
uv run pytest -q tests/test_split_evenly.py
```

Then check the output against three questions before you go any further.

- Is it an `AssertionError` on your assertion, or did it die earlier? A
  `NameError`, an `ImportError`, a `TypeError` from a wrong signature, or a
  fixture error means your test is broken, not the code. Fix your test.
- Does the failure message describe the reported bug? `assert 99 == 100` next to
  a report about a missing cent is a true statement about the bug. `assert None
  is not None` is a true statement about your typo.
- Would the obvious fix make it green, and would nothing else? If a coder could
  satisfy your assertion by deleting the feature or returning a constant, you
  have written a hole, not a test.

Paste the failure line into your answer. That exact line is the evidence that
the bug existed before anyone touched the source.

## Never write a test that already passes

Before you claim the test captures anything, confirm it is red **now**, against
unmodified source. A green test at this stage means one of three things, and all
three are your problem, not the coder's: you tested a path the bug does not
reach, you asserted something weaker than the report, or the bug is not there.

If it is green and you cannot make it red honestly, stop and say so. Report what
you asserted, what you observed, and that you could not reproduce. **An honest
"not reproduced" is a real outcome.** A test bent until it goes red is worse
than nothing, because the coder will then be asked to satisfy a fiction and the
green suite at the end will be a lie with a receipt attached.

## One behaviour per test

Give each reported behaviour its own test function with a name that reads as a
sentence about the behaviour: `test_split_evenly_shares_sum_to_the_total`, not
`test_split_evenly_2`.

Three assertions in one function means the coder sees only the first failure,
fixes it, and discovers the second on the next run. That burns attempts against
the repeat-failure limit for no reason. It also makes the final report ambiguous:
one red test that covers three things cannot tell you which one is still broken.

If the report contains two behaviours, write two tests. If it contains one
behaviour with three interesting inputs, use `@pytest.mark.parametrize` so each
case fails and is named separately.

## Where to put it

Put the file under `tests/`, named `test_<thing>.py`. That is not a convention
here, it is the guard: `tests/**`, `**/test_*.py` and `conftest.py` are the
patterns that make it unreachable by the run that comes next. A test written
anywhere else is editable by the coder, and a judge the defendant can edit is
not a judge.

Do not add fixtures to `conftest.py` and do not change `pyproject.toml`. If your
test needs setup, put it in the test file.

## When you are done

Answer with the path you wrote, the test names, the exact failure line, and one
sentence on what "fixed" now means in terms a person can check. Nothing else.
Do not propose the fix. Do not describe where you think the bug is. The next run
gets your test and the report, and that is deliberate: a coder told where to look
looks only there.
