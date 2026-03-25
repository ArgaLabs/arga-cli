from __future__ import annotations

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
