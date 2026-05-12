from __future__ import annotations

import json

from arga_cli import main


def test_start_pr_run_posts_to_new_endpoint(monkeypatch) -> None:
    client = main.ApiClient("https://api.argalabs.com", api_key="arga_api_key")
    captured: dict[str, object] = {}

    class FakeStream:
        status_code = 200
        is_success = True
        headers = {"X-Run-Id": "run_123", "X-Session-Id": "session_123"}

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def iter_text(self):
            yield "data: {}\n\n"

    def fake_stream(method: str, url: str, *, json: dict[str, object], headers: dict[str, str], timeout: float):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeStream()

    monkeypatch.setattr(client._client, "stream", fake_stream)
    try:
        payload = client.start_pr_run(
            repo="arga-labs/validation-server",
            pr_url="https://github.com/arga-labs/validation-server/pull/298",
            context_notes="focus blocks",
            twins=["slack"],
        )
    finally:
        client.close()

    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.argalabs.com/validate/pr-run"
    assert captured["json"] == {
        "repo": "arga-labs/validation-server",
        "run_type": "pr_run",
        "pr_url": "https://github.com/arga-labs/validation-server/pull/298",
        "context_notes": "focus blocks",
        "twins": ["slack"],
    }
    assert payload == {"run_id": "run_123", "session_id": "session_123", "status": "generating_story"}


def test_test_runner_tests_run_uses_saved_test_endpoint(monkeypatch, capsys) -> None:
    from arga_cli.wizard import provision

    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "get_me", lambda self: {"billing_plan": "team"})
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(
        provision, "provision_twins", lambda *args, **kwargs: {"run_id": "provision_1", "status": "ready"}
    )
    monkeypatch.setattr("builtins.input", lambda: "")
    captured: dict[str, object] = {}

    def fake_run(
        self,
        test_id: str,
        *,
        start_url: str | None = None,
        prompt: str | None = None,
        twins: list[str] | None = None,
        ttl_minutes: int | None = None,
        session_id: str | None = None,
    ):
        captured.update(
            {
                "test_id": test_id,
                "start_url": start_url,
                "prompt": prompt,
                "twins": twins,
                "ttl_minutes": ttl_minutes,
                "session_id": session_id,
            }
        )
        return {"id": "demo_run_1", "status": "queued", "start_url": start_url}

    monkeypatch.setattr(main.ApiClient, "run_demo_test", fake_run)

    args = main.build_parser().parse_args(
        [
            "test-runner",
            "tests",
            "run",
            "test_123",
            "--url",
            "https://preview.example.com",
            "--twins",
            "slack,jira",
            "--ttl",
            "60",
        ]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured == {
        "test_id": "test_123",
        "start_url": "https://preview.example.com",
        "prompt": None,
        "twins": ["slack", "jira"],
        "ttl_minutes": 60,
        "session_id": None,
    }
    assert "Saved test run started." in output
    assert "Run ID: demo_run_1" in output


def test_config_validate_rejects_ambiguous_assertion(tmp_path, capsys) -> None:
    config_path = tmp_path / "test_config.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "steps": [
                    {
                        "id": "assert_1",
                        "action": "expect",
                        "expect": {"type": "text"},
                    }
                ],
            }
        )
    )

    args = main.build_parser().parse_args(["test-runner", "tests", "config", "validate", "--file", str(config_path)])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "expect.contains is required" in output


def test_test_runner_runs_url_accepts_test_config(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "get_me", lambda self: {"billing_plan": "team"})
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    captured: dict[str, object] = {}

    def fake_create(self, *, prompt: str, start_url: str | None = None, test_config: dict[str, object] | None = None):
        captured["prompt"] = prompt
        captured["start_url"] = start_url
        captured["test_config"] = test_config
        return {"id": "demo_run_config", "status": "queued"}

    monkeypatch.setattr(main.ApiClient, "create_demo_run", fake_create)
    config_path = tmp_path / "test_config.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "prompt": "Run checkout",
                "starting_url": "https://example.com",
                "steps": [{"id": "step_1", "action": "goto", "value": "https://example.com"}],
            }
        )
    )

    args = main.build_parser().parse_args(["test-runner", "runs", "url", "--test-config", str(config_path)])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["prompt"] == "Run checkout"
    assert captured["start_url"] == "https://example.com"
    assert isinstance(captured["test_config"], dict)
    assert "Run ID: demo_run_config" in output


def test_previews_sandbox_run_uses_agent_run(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    captured: dict[str, object] = {}

    def fake_start_pr_run(self, **kwargs: object):
        captured.update(kwargs)
        return {"run_id": "run_sandbox", "status": "generating_story", "session_id": "session_1"}

    monkeypatch.setattr(main.ApiClient, "start_pr_run", fake_start_pr_run)

    args = main.build_parser().parse_args(
        [
            "previews",
            "sandboxes",
            "run",
            "--repo",
            "arga-labs/app",
            "--branch",
            "feature/demo",
            "--twins",
            "slack",
        ]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["repo"] == "arga-labs/app"
    assert captured["branch"] == "feature/demo"
    assert captured["twins"] == ["slack"]
    assert captured["run_type"] == "agent_run"
    assert "Sandbox preview started." in output


def test_twins_provision_accepts_linear(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(main, "_resolve_ttl", lambda client, ttl: ttl)
    captured: dict[str, object] = {}

    def fake_provision(self, *, twins: list[str], ttl_minutes: int, scenario_prompt: str | None = None):
        captured.update({"twins": twins, "ttl_minutes": ttl_minutes, "scenario_prompt": scenario_prompt})
        return {"run_id": "linear_run", "status": "queued"}

    monkeypatch.setattr(main.ApiClient, "provision_twins_start", fake_provision)

    args = main.build_parser().parse_args(
        [
            "previews",
            "twins",
            "provision",
            "--twins",
            "linear",
            "--ttl",
            "30",
            "--scenario-prompt",
            "seed Linear issues and project updates",
        ]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured == {
        "twins": ["linear"],
        "ttl_minutes": 30,
        "scenario_prompt": "seed Linear issues and project updates",
    }
    assert "Twin provisioning started." in output
    assert "Run ID: linear_run" in output


def test_twins_provision_accepts_gitlab(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(main, "_resolve_ttl", lambda client, ttl: ttl)
    captured: dict[str, object] = {}

    def fake_provision(self, *, twins: list[str], ttl_minutes: int, scenario_prompt: str | None = None):
        captured.update({"twins": twins, "ttl_minutes": ttl_minutes, "scenario_prompt": scenario_prompt})
        return {"run_id": "gitlab_run", "status": "queued"}

    monkeypatch.setattr(main.ApiClient, "provision_twins_start", fake_provision)

    args = main.build_parser().parse_args(
        [
            "previews",
            "twins",
            "provision",
            "--twins",
            "gitlab",
            "--ttl",
            "30",
            "--scenario-prompt",
            "seed GitLab projects and merge requests",
        ]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured == {
        "twins": ["gitlab"],
        "ttl_minutes": 30,
        "scenario_prompt": "seed GitLab projects and merge requests",
    }
    assert "Twin provisioning started." in output
    assert "Run ID: gitlab_run" in output


def test_twins_reset_hits_api(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    captured: dict[str, object] = {}

    def fake_reset(self, run_id: str):
        captured["run_id"] = run_id
        return {
            "run_id": run_id,
            "status": "reset_complete",
            "baseline_kind": "empty",
            "factory_reset": {},
            "seed_results": {},
        }

    monkeypatch.setattr(main.ApiClient, "reset_twins", fake_reset)

    args = main.build_parser().parse_args(["previews", "twins", "reset", "run_xyz"])
    exit_code = args.func(args)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert captured["run_id"] == "run_xyz"
    assert "reset_complete" in out


def test_twins_mcp_config_prints_capable_twin_config(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_status(self, run_id: str):
        return {
            "run_id": run_id,
            "status": "ready",
            "twins": {
                "slack": {
                    "mcp_url": "https://pub-r1--slack.sandbox.argalabs.com/mcp",
                    "mcp": {"url": "https://pub-r1--slack.sandbox.argalabs.com/mcp"},
                },
                "linear": {},
            },
        }

    monkeypatch.setattr(main.ApiClient, "get_twin_provision_status", fake_status)

    args = main.build_parser().parse_args(
        ["previews", "twins", "mcp-config", "run_xyz", "--twin", "slack", "--token", "xoxp-test"]
    )
    exit_code = args.func(args)
    out = capsys.readouterr().out

    assert exit_code == 0
    payload = json.loads(out)
    assert payload["mcpServers"]["arga-twin-slack"]["url"] == "https://pub-r1--slack.sandbox.argalabs.com/mcp"
    assert payload["mcpServers"]["arga-twin-slack"]["headers"]["Authorization"] == "Bearer xoxp-test"


def test_twins_mcp_config_install_merges_detected_targets(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    (tmp_path / ".cursor").mkdir()
    from arga_cli import mcp

    install_from_config = mcp.install_mcp_configuration_from_config

    def fake_status(self, run_id: str):
        return {
            "run_id": run_id,
            "status": "ready",
            "twins": {
                "gitlab": {
                    "mcp_url": "https://pub-r1--gitlab.sandbox.argalabs.com/api/v4/mcp",
                }
            },
        }

    def fake_install(config):
        return install_from_config(config, home=tmp_path, echo=lambda _line: None)

    monkeypatch.setattr(main.ApiClient, "get_twin_provision_status", fake_status)
    monkeypatch.setattr("arga_cli.mcp.install_mcp_configuration_from_config", fake_install)

    args = main.build_parser().parse_args(["previews", "twins", "mcp-config", "run_xyz", "--install"])
    exit_code = args.func(args)

    assert exit_code == 0
    installed = json.loads((tmp_path / ".cursor" / "mcp.json").read_text())
    assert installed["mcpServers"]["arga-twin-gitlab"]["url"].endswith("/api/v4/mcp")
