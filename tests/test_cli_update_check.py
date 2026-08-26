from __future__ import annotations

import json
import time
from argparse import Namespace

from arga_cli import main


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def test_required_update_blocks_wizard_startup(monkeypatch, tmp_path, capsys) -> None:
    cache_path = tmp_path / "version_check.json"
    monkeypatch.setattr(main, "VERSION_CHECK_PATH", cache_path)
    monkeypatch.setattr(main, "_cli_version", lambda: "0.1.18")

    def fake_get(url: str, **kwargs) -> _Response:
        assert url == "https://api.argalabs.com/client-versions/arga-cli"
        assert kwargs["headers"] == {main.ARGA_CLI_VERSION_HEADER: "0.1.18"}
        return _Response(
            {
                "latest_version": "0.1.19",
                "minimum_version": "0.1.19",
                "upgrade_command": "uv tool upgrade arga-cli",
                "message": "Update Arga, then restart the wizard.",
            }
        )

    monkeypatch.setattr(main.httpx, "get", fake_get)

    assert main._check_for_update("https://api.argalabs.com/") is False
    assert "Update Arga, then restart the wizard." in capsys.readouterr().err
    assert json.loads(cache_path.read_text())["current_version"] == "0.1.18"


def test_available_update_warns_without_blocking(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(main, "VERSION_CHECK_PATH", tmp_path / "version_check.json")
    monkeypatch.setattr(main, "_cli_version", lambda: "0.1.18")
    monkeypatch.setattr(
        main.httpx,
        "get",
        lambda *_args, **_kwargs: _Response(
            {
                "latest_version": "0.1.19",
                "minimum_version": "0.1.18",
                "upgrade_command": "uv tool upgrade arga-cli",
            }
        ),
    )

    assert main._check_for_update() is True
    assert "arga-cli 0.1.19 available" in capsys.readouterr().err


def test_fresh_cache_avoids_network_request(monkeypatch, tmp_path) -> None:
    cache_path = tmp_path / "version_check.json"
    cache_path.write_text(
        json.dumps(
            {
                "api_url": "https://api.argalabs.com",
                "current_version": "0.1.19",
                "latest_version": "0.1.19",
                "minimum_version": "0.1.19",
                "checked_at": time.time(),
            }
        )
    )
    monkeypatch.setattr(main, "VERSION_CHECK_PATH", cache_path)
    monkeypatch.setattr(main, "_cli_version", lambda: "0.1.19")

    def unexpected_get(*_args, **_kwargs):
        raise AssertionError("fresh cache should prevent a network request")

    monkeypatch.setattr(main.httpx, "get", unexpected_get)

    assert main._check_for_update() is True


def test_authenticated_requests_include_cli_version(monkeypatch) -> None:
    monkeypatch.setattr(main, "_cli_version", lambda: "0.1.19")
    client = main.ApiClient("https://api.argalabs.com", api_key="arga_sk_test")
    try:
        assert client._auth_headers() == {
            "Authorization": "Bearer arga_sk_test",
            main.ARGA_CLI_VERSION_HEADER: "0.1.19",
        }
    finally:
        client.close()


def test_wizard_does_not_open_when_upgrade_is_required(monkeypatch) -> None:
    monkeypatch.setattr(main, "_check_for_update", lambda _api_url: False)

    assert (
        main.run_wizard_init(
            Namespace(
                api_url="https://api.argalabs.com",
                ttl=None,
                no_shape_detect=False,
            )
        )
        == 1
    )


def test_version_comparison_handles_patch_and_prerelease_versions() -> None:
    assert main._version_is_older("0.1.18", "0.1.19")
    assert not main._version_is_older("0.1.19", "0.1.19")
    assert not main._version_is_older("0.2.0", "0.1.19")
    assert not main._version_is_older("unknown", "0.1.19")
    assert main._version_tuple("0.1.19rc1") is None
    assert main._version_tuple("0.1.19-beta.1") == (0, 1, 19)
