from __future__ import annotations

import json

import pytest

from arga_cli import main


def test_twins_provision_wait_polls_until_ready_and_prints_env(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(main, "_resolve_ttl", lambda client, ttl: ttl)
    monkeypatch.setattr(main.time, "sleep", lambda _seconds: None)

    status_calls: list[str] = []

    def fake_start(self, **kwargs):
        assert kwargs == {
            "twins": ["slack", "box"],
            "ttl_minutes": 30,
            "scenario_prompt": None,
            "scenario_id": None,
            "public": True,
        }
        return {"run_id": "run_wait", "status": "queued"}

    def fake_status(self, run_id: str):
        status_calls.append(run_id)
        if len(status_calls) == 1:
            return {"run_id": run_id, "status": "provisioning", "twins": {}}
        return {
            "run_id": run_id,
            "status": "ready",
            "twins": {
                "slack": {
                    "label": "Slack",
                    "base_url": "https://pub-run--slack.sandbox.argalabs.com",
                    "env_vars": {"SLACK_API_URL": "https://pub-run--slack.sandbox.argalabs.com/api"},
                }
            },
        }

    monkeypatch.setattr(main.ApiClient, "provision_twins_start", fake_start)
    monkeypatch.setattr(main.ApiClient, "get_twin_provision_status", fake_status)

    args = main.build_parser().parse_args(
        ["previews", "twins", "provision", "--twins", "slack,box", "--ttl", "30", "--wait"]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert status_calls == ["run_wait", "run_wait"]
    assert "Status: ready" in output
    assert "SLACK_API_URL=https://pub-run--slack.sandbox.argalabs.com/api" in output


def test_twins_provision_wait_timeout_returns_last_status_without_hanging(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(main, "_resolve_ttl", lambda client, ttl: ttl)
    monkeypatch.setattr(main.time, "sleep", lambda _seconds: None)

    ticks = iter([0.0, 0.5, 1.1])
    monkeypatch.setattr(main.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(
        main.ApiClient,
        "provision_twins_start",
        lambda self, **_kwargs: {"run_id": "run_timeout", "status": "queued"},
    )
    monkeypatch.setattr(
        main.ApiClient,
        "get_twin_provision_status",
        lambda self, run_id: {"run_id": run_id, "status": "provisioning"},
    )

    args = main.build_parser().parse_args(
        ["previews", "twins", "provision", "--twins", "slack", "--ttl", "30", "--wait", "--timeout", "1"]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Run ID: run_timeout" in output
    assert "Status: provisioning" in output


def test_twins_provision_rejects_empty_twin_list(monkeypatch) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")

    args = main.build_parser().parse_args(["previews", "twins", "provision", "--twins", " , "])

    with pytest.raises(main.CliError, match="at least one twin"):
        args.func(args)


def test_twins_list_json_keeps_machine_readable_catalog_shape(monkeypatch, capsys) -> None:
    catalog = [
        {"name": "slack", "label": "Slack", "kind": "frontend", "show_in_ui": True},
        {"name": "postgres", "label": "Postgres", "kind": "infra", "show_in_ui": False},
    ]
    monkeypatch.setattr(
        main,
        "load_api_key",
        lambda: (_ for _ in ()).throw(AssertionError("auth not required")),
    )
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(main.ApiClient, "list_twins", lambda self: catalog)

    args = main.build_parser().parse_args(["previews", "twins", "list", "--json"])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert json.loads(output) == catalog


def test_twins_reset_calls_validation_server_reset_endpoint(monkeypatch, capsys) -> None:
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_reset(self, run_id: str):
        captured.append((self._api_url, run_id))
        return {"run_id": run_id, "status": "reset_complete", "baseline_kind": "seed"}

    monkeypatch.setattr(main.ApiClient, "reset_twins", fake_reset)

    top_level_args = main.build_parser().parse_args(["twin-runs", "reset", "run_reset"])
    legacy_args = main.build_parser().parse_args(["previews", "twins", "reset", "run_legacy", "--json"])

    assert top_level_args.func(top_level_args) == 0
    top_level_output = capsys.readouterr().out
    assert "Run ID: run_reset" in top_level_output
    assert "Baseline: seed" in top_level_output

    assert legacy_args.func(legacy_args) == 0
    legacy_output = capsys.readouterr().out
    assert json.loads(legacy_output)["run_id"] == "run_legacy"
    assert captured == [
        ("https://api.argalabs.com", "run_reset"),
        ("https://api.argalabs.com", "run_legacy"),
    ]


def test_api_client_resets_twins_via_supported_validation_endpoint(monkeypatch) -> None:
    client = main.ApiClient("https://api.argalabs.com", api_key="arga_api_key")
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        is_success = True

        def json(self):
            return {"run_id": "run_reset", "status": "reset_complete"}

    def fake_post(url: str, *, headers: dict[str, str]):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(client._client, "post", fake_post)
    try:
        result = client.reset_twins("run_reset")
    finally:
        client.close()

    assert result["status"] == "reset_complete"
    assert captured == {
        "url": "https://api.argalabs.com/validate/twins/provision/run_reset/reset",
        "headers": {"Authorization": "Bearer arga_api_key"},
    }


def test_sandbox_run_with_pr_url_twins_scenario_and_json_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(main, "_resolve_ttl", lambda client, ttl: ttl)
    captured: dict[str, object] = {}

    def fake_create_sandbox(self, **kwargs):
        captured.update(kwargs)
        return {"sandbox_id": "sandbox_pr", "status": "queued", "twins": {"slack": {"status": "queued"}}}

    monkeypatch.setattr(main.ApiClient, "create_sandbox", fake_create_sandbox)

    args = main.build_parser().parse_args(
        [
            "previews",
            "sandboxes",
            "run",
            "--repo",
            "arga-labs/app",
            "--pr-url",
            "https://github.com/arga-labs/app/pull/42",
            "--twins",
            "slack,github",
            "--scenario-id",
            "scenario_pr",
            "--ttl",
            "75",
            "--json",
        ]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured == {
        "repo": "arga-labs/app",
        "branch": None,
        "pr_url": "https://github.com/arga-labs/app/pull/42",
        "scenario_prompt": None,
        "scenario_id": "scenario_pr",
        "twins": ["slack", "github"],
        "ttl_minutes": 75,
        "env": {},
        "app_command": None,
    }
    assert json.loads(output)["sandbox_id"] == "sandbox_pr"


def test_scenario_import_and_export_round_trip_payloads(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    captured_create: dict[str, object] = {}

    scenario_payload = {
        "name": "Support backlog",
        "prompt": "Seed Slack and Jira",
        "description": "Queue with escalations",
        "twins": ["slack", "jira"],
        "seed_config": {"slack": {"channels": [{"name": "support"}]}},
        "tags": ["smoke"],
    }
    import_path = tmp_path / "scenario.json"
    import_path.write_text(json.dumps(scenario_payload), encoding="utf-8")

    def fake_create_scenario(self, **kwargs):
        captured_create.update(kwargs)
        return {"id": "scenario_imported", **scenario_payload}

    monkeypatch.setattr(main.ApiClient, "create_scenario", fake_create_scenario)

    import_args = main.build_parser().parse_args(
        ["test-runner", "scenarios", "import", "--file", str(import_path), "--json"]
    )
    import_exit = import_args.func(import_args)
    imported = json.loads(capsys.readouterr().out)

    assert import_exit == 0
    assert imported["id"] == "scenario_imported"
    assert captured_create == {
        "name": "Support backlog",
        "prompt": "Seed Slack and Jira",
        "description": "Queue with escalations",
        "twins": ["slack", "jira"],
        "seed_config": {"slack": {"channels": [{"name": "support"}]}},
        "tags": ["smoke"],
    }

    monkeypatch.setattr(
        main.ApiClient,
        "get_scenario",
        lambda self, scenario_id: {"id": scenario_id, **scenario_payload},
    )
    export_path = tmp_path / "exported.json"
    export_args = main.build_parser().parse_args(
        ["test-runner", "scenarios", "export", "scenario_imported", "--output", str(export_path)]
    )
    export_exit = export_args.func(export_args)

    assert export_exit == 0
    assert json.loads(export_path.read_text(encoding="utf-8"))["twins"] == ["slack", "jira"]
