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
