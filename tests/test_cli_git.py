from __future__ import annotations

import subprocess
import sys

import pytest

from arga_cli import main


def test_commit_command_with_skip_appends_skip_message(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(main.subprocess, "run", fake_run)

    exit_code = main.run_commit_cli(["-m", "feat: add tests", "--skip"])

    assert exit_code == 0
    assert captured["command"] == ["git", "commit", "-m", "feat: add tests", "-m", main.SKIP_TRAILER]
    assert captured["kwargs"] == {"text": True, "input": None, "check": False}


def test_push_command_with_skip_requires_head_commit_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "_get_head_commit_message", lambda: "feat: regular commit")

    with pytest.raises(main.CliError, match="HEAD is not marked to skip Arga validation"):
        main.run_push_cli(["origin", "main", "--skip"])


def test_push_command_with_skip_runs_git_push(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(main, "_get_head_commit_message", lambda: "feat: change\n\n[skip arga]\n")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(main.subprocess, "run", fake_run)

    exit_code = main.run_push_cli(["origin", "main", "--skip"])

    assert exit_code == 0
    assert captured["command"] == ["git", "push", "origin", "main"]
    assert captured["kwargs"] == {"text": True, "input": None, "check": False}


def test_main_dispatches_commit_wrapper_before_argparse(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_commit(argv: list[str]) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(main, "run_commit_cli", fake_commit)
    monkeypatch.setattr(sys, "argv", ["arga", "commit", "-m", "feat: add tests", "--skip"])

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 0
    assert captured["argv"] == ["-m", "feat: add tests", "--skip"]
