"""The receipt.

A ratchet turns one way only. The claim Ratchet makes is not "the agent says it
fixed it" but "the suite went from red to green while the thing that judged it
did not move". That claim is worth exactly one sha256.

The test file is hashed the moment it lands in ``tests/`` and hashed again after
the coder has finished. Same digest means the green run was earned: the judge the
red run failed against is byte-for-byte the judge the green run passed. A
different digest means the run is void, whatever the exit code said.

Nothing here trusts the agent, the planner, or the guard. ``s17code/coding/guard.py``
is what *prevents* the edit; this module is what *proves* no edit happened. Those
are different jobs and a product that only does the first one is asking to be
believed.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

_CHUNK = 1 << 16

#: Stand-in digest for a file that is not there any more. A coder that deletes
#: the test rather than editing it has still moved the judge, and this is how the
#: receipt says so instead of raising and losing the run.
ABSENT = "absent"


def sha256_file(path: Path) -> str:
    """Hex sha256 of a file's bytes, or :data:`ABSENT` if it is gone."""
    if not path.is_file():
        return ABSENT
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class Seal:
    """The judge, as it stood the moment it was written."""

    test_path: str
    sha256: str
    size_bytes: int

    @property
    def exists(self) -> bool:
        return self.sha256 != ABSENT


def seal(workspace_root: Path, test_path: str) -> Seal:
    """Hash the authored test the instant it exists, before any coder runs."""
    path = Path(workspace_root) / test_path
    digest = sha256_file(path)
    size = path.stat().st_size if path.is_file() else 0
    return Seal(test_path=test_path, sha256=digest, size_bytes=size)


@dataclass(frozen=True)
class Receipt:
    """What the run is willing to be checked on."""

    test_path: str
    sha256_before: str
    sha256_after: str

    @property
    def unchanged(self) -> bool:
        # An absent file is never "unchanged", even against an absent baseline:
        # a receipt for a judge that does not exist proves nothing.
        if self.sha256_after == ABSENT or self.sha256_before == ABSENT:
            return False
        return self.sha256_before == self.sha256_after

    def as_event(self) -> dict:
        """Exactly the payload of the ``proof`` SSE event, and nothing extra."""
        return {
            "testPath": self.test_path,
            "sha256Before": self.sha256_before,
            "sha256After": self.sha256_after,
            "unchanged": self.unchanged,
        }

    def describe(self) -> str:
        if self.unchanged:
            return f"test file unchanged (sha256 {self.sha256_before[:12]}…)"
        if self.sha256_after == ABSENT:
            return "the test file was DELETED during the fix phase"
        if self.sha256_before == ABSENT:
            return "no test file was ever sealed, so there is nothing to prove"
        return (f"the test file CHANGED during the fix phase "
                f"({self.sha256_before[:12]}… -> {self.sha256_after[:12]}…)")


def verify(workspace_root: Path, sealed: Seal) -> Receipt:
    """Re-hash the sealed test and produce the receipt."""
    after = sha256_file(Path(workspace_root) / sealed.test_path)
    return Receipt(test_path=sealed.test_path,
                   sha256_before=sealed.sha256,
                   sha256_after=after)
