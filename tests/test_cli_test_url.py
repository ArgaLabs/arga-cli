from __future__ import annotations

from arga_cli import main


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
