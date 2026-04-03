from __future__ import annotations

import json

from arga_cli import main


def test_validate_pr_command_prints_run_id(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")

    def fake_start(self, *, repo: str, pr_number: int):
        assert repo == "arga-labs/validation-server"
        assert pr_number == 182
        return {"run_id": "run_83921", "status": "queued"}

    monkeypatch.setattr(main.ApiClient, "start_pr_validation", fake_start)
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    args = main.build_parser().parse_args(
        ["validate", "pr", "--repo", "arga-labs/validation-server", "--pr", "182"]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Starting PR validation..." in output
    assert "Repository: arga-labs/validation-server" in output
    assert "PR: #182" in output
    assert "Validation run started." in output
    assert "Run ID: run_83921" in output
    assert "Status: queued" in output


def test_validate_pr_json_flag(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")

    def fake_start(self, *, repo: str, pr_number: int):
        return {"run_id": "run_83921", "status": "queued"}

    monkeypatch.setattr(main.ApiClient, "start_pr_validation", fake_start)
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    args = main.build_parser().parse_args(
        ["validate", "pr", "--repo", "arga-labs/validation-server", "--pr", "182", "--json"]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    parsed = json.loads(output)
    assert parsed == {"run_id": "run_83921", "status": "queued"}
