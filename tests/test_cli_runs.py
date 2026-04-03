from __future__ import annotations

import json

from arga_cli import main


def test_runs_list_prints_filtered_table(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_list(self, *, repo: str | None = None, limit: int = 20, offset: int = 0):
        assert repo == "arga-labs/validation-server"
        if offset == 0:
            return {
                "items": [
                    {
                        "run_id": "run_completed",
                        "status": "completed",
                        "repo": "arga-labs/validation-server",
                        "pr_number": 182,
                        "created_at": "2026-03-25T12:30:00Z",
                    },
                    {
                        "run_id": "run_failed",
                        "status": "failed",
                        "repo": "arga-labs/validation-server",
                        "branch": "main",
                        "created_at": "2026-03-25T12:00:00Z",
                    },
                ],
                "limit": limit,
                "offset": offset,
                "has_more": False,
                "total": 2,
            }
        raise AssertionError("Unexpected extra page request")

    monkeypatch.setattr(main.ApiClient, "list_pr_validation_runs", fake_list)

    args = main.build_parser().parse_args(
        ["runs", "list", "--repo", "arga-labs/validation-server", "--status", "failed", "--limit", "20"]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "RUN_ID" in output
    assert "run_failed" in output
    assert "main" in output
    assert "run_completed" not in output


def test_runs_list_running_filter_includes_non_terminal_statuses(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_list(self, *, repo: str | None = None, limit: int = 20, offset: int = 0):
        return {
            "items": [
                {
                    "run_id": "run_queued",
                    "status": "queued",
                    "repo": "arga-labs/validation-server",
                    "branch": "feature/arga",
                    "created_at": "2026-03-25T13:00:00Z",
                },
                {
                    "run_id": "run_completed",
                    "status": "completed",
                    "repo": "arga-labs/validation-server",
                    "branch": "main",
                    "created_at": "2026-03-25T12:00:00Z",
                },
            ],
            "limit": limit,
            "offset": offset,
            "has_more": False,
            "total": 2,
        }

    monkeypatch.setattr(main.ApiClient, "list_pr_validation_runs", fake_list)

    args = main.build_parser().parse_args(["runs", "list", "--status", "running"])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "run_queued" in output
    assert "run_completed" not in output


def test_runs_status_prints_detail_summary(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_get_run(self, run_id: str):
        assert run_id == "run_123"
        return {
            "id": run_id,
            "status": "running",
            "run_type": "pr",
            "mode": "auto_visual",
            "repo_full_name": "arga-labs/validation-server",
            "github_pr_number": 182,
            "commit_sha": "abc123",
            "created_at": "2026-03-25T12:30:00Z",
            "environment_url": "https://preview.example.com",
            "session_id": "session_1",
        }

    monkeypatch.setattr(main.ApiClient, "get_run", fake_get_run)

    args = main.build_parser().parse_args(["runs", "status", "run_123"])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Run ID: run_123" in output
    assert "Status: running" in output
    assert "Repository: arga-labs/validation-server" in output
    assert "PR/Branch: PR #182" in output


def test_runs_list_json_flag(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_list(self, *, repo: str | None = None, limit: int = 20, offset: int = 0):
        return {
            "items": [
                {
                    "run_id": "run_1",
                    "status": "completed",
                    "repo": "arga-labs/validation-server",
                    "pr_number": 182,
                    "created_at": "2026-03-25T12:30:00Z",
                },
                {
                    "run_id": "run_2",
                    "status": "failed",
                    "repo": "arga-labs/validation-server",
                    "branch": "main",
                    "created_at": "2026-03-25T12:00:00Z",
                },
            ],
            "limit": limit,
            "offset": offset,
            "has_more": False,
            "total": 2,
        }

    monkeypatch.setattr(main.ApiClient, "list_pr_validation_runs", fake_list)

    args = main.build_parser().parse_args(["runs", "list", "--json"])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    parsed = json.loads(output)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["run_id"] == "run_1"
    assert parsed[1]["run_id"] == "run_2"


def test_runs_list_json_flag_empty(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_list(self, *, repo: str | None = None, limit: int = 20, offset: int = 0):
        return {"items": [], "limit": limit, "offset": offset, "has_more": False, "total": 0}

    monkeypatch.setattr(main.ApiClient, "list_pr_validation_runs", fake_list)

    args = main.build_parser().parse_args(["runs", "list", "--json"])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert json.loads(output) == []


def test_runs_status_json_flag(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    run_data = {
        "id": "run_123",
        "status": "running",
        "run_type": "pr",
        "mode": "auto_visual",
        "repo_full_name": "arga-labs/validation-server",
        "github_pr_number": 182,
        "commit_sha": "abc123",
        "created_at": "2026-03-25T12:30:00Z",
        "environment_url": "https://preview.example.com",
        "session_id": "session_1",
    }

    def fake_get_run(self, run_id: str):
        return run_data

    monkeypatch.setattr(main.ApiClient, "get_run", fake_get_run)

    args = main.build_parser().parse_args(["runs", "status", "run_123", "--json"])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    parsed = json.loads(output)
    assert parsed == run_data


def test_runs_logs_prints_worker_and_runtime_logs(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_get_logs(self, run_id: str):
        assert run_id == "run_123"
        return {
            "run": {
                "id": run_id,
                "status": "ready",
                "run_type": "twin_quickstart",
                "mode": "staging",
                "repo_full_name": None,
                "commit_sha": None,
                "created_at": "2026-03-25T12:30:00Z",
                "environment_url": "https://preview.example.com",
                "event_log_json": [{"type": "environment_ready"}],
            },
            "worker_logs": [
                {
                    "job_id": "job_1",
                    "job_type": "deploy",
                    "target_role": "warm-vm",
                    "status": "succeeded",
                    "content": "deploy output",
                    "truncated": False,
                    "error": None,
                }
            ],
            "runtime_logs": [
                {
                    "timestamp": "2026-03-25T12:31:00Z",
                    "service_name": "arga-api",
                    "severity": "INFO",
                    "event": "environment_ready",
                    "code": "ok",
                    "request_id": "req_1",
                    "job_id": "job_1",
                    "surface_name": "app",
                    "message": "Environment ready.",
                }
            ],
            "warnings": ["Cloud Logging query was partially truncated."],
        }

    monkeypatch.setattr(main.ApiClient, "get_run_logs", fake_get_logs)

    args = main.build_parser().parse_args(["runs", "logs", "run_123"])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Run ID: run_123" in output
    assert "Worker Logs:" in output
    assert "deploy output" in output
    assert "Runtime Logs:" in output
    assert "Environment ready." in output
    assert "Warnings:" in output


def test_runs_logs_prints_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    payload = {
        "run": {"id": "run_123", "status": "ready"},
        "worker_logs": [],
        "runtime_logs": [],
        "warnings": [],
    }

    monkeypatch.setattr(main.ApiClient, "get_run_logs", lambda self, run_id: payload)

    args = main.build_parser().parse_args(["runs", "logs", "run_123", "--json"])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert json.loads(output) == payload


def test_runs_logs_errors_only_filters_plain_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_get_logs(self, run_id: str):
        assert run_id == "run_123"
        return {
            "run": {
                "id": run_id,
                "status": "ready",
                "run_type": "twin_quickstart",
                "mode": "staging",
                "repo_full_name": None,
                "commit_sha": None,
                "created_at": "2026-03-25T12:30:00Z",
                "environment_url": "https://preview.example.com",
                "event_log_json": [],
            },
            "worker_logs": [
                {
                    "job_id": "job_ok",
                    "job_type": "build",
                    "target_role": "builder",
                    "status": "succeeded",
                    "content": "all good",
                    "truncated": False,
                    "error": None,
                },
                {
                    "job_id": "job_bad",
                    "job_type": "deploy",
                    "target_role": "warm-vm",
                    "status": "failed",
                    "content": "deploy failed output",
                    "truncated": False,
                    "error": None,
                },
            ],
            "runtime_logs": [
                {
                    "timestamp": "2026-03-25T12:31:00Z",
                    "service_name": "arga-api",
                    "severity": "INFO",
                    "event": "environment_ready",
                    "code": None,
                    "request_id": "req_ok",
                    "job_id": None,
                    "surface_name": None,
                    "message": "Environment ready.",
                },
                {
                    "timestamp": "2026-03-25T12:32:00Z",
                    "service_name": "preview-proxy",
                    "severity": "WARNING",
                    "event": "preview.request.finish",
                    "code": None,
                    "request_id": "req_warn",
                    "job_id": None,
                    "surface_name": "slack",
                    "message": "Preview request completed.",
                },
            ],
            "warnings": ["Cloud Logging query was partially truncated."],
        }

    monkeypatch.setattr(main.ApiClient, "get_run_logs", fake_get_logs)

    args = main.build_parser().parse_args(["runs", "logs", "run_123", "--errors-only"])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "job_bad" in output
    assert "deploy failed output" in output
    assert "job_ok" not in output
    assert "all good" not in output
    assert "Preview request completed." in output
    assert "Environment ready." not in output
    assert "Warnings:" in output


def test_runs_logs_errors_only_filters_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    payload = {
        "run": {"id": "run_123", "status": "ready"},
        "worker_logs": [
            {"job_id": "job_ok", "status": "succeeded", "error": None},
            {"job_id": "job_bad", "status": "failed", "error": None},
        ],
        "runtime_logs": [
            {"severity": "INFO", "message": "Environment ready."},
            {"severity": "WARNING", "message": "Preview request completed."},
        ],
        "warnings": ["Cloud Logging query was partially truncated."],
    }

    monkeypatch.setattr(main.ApiClient, "get_run_logs", lambda self, run_id: payload)

    args = main.build_parser().parse_args(["runs", "logs", "run_123", "--json", "--errors-only"])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    parsed = json.loads(output)
    assert parsed["worker_logs"] == [{"job_id": "job_bad", "status": "failed", "error": None}]
    assert parsed["runtime_logs"] == [{"severity": "WARNING", "message": "Preview request completed."}]
    assert parsed["warnings"] == ["Cloud Logging query was partially truncated."]


def test_runs_logs_uses_wizard_session_file_when_run_id_missing(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / main.WIZARD_SESSION_FILE).write_text(json.dumps({"run_id": "run_from_session"}) + "\n")
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_get_logs(self, run_id: str):
        assert run_id == "run_from_session"
        return {
            "run": {"id": run_id, "status": "ready"},
            "worker_logs": [],
            "runtime_logs": [],
            "warnings": [],
        }

    monkeypatch.setattr(main.ApiClient, "get_run_logs", fake_get_logs)

    args = main.build_parser().parse_args(["runs", "logs"])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Run ID: run_from_session" in output


def test_runs_cancel_prints_cancelled_status(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_cancel(self, run_id: str):
        assert run_id == "run_123"
        return {"status": "cancelled"}

    monkeypatch.setattr(main.ApiClient, "cancel_validation_run", fake_cancel)

    args = main.build_parser().parse_args(["runs", "cancel", "run_123"])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Run ID: run_123" in output
    assert "Status: cancelled" in output
