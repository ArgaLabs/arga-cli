from __future__ import annotations

import argparse
import json

from arga_cli import main


def test_devices_list_command_uses_cli_devices_api(monkeypatch, capsys) -> None:
    seen: dict[str, str | None] = {}

    monkeypatch.setattr(main, "load_api_key", lambda: "arga_key")

    def fake_list(self: main.ApiClient) -> list[dict[str, str | None]]:
        seen["api_url"] = self._api_url
        return [
            {
                "id": "device_123",
                "device_name": "dev-laptop",
                "key_preview": "arga_...abcd",
                "created_at": "2026-05-31T12:00:00Z",
                "last_used_at": None,
                "revoked_at": None,
            }
        ]

    monkeypatch.setattr(main.ApiClient, "list_cli_devices", fake_list)

    args = main.build_parser().parse_args(["devices", "list", "--api-url", "https://api.example.com"])
    exit_code = args.func(args)

    assert exit_code == 0
    assert seen["api_url"] == "https://api.example.com"
    output = capsys.readouterr().out
    assert "device_123" in output
    assert "dev-laptop" in output
    assert "2026-05-31 12:00" in output


def test_devices_list_command_supports_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_key")
    monkeypatch.setattr(
        main.ApiClient,
        "list_cli_devices",
        lambda self: [{"id": "device_123", "device_name": "dev-laptop"}],
    )

    args = main.build_parser().parse_args(["devices", "list", "--json"])
    exit_code = args.func(args)

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == [{"id": "device_123", "device_name": "dev-laptop"}]


def test_devices_revoke_command_uses_cli_device_revoke_api(monkeypatch, capsys) -> None:
    seen: dict[str, str] = {}

    monkeypatch.setattr(main, "load_api_key", lambda: "arga_key")

    def fake_revoke(self: main.ApiClient, device_id: str) -> dict[str, str]:
        seen["device_id"] = device_id
        seen["api_url"] = self._api_url
        return {"status": "revoked"}

    monkeypatch.setattr(main.ApiClient, "revoke_cli_device", fake_revoke)

    args = main.build_parser().parse_args(
        ["devices", "revoke", "device_123", "--api-url", "https://api.example.com"]
    )
    exit_code = args.func(args)

    assert exit_code == 0
    assert seen == {"device_id": "device_123", "api_url": "https://api.example.com"}
    output = capsys.readouterr().out
    assert "Device ID: device_123" in output
    assert "Status: revoked" in output


def test_wizard_teardown_uses_twin_run_teardown_api(monkeypatch, tmp_path, capsys) -> None:
    session_path = tmp_path / ".arga-session.json"
    session_path.write_text(
        json.dumps({"api_url": "https://api.example.com", "api_key": "arga_key", "run_id": "run_123"})
    )
    monkeypatch.chdir(tmp_path)

    seen: dict[str, str] = {}

    def fake_teardown(self: main.ApiClient, run_id: str) -> dict[str, str]:
        seen["run_id"] = run_id
        seen["api_url"] = self._api_url
        return {"status": "cleaning_up"}

    monkeypatch.setattr(main.ApiClient, "teardown_twins", fake_teardown)

    exit_code = main.run_wizard_teardown(argparse.Namespace())

    assert exit_code == 0
    assert seen == {"run_id": "run_123", "api_url": "https://api.example.com"}
    assert not session_path.exists()
    assert "Session destroyed" in capsys.readouterr().out
