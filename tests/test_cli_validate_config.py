from __future__ import annotations

import sys

from arga_cli import main


def test_validate_install_prints_webhook_details(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_install(self, *, repo: str):
        assert repo == "arga-labs/validation-server"
        return {
            "repo": "arga-labs/validation-server",
            "webhook_id": "12345",
            "enabled": True,
        }

    monkeypatch.setattr(main.ApiClient, "install_github_validation", fake_install)

    exit_code = main.run_validate_cli(["install", "arga-labs/validation-server"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Installed validation webhook." in output
    assert "Repository: arga-labs/validation-server" in output
    assert "Webhook ID: 12345" in output
    assert "Enabled: yes" in output


def test_validate_config_prints_current_settings(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_get(self, *, repo: str):
        assert repo == "arga-labs/validation-server"
        return {
            "repo": "arga-labs/validation-server",
            "installed": True,
            "installation_id": "inst_123",
            "enabled": True,
            "trigger_mode": "branch",
            "branch": "main",
            "default_branch": "main",
            "comment_on_pr": False,
        }

    monkeypatch.setattr(main.ApiClient, "get_github_validation_config", fake_get)

    exit_code = main.run_validate_cli(["config", "arga-labs/validation-server"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Installed: yes" in output
    assert "Trigger Mode: branch" in output
    assert "Branch: main" in output
    assert "PR Comments: off" in output


def test_validate_config_set_merges_unspecified_values(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    captured: dict[str, object] = {}

    def fake_get(self, *, repo: str):
        assert repo == "arga-labs/validation-server"
        return {
            "repo": "arga-labs/validation-server",
            "installed": True,
            "installation_id": "inst_123",
            "enabled": True,
            "trigger_mode": "branch",
            "branch": "main",
            "default_branch": "main",
            "comment_on_pr": False,
        }

    def fake_save(self, *, repo: str, trigger_mode: str, branch: str | None, comment_on_pr: bool):
        captured["repo"] = repo
        captured["trigger_mode"] = trigger_mode
        captured["branch"] = branch
        captured["comment_on_pr"] = comment_on_pr
        return {
            "repo": repo,
            "installed": True,
            "installation_id": "inst_123",
            "enabled": True,
            "trigger_mode": trigger_mode,
            "branch": branch,
            "default_branch": "main",
            "comment_on_pr": comment_on_pr,
        }

    monkeypatch.setattr(main.ApiClient, "get_github_validation_config", fake_get)
    monkeypatch.setattr(main.ApiClient, "save_github_validation_config", fake_save)

    exit_code = main.run_validate_cli(["config", "set", "arga-labs/validation-server", "--comments", "on"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured == {
        "repo": "arga-labs/validation-server",
        "trigger_mode": "branch",
        "branch": "main",
        "comment_on_pr": True,
    }
    assert "Saved validation config." in output
    assert "PR Comments: on" in output


def test_main_dispatches_validate_wrapper_before_argparse(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_validate(argv: list[str]) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(main, "run_validate_cli", fake_validate)
    monkeypatch.setattr(sys, "argv", ["arga", "validate", "config", "arga-labs/validation-server"])

    try:
        main.main()
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("Expected main() to exit")

    assert captured["argv"] == ["config", "arga-labs/validation-server"]


def test_main_supports_global_version_flag(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "_cli_version", lambda: "0.1.3")
    monkeypatch.setattr(sys, "argv", ["arga", "--version"])

    try:
        main.main()
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("Expected main() to exit")

    assert capsys.readouterr().out.strip() == "arga 0.1.3"
