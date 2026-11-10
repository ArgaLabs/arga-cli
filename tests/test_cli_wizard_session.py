from __future__ import annotations

import argparse
import json
import stat

import pytest

from arga_cli import main
from arga_cli.wizard import session, summary


@pytest.fixture(autouse=True)
def isolated_auth(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "CONFIG_PATH", tmp_path / "auth" / "config.json")


def authenticate(key="test-device-key"):
    main.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    main.CONFIG_PATH.write_text(json.dumps({"api_key": key}))


def status():
    return {
        "run_id": "run-gong",
        "status": "ready",
        "proxy_token": "transient-proxy-token",
        "twins": {"gong": {"base_url": "https://gong.example.test", "admin_url": "https://gong.example.test"}},
    }


def test_saved_project_session_contains_metadata_only_and_resolves_auth_in_memory(tmp_path):
    authenticate()
    summary.save_session_state(str(tmp_path), status(), "https://api.argalabs.com")
    path = tmp_path / ".arga-session.json"
    raw = path.read_text()
    metadata = json.loads(raw)
    assert metadata["credential_source"] == "cli-config" and metadata["run_id"] == "run-gong"
    assert "api_key" not in metadata and "proxy_token" not in metadata
    assert "test-device-key" not in raw and "transient-proxy-token" not in raw
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    loaded = session.load_session(str(tmp_path))
    assert loaded["api_key"] == main.load_api_key()
    assert path.read_text() == raw


def test_new_session_writes_strip_legacy_and_nested_credentials_atomically(tmp_path):
    path = tmp_path / ".arga-session.json"
    path.write_text("old metadata")
    path.chmod(0o644)
    session.save_session(
        str(tmp_path),
        {
            "run_id": "run-gong",
            "api_url": "https://api.argalabs.com",
            "api_key": "legacy-test-key",
            "proxy_token": "old-proxy-token",
            "unknown_secret": "not-metadata",
            "twins": {
                "gong": {
                    "base_url": "https://gong.example.test",
                    "api_key": "nested-test-key",
                    "env_vars": {"SECRET": "value"},
                }
            },
        },
    )
    metadata = json.loads(path.read_text())
    assert set(metadata) == {"run_id", "api_url", "credential_source", "twins"}
    assert metadata["twins"] == {"gong": {"base_url": "https://gong.example.test"}}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".arga-session-*"))


def test_new_session_survives_standard_credential_rotation_without_rewriting_project_file(tmp_path):
    authenticate("first-test-device-key")
    summary.save_session_state(str(tmp_path), status(), "https://api.argalabs.com")
    path = tmp_path / ".arga-session.json"
    original = path.read_text()
    first = session.load_session(str(tmp_path))["api_key"]
    authenticate("rotated-test-device-key")
    second = session.load_session(str(tmp_path))["api_key"]
    assert first != second and second == main.load_api_key()
    assert path.read_text() == original


def test_flag_only_session_preserves_run_but_requires_standard_login_to_resume(tmp_path):
    summary.save_session_state(str(tmp_path), status(), "https://api.argalabs.com")
    path = tmp_path / ".arga-session.json"
    metadata = path.read_text()
    assert json.loads(metadata)["run_id"] == "run-gong"
    with pytest.raises(main.NotAuthenticatedError, match="arga login"):
        session.load_session(str(tmp_path))
    assert not main.CONFIG_PATH.exists()
    authenticate()
    assert session.load_session(str(tmp_path))["run_id"] == "run-gong"
    assert path.read_text() == metadata


def test_legacy_embedded_key_is_readable_as_fallback_but_is_not_copied_on_new_write(tmp_path):
    path = tmp_path / ".arga-session.json"
    legacy = {"run_id": "run-gong", "api_url": "https://api.argalabs.com", "api_key": "legacy-test-key"}
    path.write_text(json.dumps(legacy))
    loaded = session.load_session(str(tmp_path))
    assert loaded == legacy and not main.CONFIG_PATH.exists()
    session.save_session(str(tmp_path), loaded)
    assert "api_key" not in json.loads(path.read_text())
    assert not main.CONFIG_PATH.exists()


def test_standard_auth_takes_precedence_over_legacy_credential_after_rotation(tmp_path):
    path = tmp_path / ".arga-session.json"
    path.write_text(json.dumps({"run_id": "run-gong", "api_key": "old-test-key"}))
    original = path.read_text()
    authenticate("rotated-test-key")
    assert session.load_session(str(tmp_path))["api_key"] == main.load_api_key()
    assert path.read_text() == original


@pytest.mark.parametrize(
    "command", [main.run_wizard_status, main.run_wizard_extend, main.run_wizard_reset, main.run_wizard_teardown]
)
def test_session_commands_resume_reference_only_session_using_current_auth(monkeypatch, tmp_path, command):
    authenticate()
    summary.save_session_state(str(tmp_path), status(), "https://api.argalabs.com")
    monkeypatch.chdir(tmp_path)
    requests = []

    class Client:
        def __init__(self, api_url, *, api_key):
            assert api_key == main.load_api_key()
            self._api_url = api_url
            self._client = self

        def _auth_headers(self):
            return {"Authorization": "Bearer " + main.load_api_key()}

        def get(self, url, **kwargs):
            requests.append(("GET", url, kwargs))
            return status()

        def post(self, url, **kwargs):
            requests.append(("POST", url, kwargs))
            return {}

        def _parse_json(self, response, _message):
            return response

        def close(self):
            pass

    monkeypatch.setattr(main, "ApiClient", Client)
    assert command(argparse.Namespace()) == 0
    assert requests and requests[0][2]["headers"] == {"Authorization": "Bearer " + main.load_api_key()}
    if command == main.run_wizard_reset:
        assert requests[-1][1].endswith("/admin/reset?token=transient-proxy-token")
    if command == main.run_wizard_teardown:
        assert not (tmp_path / ".arga-session.json").exists()
