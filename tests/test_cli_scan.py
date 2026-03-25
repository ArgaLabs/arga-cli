from __future__ import annotations

import json
import sys

import pytest

from arga_cli import main


def test_scan_start_polls_until_plan_ready_and_auto_approves(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(main.time, "sleep", lambda _: None)

    statuses = iter(
        [
            {"status": "planning"},
            {"status": "awaiting_approval"},
        ]
    )

    def fake_start(self, *, url: str, action_budget: int):
        assert url == "https://demo-app.com"
        assert action_budget == 200
        return {"run_id": "run_scan_123", "status": "planning"}

    def fake_get_run(self, run_id: str):
        assert run_id == "run_scan_123"
        status = next(statuses)
        return {
            "id": run_id,
            "status": status["status"],
            "frontend_url": "https://demo-app.com",
            "mode": "redteam",
        }

    def fake_approve(self, run_id: str):
        assert run_id == "run_scan_123"
        return {"run_id": run_id, "status": "queued"}

    monkeypatch.setattr(main.ApiClient, "start_redteam_scan", fake_start)
    monkeypatch.setattr(main.ApiClient, "get_run", fake_get_run)
    monkeypatch.setattr(main.ApiClient, "approve_redteam_scan", fake_approve)

    exit_code = main.run_scan_cli(["https://demo-app.com"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Starting app scan..." in output
    assert "URL: https://demo-app.com" in output
    assert "Budget: 200" in output
    assert "Run ID: run_scan_123" in output
    assert "Status: queued" in output


def test_scan_status_prints_summary(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_get_run(self, run_id: str):
        assert run_id == "run_scan_123"
        return {
            "id": run_id,
            "status": "running",
            "frontend_url": "https://demo-app.com",
            "mode": "redteam",
            "redteam_report_json": {"anomalies": [{"title": "Issue 1"}, {"title": "Issue 2"}]},
        }

    monkeypatch.setattr(main.ApiClient, "get_run", fake_get_run)

    exit_code = main.run_scan_cli(["status", "run_scan_123"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Run ID: run_scan_123" in output
    assert "Status: running" in output
    assert "Anomalies: 2" in output


def test_scan_report_prints_json(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_report(self, run_id: str):
        assert run_id == "run_scan_123"
        return {"summary": "done", "anomalies": [{"title": "Issue 1"}]}

    monkeypatch.setattr(main.ApiClient, "get_redteam_report", fake_report)

    exit_code = main.run_scan_cli(["report", "run_scan_123"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert json.loads(output) == {"summary": "done", "anomalies": [{"title": "Issue 1"}]}


def test_main_dispatches_scan_wrapper_before_argparse(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_scan(argv: list[str]) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(main, "run_scan_cli", fake_scan)
    monkeypatch.setattr(sys, "argv", ["arga", "scan", "status", "run_scan_123"])

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 0
    assert captured["argv"] == ["status", "run_scan_123"]
