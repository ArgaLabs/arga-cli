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


def test_preview_api_methods_use_supported_validation_server_routes(monkeypatch) -> None:
    client = main.ApiClient("https://api.argalabs.com", api_key="arga_api_key")
    captured: list[tuple[str, str, dict[str, object] | None]] = []

    class FakeResponse:
        def __init__(self, payload: object):
            self._payload = payload
            self.status_code = 200
            self.is_success = True

        def json(self):
            return self._payload

    def fake_get(url: str, *, headers: dict[str, str], params: dict[str, object] | None = None):
        captured.append(("GET", url, params))
        payload: object = [{"name": "linear", "label": "Linear", "kind": "backend", "show_in_ui": True}]
        if url.endswith("/status"):
            payload = {"run_id": "run_123", "status": "ready"}
        elif "/sandboxes/" in url and url.endswith("/logs"):
            payload = {"sandbox_id": "sandbox_123", "logs": []}
        elif "/sandboxes/" in url:
            payload = {"sandbox_id": "sandbox_123", "status": "ready", "twins": {}}
        return FakeResponse(payload)

    def fake_delete(url: str, *, headers: dict[str, str]):
        captured.append(("DELETE", url, None))
        return FakeResponse({"sandbox_id": "sandbox_123", "status": "deleted"})

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, object] | None = None):
        captured.append(("POST", url, json))
        if url.endswith("/sandboxes"):
            return FakeResponse({"sandbox_id": "sandbox_123", "status": "queued", "twins": {}})
        return FakeResponse({"status": "ok", "run_id": "run_123", "ttl_minutes": 75, "is_public": False})

    monkeypatch.setattr(client._client, "get", fake_get)
    monkeypatch.setattr(client._client, "delete", fake_delete)
    monkeypatch.setattr(client._client, "post", fake_post)
    try:
        client.create_sandbox(
            repo="arga-labs/app",
            branch="feature/demo",
            twins=["slack"],
            scenario_id="scenario_123",
            ttl_minutes=90,
            env={"FEATURE_FLAG": "on"},
        )
        client.get_sandbox("sandbox_123")
        client.get_sandbox_logs("sandbox_123")
        client.delete_sandbox("sandbox_123")
        client.list_twins()
        client.provision_twins_start(
            twins=["linear"],
            ttl_minutes=75,
            scenario_prompt="seed",
            scenario_id="scenario_123",
            public=False,
        )
        client.get_twin_provision_status("run_123")
        client.extend_twins("run_123", ttl_minutes=75)
        client.teardown_twins("run_123")
        client.lock_twins("run_123")
    finally:
        client.close()

    assert captured == [
        (
            "POST",
            "https://api.argalabs.com/sandboxes",
            {
                "repo": "arga-labs/app",
                "branch": "feature/demo",
                "twins": ["slack"],
                "scenario_id": "scenario_123",
                "ttl_minutes": 90,
                "env": {"FEATURE_FLAG": "on"},
            },
        ),
        ("GET", "https://api.argalabs.com/sandboxes/sandbox_123", None),
        ("GET", "https://api.argalabs.com/sandboxes/sandbox_123/logs", None),
        ("DELETE", "https://api.argalabs.com/sandboxes/sandbox_123", None),
        ("GET", "https://api.argalabs.com/validate/twins", None),
        (
            "POST",
            "https://api.argalabs.com/validate/twins/provision",
            {
                "twins": ["linear"],
                "ttl_minutes": 75,
                "scenario": "quickstart",
                "scenario_prompt": "seed",
                "scenario_id": "scenario_123",
                "public": False,
            },
        ),
        ("GET", "https://api.argalabs.com/validate/twins/provision/run_123/status", None),
        (
            "POST",
            "https://api.argalabs.com/validate/twins/provision/run_123/extend",
            {"ttl_minutes": 75},
        ),
        ("POST", "https://api.argalabs.com/validate/twins/provision/run_123/teardown", None),
        ("POST", "https://api.argalabs.com/validate/twins/provision/run_123/lock", None),
    ]


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


def test_previews_sandbox_run_uses_sandbox_api(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(main, "_resolve_ttl", lambda client, ttl: ttl)
    captured: dict[str, object] = {}

    def fake_create_sandbox(self, **kwargs: object):
        captured.update(kwargs)
        return {"sandbox_id": "sandbox_123", "status": "queued", "twins": {}}

    monkeypatch.setattr(main.ApiClient, "create_sandbox", fake_create_sandbox)

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
            "--ttl",
            "45",
            "--env",
            "FEATURE_FLAG=on",
        ]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["repo"] == "arga-labs/app"
    assert captured["branch"] == "feature/demo"
    assert captured["twins"] == ["slack"]
    assert captured["ttl_minutes"] == 45
    assert captured["env"] == {"FEATURE_FLAG": "on"}
    assert "Sandbox preview started." in output
    assert "Sandbox ID: sandbox_123" in output


def test_previews_sandbox_status_logs_and_teardown(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(
        main.ApiClient,
        "get_sandbox",
        lambda self, sandbox_id: {"sandbox_id": sandbox_id, "status": "ready", "app_url": "https://app.example.com"},
    )
    monkeypatch.setattr(
        main.ApiClient,
        "get_sandbox_logs",
        lambda self, sandbox_id: {
            "sandbox_id": sandbox_id,
            "logs": [{"timestamp": "2026-05-13T12:00:00Z", "type": "deploy", "message": "Started"}],
        },
    )
    monkeypatch.setattr(
        main.ApiClient,
        "delete_sandbox",
        lambda self, sandbox_id: {"sandbox_id": sandbox_id, "status": "deleted"},
    )

    status_args = main.build_parser().parse_args(["previews", "sandboxes", "status", "sandbox_123"])
    status_exit = status_args.func(status_args)
    status_output = capsys.readouterr().out

    logs_args = main.build_parser().parse_args(["previews", "sandboxes", "logs", "sandbox_123"])
    logs_exit = logs_args.func(logs_args)
    logs_output = capsys.readouterr().out

    teardown_args = main.build_parser().parse_args(["previews", "sandboxes", "teardown", "sandbox_123"])
    teardown_exit = teardown_args.func(teardown_args)
    teardown_output = capsys.readouterr().out

    assert status_exit == 0
    assert "Sandbox ID: sandbox_123" in status_output
    assert "App URL: https://app.example.com" in status_output
    assert logs_exit == 0
    assert "deploy: Started" in logs_output
    assert teardown_exit == 0
    assert "Status: deleted" in teardown_output


def test_twins_provision_accepts_linear(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(main, "_resolve_ttl", lambda client, ttl: ttl)
    captured: dict[str, object] = {}

    def fake_provision(
        self,
        *,
        twins: list[str],
        ttl_minutes: int,
        scenario_prompt: str | None = None,
        scenario_id: str | None = None,
        public: bool = True,
    ):
        captured.update(
            {
                "twins": twins,
                "ttl_minutes": ttl_minutes,
                "scenario_prompt": scenario_prompt,
                "scenario_id": scenario_id,
                "public": public,
            }
        )
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
        "scenario_id": None,
        "public": True,
    }
    assert "Twin provisioning started." in output
    assert "Run ID: linear_run" in output

def test_twins_provision_accepts_gitlab(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(main, "_resolve_ttl", lambda client, ttl: ttl)
    captured: dict[str, object] = {}

    def fake_provision(
        self,
        *,
        twins: list[str],
        ttl_minutes: int,
        scenario_prompt: str | None = None,
        scenario_id: str | None = None,
        public: bool = True,
    ):
        captured.update(
            {
                "twins": twins,
                "ttl_minutes": ttl_minutes,
                "scenario_prompt": scenario_prompt,
                "scenario_id": scenario_id,
                "public": public,
            }
        )
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
        "scenario_id": None,
        "public": True,
    }
    assert "Twin provisioning started." in output
    assert "Run ID: gitlab_run" in output


def test_twins_provision_supports_private_and_scenario_id(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(main, "_resolve_ttl", lambda client, ttl: ttl)
    captured: dict[str, object] = {}

    def fake_provision(
        self,
        *,
        twins: list[str],
        ttl_minutes: int,
        scenario_prompt: str | None = None,
        scenario_id: str | None = None,
        public: bool = True,
    ):
        captured.update(
            {
                "twins": twins,
                "ttl_minutes": ttl_minutes,
                "scenario_prompt": scenario_prompt,
                "scenario_id": scenario_id,
                "public": public,
            }
        )
        return {"run_id": "private_run", "status": "queued"}

    monkeypatch.setattr(main.ApiClient, "provision_twins_start", fake_provision)

    args = main.build_parser().parse_args(
        [
            "previews",
            "twins",
            "provision",
            "--twins",
            "slack,jira",
            "--ttl",
            "45",
            "--scenario-id",
            "scenario_123",
            "--private",
        ]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured == {
        "twins": ["slack", "jira"],
        "ttl_minutes": 45,
        "scenario_prompt": None,
        "scenario_id": "scenario_123",
        "public": False,
    }
    assert "Run ID: private_run" in output


def test_twins_list_prints_catalog(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(
        main.ApiClient,
        "list_twins",
        lambda self: [
            {"name": "jira", "label": "Jira", "kind": "backend", "show_in_ui": True},
            {"name": "slack", "label": "Slack", "kind": "backend", "show_in_ui": False},
        ],
    )

    args = main.build_parser().parse_args(["previews", "twins", "list"])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "NAME" in output
    assert "jira" in output
    assert "Slack" in output
    assert "no" in output


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


def test_twins_extend_uses_api_ttl(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(main, "_resolve_ttl", lambda client, ttl: ttl)
    captured: dict[str, object] = {}

    def fake_extend(self, run_id: str, *, ttl_minutes: int):
        captured.update({"run_id": run_id, "ttl_minutes": ttl_minutes})
        return {"status": "extended", "ttl_minutes": ttl_minutes}

    monkeypatch.setattr(main.ApiClient, "extend_twins", fake_extend)

    args = main.build_parser().parse_args(["previews", "twins", "extend", "run_123", "--ttl", "90"])
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured == {"run_id": "run_123", "ttl_minutes": 90}
    assert "Status: extended" in output


def test_twins_teardown_and_lock_commands(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)
    monkeypatch.setattr(
        main.ApiClient,
        "teardown_twins",
        lambda self, run_id: {"run_id": run_id, "status": "cleaning_up"},
    )
    monkeypatch.setattr(
        main.ApiClient,
        "lock_twins",
        lambda self, run_id: {"run_id": run_id, "status": "locked", "is_public": False},
    )

    teardown_args = main.build_parser().parse_args(["previews", "twins", "teardown", "run_456"])
    teardown_exit = teardown_args.func(teardown_args)
    teardown_output = capsys.readouterr().out

    lock_args = main.build_parser().parse_args(["previews", "twins", "lock", "run_456"])
    lock_exit = lock_args.func(lock_args)
    lock_output = capsys.readouterr().out

    assert teardown_exit == 0
    assert "Status: cleaning_up" in teardown_output
    assert lock_exit == 0
    assert "Status: locked" in lock_output
    assert "Public access: off" in lock_output
