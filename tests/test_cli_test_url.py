from __future__ import annotations

import json

from arga_cli import main


def test_create_demo_run_uses_supported_test_runs_endpoint(monkeypatch) -> None:
    client = main.ApiClient("https://api.argalabs.com", api_key="arga_api_key")
    captured: dict[str, object] = {}

    def fake_post(url: str, *, json: dict[str, object], headers: dict[str, str]):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers

        class FakeResponse:
            is_success = True
            status_code = 200

            def json(self) -> dict[str, str]:
                return {"id": "run_3421", "status": "queued", "session_id": "session_1"}

        return FakeResponse()

    monkeypatch.setattr(client._client, "post", fake_post)
    try:
        payload = client.create_demo_run(
            start_url="https://demo-app.com",
            prompt="test login flow",
            repo="arga-labs/demo",
            branch="main",
            pr_url="https://github.com/arga-labs/demo/pull/1",
            scenario_id="scenario_123",
            twins=["slack"],
        )
    finally:
        client.close()

    assert captured["url"] == "https://api.argalabs.com/test-runs"
    assert captured["json"] == {
        "prompt": "test login flow",
        "start_url": "https://demo-app.com",
        "repo": "arga-labs/demo",
        "branch": "main",
        "pr_url": "https://github.com/arga-labs/demo/pull/1",
        "scenario_id": "scenario_123",
        "twins": ["slack"],
    }
    assert payload == {"id": "run_3421", "status": "queued", "session_id": "session_1"}


def test_test_url_command_prints_run_id(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "get_me", lambda self: {"billing_plan": "free"})

    def fake_create(
        self,
        *,
        prompt: str,
        start_url: str | None = None,
        scenario_id: str | None = None,
        twins: list[str] | None = None,
        **_: object,
    ):
        assert start_url == "https://demo-app.com"
        assert prompt == "test login flow"
        assert scenario_id is None
        assert twins is None
        return {"run_id": "run_3421", "status": "queued", "session_id": "session_1"}

    monkeypatch.setattr(main.ApiClient, "create_demo_run", fake_create)
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    args = main.build_parser().parse_args(
        ["test", "url", "--url", "https://demo-app.com", "--prompt", "test login flow"]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Starting test run..." in output
    assert "Run ID: run_3421" in output
    assert "Status: queued" in output


def test_test_url_json_flag(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "get_me", lambda self: {"billing_plan": "free"})

    def fake_create(
        self,
        *,
        prompt: str,
        start_url: str | None = None,
        scenario_id: str | None = None,
        twins: list[str] | None = None,
        **_: object,
    ):
        assert start_url == "https://demo-app.com"
        assert prompt == "test login flow"
        assert scenario_id is None
        assert twins is None
        return {"run_id": "run_3421", "status": "queued", "session_id": "session_1"}

    monkeypatch.setattr(main.ApiClient, "create_demo_run", fake_create)
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    args = main.build_parser().parse_args(
        ["test", "url", "--url", "https://demo-app.com", "--prompt", "test login flow", "--json"]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    parsed = json.loads(output)
    assert parsed == {"run_id": "run_3421", "status": "queued"}


def test_test_url_rejects_ttl_without_supported_run_surface(monkeypatch) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "get_me", lambda self: {"billing_plan": "team"})
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    args = main.build_parser().parse_args(
        ["test-runner", "runs", "url", "--url", "https://demo-app.com", "--prompt", "test login flow", "--ttl", "30"]
    )

    try:
        args.func(args)
    except main.CliError as exc:
        assert "--ttl is only supported" in str(exc)
    else:
        raise AssertionError("expected CliError")


def test_test_url_rejects_legacy_credentials(monkeypatch) -> None:
    args = main.build_parser().parse_args(
        [
            "test",
            "url",
            "--url",
            "https://demo-app.com",
            "--prompt",
            "test login flow",
            "--email",
            "user@example.com",
            "--password",
            "secret",
        ]
    )

    try:
        args.func(args)
    except main.CliError as exc:
        assert "Direct URL runs no longer accept --email/--password" in str(exc)
    else:
        raise AssertionError("expected CliError")
