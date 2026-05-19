from __future__ import annotations

from arga_cli import main


def test_top_level_saved_test_run_accepts_pr_metadata(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(main, "load_api_key", lambda: "arga_test")
    monkeypatch.setattr(main, "_resolve_ttl", lambda client, ttl: ttl)

    def fake_run(self, test_id: str, **kwargs: object) -> dict[str, object]:
        captured["test_id"] = test_id
        captured.update(kwargs)
        return {"id": "test_run_123", "status": "queued", "start_url": "https://app.example.com"}

    monkeypatch.setattr(main.ApiClient, "run_demo_test", fake_run)

    args = main.build_parser().parse_args(
        [
            "tests",
            "run",
            "test_123",
            "--sandbox-id",
            "sandbox_123",
            "--repo",
            "arga-labs/demo",
            "--branch",
            "feature/test",
            "--pr-url",
            "https://github.com/arga-labs/demo/pull/7",
        ]
    )

    assert args.func(args) == 0

    assert captured["test_id"] == "test_123"
    assert captured["sandbox_id"] == "sandbox_123"
    assert captured["repo"] == "arga-labs/demo"
    assert captured["branch"] == "feature/test"
    assert captured["pr_url"] == "https://github.com/arga-labs/demo/pull/7"
    assert captured["trigger_source"] == "pr"
    assert "Run ID: test_run_123" in capsys.readouterr().out


def test_top_level_sandbox_and_twin_run_commands(monkeypatch, capsys) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(main, "load_api_key", lambda: "arga_test")
    monkeypatch.setattr(main, "_resolve_ttl", lambda client, ttl: ttl)

    def fake_sandbox(self, **kwargs: object) -> dict[str, object]:
        calls.append(("sandbox", kwargs))
        return {"sandbox_id": "sandbox_123", "status": "queued", "twins": {}}

    def fake_twin(self, **kwargs: object) -> dict[str, object]:
        calls.append(("twin", kwargs))
        return {"run_id": "twin_run_123", "status": "queued"}

    monkeypatch.setattr(main.ApiClient, "create_sandbox", fake_sandbox)
    monkeypatch.setattr(main.ApiClient, "provision_twins_start", fake_twin)

    sandbox_args = main.build_parser().parse_args(
        [
            "sandbox-runs",
            "create",
            "--repo",
            "arga-labs/demo",
            "--branch",
            "feature/test",
            "--twins",
            "slack,stripe",
        ]
    )
    twin_args = main.build_parser().parse_args(
        ["twin-runs", "create", "--twins", "slack", "--scenario-id", "scenario_123"]
    )

    assert sandbox_args.func(sandbox_args) == 0
    assert twin_args.func(twin_args) == 0

    assert calls[0] == (
        "sandbox",
        {
            "repo": "arga-labs/demo",
            "branch": "feature/test",
            "pr_url": None,
            "scenario_prompt": None,
            "scenario_id": None,
            "twins": ["slack", "stripe"],
            "ttl_minutes": None,
            "env": {},
        },
    )
    assert calls[1][0] == "twin"
    assert calls[1][1]["twins"] == ["slack"]
    assert calls[1][1]["scenario_id"] == "scenario_123"
    assert "Sandbox ID: sandbox_123" in capsys.readouterr().out
