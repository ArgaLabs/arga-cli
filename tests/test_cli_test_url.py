from __future__ import annotations

import json

from arga_cli import main


def test_start_url_validation_uses_longer_timeout(monkeypatch) -> None:
    client = main.ApiClient("https://api.argalabs.com", api_key="arga_api_key")
    captured: dict[str, object] = {}

    def fake_post(url: str, *, json: dict[str, object], headers: dict[str, str], timeout: float):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout

        class FakeResponse:
            is_success = True
            status_code = 200

            def json(self) -> dict[str, str]:
                return {"run_id": "run_3421", "status": "queued", "session_id": "session_1"}

        return FakeResponse()

    monkeypatch.setattr(client._client, "post", fake_post)
    try:
        payload = client.start_url_validation(url="https://demo-app.com", prompt="test login flow")
    finally:
        client.close()

    assert captured["url"] == "https://api.argalabs.com/validate/url"
    assert captured["json"] == {"url": "https://demo-app.com", "prompt": "test login flow"}
    assert captured["timeout"] == main.URL_VALIDATION_START_TIMEOUT_SECONDS
    assert payload == {"run_id": "run_3421", "status": "queued", "session_id": "session_1"}


def test_test_url_command_prints_run_id(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")

    def fake_start(self, *, url: str, prompt: str, email: str | None = None, password: str | None = None):
        assert url == "https://demo-app.com"
        assert prompt == "test login flow"
        assert email is None
        assert password is None
        return {"run_id": "run_3421", "status": "queued", "session_id": "session_1"}

    monkeypatch.setattr(main.ApiClient, "start_url_validation", fake_start)
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    args = main.build_parser().parse_args(
        ["test", "url", "--url", "https://demo-app.com", "--prompt", "test login flow"]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Starting validation..." in output
    assert "Run ID: run_3421" in output
    assert "Status: queued" in output


def test_test_url_json_flag(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")

    def fake_start(self, *, url: str, prompt: str, email: str | None = None, password: str | None = None):
        return {"run_id": "run_3421", "status": "queued", "session_id": "session_1"}

    monkeypatch.setattr(main.ApiClient, "start_url_validation", fake_start)
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    args = main.build_parser().parse_args(
        ["test", "url", "--url", "https://demo-app.com", "--prompt", "test login flow", "--json"]
    )
    exit_code = args.func(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    parsed = json.loads(output)
    assert parsed == {"run_id": "run_3421", "status": "queued"}
