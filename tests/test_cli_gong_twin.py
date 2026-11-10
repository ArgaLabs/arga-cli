from __future__ import annotations

import argparse
import copy
import stat
from types import SimpleNamespace

import pytest

from arga_cli import main, wizard
from arga_cli.wizard import env, prompts, session
from arga_cli.wizard.constants import QUICKSTART_SUMMARIES, TWIN_CATALOG, TWIN_ENV_MAPPINGS

RETURNED_ENV = {
    "GONG_ACCESS_TOKEN": "scenario-access-token",
    "GONG_ACCESS_KEY": "scenario-access-key",
    "GONG_ACCESS_KEY_SECRET": "scenario-access-secret",
    "GONG_ACCESS_SECRET": "scenario-access-secret",
    "GONG_CLIENT_ID": "scenario-client-id",
    "GONG_CLIENT_SECRET": "scenario-client-secret",
    "GONG_BASE_URL": "https://pub-run--gong.sandbox.argalabs.com",
    "GONG_API_BASE_URL": "https://pub-run--gong.sandbox.argalabs.com",
    "GONG_AUTH_BASE_URL": "https://pub-run--gong.sandbox.argalabs.com",
    "GONG_MCP_URL": "https://pub-run--gong.sandbox.argalabs.com/mcp",
    "GONG_SCIM_BASE_URL": "https://pub-run--gong.sandbox.argalabs.com/scim/v2",
}
READY_STATUS = {"run_id": "run-gong", "status": "ready", "twins": {"gong": {"env_vars": RETURNED_ENV}}}


def original_env():
    values = {key: ("https://real.api.gong.io" if "URL" in key else "real-" + key) for key in RETURNED_ENV}
    return (
        "# Existing configuration\n"
        + "".join(f"{key}={value}\n" for key, value in values.items())
        + "SLACK_BOT_TOKEN=real-slack-token\nUNRELATED_URL=https://other.example\n"
    )


def accept_env_prompts(monkeypatch, file_path):
    monkeypatch.setattr(env.questionary, "select", lambda *args, **kwargs: SimpleNamespace(ask=lambda: str(file_path)))
    monkeypatch.setattr(env.questionary, "confirm", lambda *args, **kwargs: SimpleNamespace(ask=lambda: True))


def fake_wizard(monkeypatch, provision):
    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_me(self):
            return {"billing_plan": "paid", "plan_limits": {}}

        def list_twins(self):
            return [{"name": "gong", "label": "Gong", "kind": "frontend"}]

    monkeypatch.setattr(main, "ApiClient", Client)
    monkeypatch.setattr(main, "load_api_key", lambda: "arga-test")
    monkeypatch.setattr(wizard, "prompt_api_key", lambda _url, supplied: supplied or "arga-test")
    monkeypatch.setattr(wizard, "select_twins", lambda *_args, **_kwargs: ["gong"])
    monkeypatch.setattr(wizard, "describe_scenario", lambda *_args: None)
    monkeypatch.setattr(wizard, "provision_twins", provision)
    monkeypatch.setattr(wizard, "seed_and_report", lambda *_args: None)
    monkeypatch.setattr(wizard, "print_summary", lambda *_args, **_kwargs: None)


def test_gong_is_selectable_offline_with_correct_service_metadata():
    assert TWIN_CATALOG["gong"] == {
        "label": "Gong",
        "port": 12162,
        "show_in_ui": True,
        "intercept_domains": [
            "api.gong.io",
            "company-twin.api.gong.io",
            "app.gong.io",
            "mcp.gong.io",
            "provisioning.gong.io",
        ],
    }
    assert "Access token: gong-twin-access-token" in QUICKSTART_SUMMARIES["gong"]
    for key, value in TWIN_ENV_MAPPINGS["gong"]["defaults"].items():
        assert env.resolve_env_var(key, ["gong"]) == {"twin": "gong", "default_value": value}


def test_wizard_waits_for_provision_then_rewrites_real_gong_hosts_and_scenario_credentials(monkeypatch, tmp_path):
    file_path = tmp_path / ".env"
    original = original_env()
    file_path.write_text(original)
    file_path.chmod(0o640)
    accept_env_prompts(monkeypatch, file_path)

    def provision(*_args, **_kwargs):
        assert file_path.read_text() == original
        assert not (tmp_path / ".env.arga-backup").exists()
        return copy.deepcopy(READY_STATUS)

    fake_wizard(monkeypatch, provision)
    assert wizard.run_wizard(api_url="https://api.argalabs.com", cwd=str(tmp_path)) == 0
    rewritten = {entry.key: entry.value.split(" # ")[0] for entry in env.parse_env_file(str(file_path)) if entry.key}
    for key, value in RETURNED_ENV.items():
        assert rewritten[key] == value
    assert rewritten["SLACK_BOT_TOKEN"] == "real-slack-token"
    assert rewritten["UNRELATED_URL"] == "https://other.example"
    assert file_path.read_text().startswith("# Existing configuration\n")
    backup = tmp_path / ".env.arga-backup"
    assert backup.read_text() == original
    assert stat.S_IMODE(file_path.stat().st_mode) == stat.S_IMODE(backup.stat().st_mode) == 0o640


def test_failed_gong_provision_does_not_rewrite_or_prompt_for_env_file(monkeypatch, tmp_path):
    file_path = tmp_path / ".env"
    file_path.write_text(original_env())

    def provision(*_args, **_kwargs):
        raise RuntimeError("Provision failed")

    fake_wizard(monkeypatch, provision)
    monkeypatch.setattr(
        wizard, "rewrite_env_files", lambda *_args, **_kwargs: pytest.fail("Rewrite called before ready")
    )
    assert wizard.run_wizard(api_url="https://api.argalabs.com", cwd=str(tmp_path)) == 1
    assert file_path.read_text() == original_env() and not (tmp_path / ".env.arga-backup").exists()


def test_interrupted_gong_env_prompt_keeps_session_for_status_and_teardown(monkeypatch, tmp_path):
    file_path = tmp_path / ".env"
    file_path.write_text(original_env())
    fake_wizard(monkeypatch, lambda *_args, **_kwargs: copy.deepcopy(READY_STATUS))

    def cancelled(*_args, **_kwargs):
        saved = session.load_session(str(tmp_path))
        assert saved["run_id"] == "run-gong" and saved["api_key"] == "arga-test"
        raise KeyboardInterrupt

    monkeypatch.setattr(wizard, "rewrite_env_files", cancelled)
    with pytest.raises(KeyboardInterrupt):
        wizard.run_wizard(api_url="https://api.argalabs.com", cwd=str(tmp_path))
    assert session.load_session(str(tmp_path))["run_id"] == "run-gong"
    assert file_path.read_text() == original_env() and not (tmp_path / ".env.arga-backup").exists()


def test_flag_only_interrupted_setup_retains_handle_without_saving_supplied_credential(monkeypatch, tmp_path):
    fake_wizard(monkeypatch, lambda *_args, **_kwargs: copy.deepcopy(READY_STATUS))

    def missing_auth():
        raise main.NotAuthenticatedError("Run `arga login`.")

    def cancelled(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(main, "load_api_key", missing_auth)
    monkeypatch.setattr(wizard, "rewrite_env_files", cancelled)
    with pytest.raises(KeyboardInterrupt):
        wizard.run_wizard(api_url="https://api.argalabs.com", api_key="flag-only-test-key", cwd=str(tmp_path))
    metadata = (tmp_path / ".arga-session.json").read_text()
    assert "flag-only-test-key" not in metadata and "api_key" not in metadata
    with pytest.raises(main.NotAuthenticatedError, match="arga login"):
        session.load_session(str(tmp_path))
    monkeypatch.setattr(main, "load_api_key", lambda: "normal-login-test-key")
    assert session.load_session(str(tmp_path))["run_id"] == "run-gong"
    assert (tmp_path / ".arga-session.json").read_text() == metadata


@pytest.mark.parametrize("run_id", [None, "", "   ", 42, [], {}])
def test_complete_gong_environment_without_valid_run_id_cannot_rewrite_files(monkeypatch, tmp_path, run_id):
    file_path = tmp_path / ".env"
    file_path.write_text(original_env())
    status = {**copy.deepcopy(READY_STATUS), "run_id": run_id}
    if run_id is None:
        status.pop("run_id")
    fake_wizard(monkeypatch, lambda *_args, **_kwargs: status)
    monkeypatch.setattr(
        wizard, "rewrite_env_files", lambda *_args, **_kwargs: pytest.fail("Unrecoverable run reached rewrite")
    )
    assert wizard.run_wizard(api_url="https://api.argalabs.com", cwd=str(tmp_path)) == 1
    assert file_path.read_text() == original_env()
    assert not (tmp_path / ".env.arga-backup").exists()
    assert not (tmp_path / ".arga-session.json").exists()


@pytest.mark.parametrize("twins", [{"gong": {"env_vars": {}}}, None, {"gong": None}])
def test_incomplete_gong_environment_keeps_run_handle_for_status_and_teardown(monkeypatch, tmp_path, capsys, twins):
    file_path = tmp_path / ".env"
    file_path.write_text(original_env())
    fake_wizard(monkeypatch, lambda *_args, **_kwargs: {"run_id": "run-live", "status": "ready", "twins": twins})
    assert wizard.run_wizard(api_url="https://api.argalabs.com", cwd=str(tmp_path)) == 1
    saved = session.load_session(str(tmp_path))
    assert saved["run_id"] == "run-live" and saved["api_url"] == "https://api.argalabs.com"
    captured = capsys.readouterr()
    output = " ".join((captured.out + captured.err).split())
    assert "Run run-live is still active" in output
    assert "arga wizard status" in output and "arga wizard teardown" in output
    assert "arga login" in output and "unsaved API key" in output
    assert file_path.read_text() == original_env() and not (tmp_path / ".env.arga-backup").exists()


@pytest.mark.parametrize(
    "status",
    [
        {"status": "ready", "twins": {}},
        {"status": "ready", "twins": {"gong": {"env_vars": {"GONG_ACCESS_TOKEN": "partial-token"}}}},
        {"status": "ready", "twins": {"gong": {"env_vars": {**RETURNED_ENV, "GONG_MCP_URL": ""}}}},
        {**READY_STATUS, "status": "provisioning"},
    ],
)
def test_incomplete_gong_status_refuses_rewrite_before_any_file_changes(monkeypatch, tmp_path, status):
    file_path = tmp_path / ".env"
    file_path.write_text(original_env())
    fake_wizard(monkeypatch, lambda *_args, **_kwargs: copy.deepcopy(status))
    monkeypatch.setattr(wizard, "rewrite_env_files", lambda *_args, **_kwargs: pytest.fail("Incomplete values applied"))
    assert wizard.run_wizard(api_url="https://api.argalabs.com", cwd=str(tmp_path)) == 1
    assert file_path.read_text() == original_env() and not (tmp_path / ".env.arga-backup").exists()


def test_returned_values_cannot_cross_selected_provider_boundaries():
    status = copy.deepcopy(READY_STATUS)
    status["twins"]["gong"]["env_vars"].update(
        {"SLACK_BOT_TOKEN": "cross-provider-value", "UNRELATED_SECRET": "ignored"}
    )
    status["twins"]["slack"] = {
        "env_vars": {"SLACK_BOT_TOKEN": "own-slack-token", "GONG_ACCESS_TOKEN": "wrong-provider"}
    }
    assert env.provisioned_env_values(status, ["gong"]) == RETURNED_ENV
    values = env.provisioned_env_values(status, ["slack", "gong"])
    assert values == {**RETURNED_ENV, "SLACK_BOT_TOKEN": "own-slack-token"}
    assert env.resolve_env_var("SLACK_BOT_TOKEN", ["gong"], env_values=values) is None
    assert env.match_value_shape("opaque-real-gong-credential", ["gong"]) is None


def test_mixed_provider_wizard_rewrites_only_each_selected_providers_own_values(monkeypatch, tmp_path):
    file_path = tmp_path / ".env"
    original = original_env() + "STRIPE_SECRET_KEY=real-stripe-key\n"
    file_path.write_text(original)
    accept_env_prompts(monkeypatch, file_path)
    status = copy.deepcopy(READY_STATUS)
    status["twins"]["gong"]["env_vars"].update(
        {"SLACK_BOT_TOKEN": "wrong-slack-token", "STRIPE_SECRET_KEY": "wrong-stripe-key"}
    )
    status["twins"]["slack"] = {
        "env_vars": {"SLACK_BOT_TOKEN": "returned-slack-token", "GONG_ACCESS_TOKEN": "wrong-gong-token"}
    }
    fake_wizard(monkeypatch, lambda *_args, **_kwargs: status)
    monkeypatch.setattr(wizard, "select_twins", lambda *_args, **_kwargs: ["slack", "gong"])
    assert wizard.run_wizard(api_url="https://api.argalabs.com", cwd=str(tmp_path)) == 0
    updated = file_path.read_text()
    assert "GONG_ACCESS_TOKEN=scenario-access-token" in updated
    assert "SLACK_BOT_TOKEN=returned-slack-token" in updated
    assert "STRIPE_SECRET_KEY=real-stripe-key\n" in updated
    assert "wrong-" not in updated
    assert (tmp_path / ".env.arga-backup").read_text() == original


def test_shape_fallback_preserves_already_correct_scenario_token_and_unselected_provider_key(monkeypatch, tmp_path):
    file_path = tmp_path / ".env"
    file_path.write_text(
        original_env().replace("SLACK_BOT_TOKEN=real-slack-token", "SLACK_BOT_TOKEN=xoxb-custom-scenario")
        + "GITHUB_TOKEN=xoxb-unselected-provider-token\n"
    )
    accept_env_prompts(monkeypatch, file_path)
    values = {**RETURNED_ENV, "SLACK_BOT_TOKEN": "xoxb-custom-scenario"}
    changes = env.rewrite_env_files(str(tmp_path), ["gong", "slack"], env_values=values)
    assert {change.key for change in changes} == set(RETURNED_ENV)
    updated = file_path.read_text()
    assert "SLACK_BOT_TOKEN=xoxb-custom-scenario\n" in updated
    assert "GITHUB_TOKEN=xoxb-unselected-provider-token\n" in updated


def test_shape_fallback_still_supports_unknown_selected_provider_aliases(monkeypatch, tmp_path):
    file_path = tmp_path / ".env"
    file_path.write_text("CUSTOM_SLACK_TOKEN=xoxb-real-token\n")
    accept_env_prompts(monkeypatch, file_path)
    changes = env.rewrite_env_files(str(tmp_path), ["slack"])
    assert len(changes) == 1 and changes[0].key == "CUSTOM_SLACK_TOKEN"
    assert changes[0].new_value == TWIN_ENV_MAPPINGS["slack"]["defaults"]["SLACK_BOT_TOKEN"]


@pytest.mark.parametrize("returned", [None, "xoxb-custom-scenario"])
def test_selected_defaultless_alias_uses_its_owners_shape_and_scenario_value(monkeypatch, tmp_path, returned):
    file_path = tmp_path / ".env"
    file_path.write_text("SLACK_TOKEN=xoxb-real-token\nGITHUB_TOKEN=xoxb-other-provider\n")
    accept_env_prompts(monkeypatch, file_path)
    values = {"SLACK_BOT_TOKEN": returned} if returned else None
    changes = env.rewrite_env_files(str(tmp_path), ["slack"], env_values=values)
    expected = returned or TWIN_ENV_MAPPINGS["slack"]["defaults"]["SLACK_BOT_TOKEN"]
    assert [(change.key, change.twin, change.new_value) for change in changes] == [("SLACK_TOKEN", "slack", expected)]
    assert "GITHUB_TOKEN=xoxb-other-provider\n" in file_path.read_text()


def test_defaultless_alias_cannot_use_another_selected_providers_shape(monkeypatch, tmp_path):
    file_path = tmp_path / ".env"
    original = "SLACK_TOKEN=glpat-real-gitlab-token\nGITLAB_BASE_URL=xoxb-not-a-url\n"
    file_path.write_text(original)
    accept_env_prompts(monkeypatch, file_path)
    monkeypatch.setattr(
        env.questionary, "confirm", lambda *_args, **_kwargs: pytest.fail("Wrong-owner fallback prompted")
    )
    assert env.rewrite_env_files(str(tmp_path), ["slack", "gitlab"]) == []
    assert file_path.read_text() == original


def test_already_correct_defaultless_scenario_alias_does_not_revert_to_static_default(monkeypatch, tmp_path):
    file_path = tmp_path / ".env"
    original = "SLACK_TOKEN=xoxb-custom-scenario\n"
    file_path.write_text(original)
    accept_env_prompts(monkeypatch, file_path)
    monkeypatch.setattr(env.questionary, "confirm", lambda *_args, **_kwargs: pytest.fail("Correct alias prompted"))
    assert env.rewrite_env_files(str(tmp_path), ["slack"], env_values={"SLACK_BOT_TOKEN": "xoxb-custom-scenario"}) == []
    assert file_path.read_text() == original


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("token # [arga-twin: gong]", "token"),
        ('"token" # [arga-twin: gong]', "token"),
        ("'token' # [arga-twin: gong]", "token"),
        ('"literal # [arga-twin: gong]"', "literal # [arga-twin: gong]"),
        ("'literal # [arga-twin: gong]'", "literal # [arga-twin: gong]"),
        ('"literal # [arga-twin: gong]', '"literal # [arga-twin: gong]'),
        ("token# [arga-twin: gong]", "token# [arga-twin: gong]"),
        ("token # [arga-twin: gong] extra", "token # [arga-twin: gong] extra"),
    ],
)
def test_twin_marker_parser_strips_only_generated_unquoted_comment_suffix(tmp_path, raw, expected):
    file_path = tmp_path / ".env"
    file_path.write_text("VALUE=" + raw + "\n")
    entry = env.parse_env_file(str(file_path))[0]
    assert entry.value == expected and entry.raw == "VALUE=" + raw


def test_second_identical_gong_rewrite_does_not_prompt_or_replace_original_backup(monkeypatch, tmp_path):
    file_path = tmp_path / ".env"
    original = original_env()
    file_path.write_text(original)
    accept_env_prompts(monkeypatch, file_path)
    assert env.rewrite_env_files(str(tmp_path), ["gong"], env_values=RETURNED_ENV)
    rewritten = file_path.read_text()
    assert "# [arga-twin: gong]" in rewritten
    monkeypatch.setattr(env.questionary, "confirm", lambda *_args, **_kwargs: pytest.fail("Identical rewrite prompted"))
    assert env.rewrite_env_files(str(tmp_path), ["gong"], env_values=RETURNED_ENV) == []
    assert file_path.read_text() == rewritten
    assert (tmp_path / ".env.arga-backup").read_text() == original


@pytest.mark.parametrize("credential", ["synthetic'credential", 'synthetic"credential', "synthetic-credential\\"])
def test_unquoted_internal_quotes_and_backslash_roundtrip_through_apply_parse_repeat(monkeypatch, tmp_path, credential):
    file_path = tmp_path / ".env"
    original = "SLACK_BOT_TOKEN=original-test-token\n"
    file_path.write_text(original)
    entries = env.parse_env_file(str(file_path))
    env.apply_env_changes(
        str(file_path), entries, [env.EnvChange("SLACK_BOT_TOKEN", "original-test-token", credential, "slack")]
    )
    rewritten = file_path.read_text()
    assert env.parse_env_file(str(file_path))[0].value == credential
    accept_env_prompts(monkeypatch, file_path)
    monkeypatch.setattr(
        env.questionary, "confirm", lambda *_args, **_kwargs: pytest.fail("Roundtrip credential prompted")
    )
    assert env.rewrite_env_files(str(tmp_path), ["slack"], env_values={"SLACK_BOT_TOKEN": credential}) == []
    assert file_path.read_text() == rewritten and (tmp_path / ".env.arga-backup").read_text() == original


@pytest.mark.parametrize(
    "status",
    [
        None,
        [],
        {"twins": None},
        {"twins": []},
        {"twins": {"gong": None}},
        {"twins": {"gong": []}},
        {"twins": {"gong": {"env_vars": None}}},
        {"twins": {"gong": {"env_vars": []}}},
    ],
)
def test_malformed_provision_response_is_rejected_without_attribute_errors(status):
    with pytest.raises(ValueError, match="no .env files changed"):
        env.provisioned_env_values(status, ["gong"])


@pytest.mark.parametrize(
    "secret", ["line\nbreak", "line\rbreak", "has space", "has#comment", "${REAL_SECRET}", "has'quote"]
)
def test_unquoted_unsafe_returned_values_refuse_before_modifying_env(monkeypatch, tmp_path, secret):
    file_path = tmp_path / ".env"
    file_path.write_text(original_env())
    values = {**RETURNED_ENV, "GONG_CLIENT_SECRET": secret}
    monkeypatch.setattr(
        env.questionary, "select", lambda *_args, **_kwargs: pytest.fail("Unsafe value reached file prompt")
    )
    with pytest.raises(ValueError, match="Cannot safely write returned GONG_CLIENT_SECRET"):
        env.rewrite_env_files(str(tmp_path), ["gong"], env_values=values)
    assert file_path.read_text() == original_env() and not (tmp_path / ".env.arga-backup").exists()


@pytest.mark.parametrize("values", [None, {}, {"GONG_ACCESS_TOKEN": "token-only"}])
def test_direct_gong_rewrite_requires_coherent_runtime_values(monkeypatch, tmp_path, values):
    file_path = tmp_path / ".env"
    file_path.write_text(original_env())
    monkeypatch.setattr(
        env.questionary, "select", lambda *_args, **_kwargs: pytest.fail("Incomplete values reached prompt")
    )
    with pytest.raises(ValueError):
        env.rewrite_env_files(str(tmp_path), ["gong"], env_values=values)
    assert file_path.read_text() == original_env() and not (tmp_path / ".env.arga-backup").exists()


def test_other_wizards_keep_the_existing_rewrite_before_provision_order(monkeypatch, tmp_path):
    calls = []
    fake_wizard(monkeypatch, lambda *_args, **_kwargs: calls.append("provision") or {})
    monkeypatch.setattr(wizard, "select_twins", lambda *_args, **_kwargs: ["slack"])
    monkeypatch.setattr(wizard, "rewrite_env_files", lambda *_args, **_kwargs: calls.append("rewrite") or [])
    assert wizard.run_wizard(api_url="https://api.argalabs.com", cwd=str(tmp_path)) == 0
    assert calls == ["rewrite", "provision"]


def test_wizard_env_uses_saved_session_current_values_and_closes_client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    file_path = tmp_path / ".env"
    file_path.write_text(original_env())
    accept_env_prompts(monkeypatch, file_path)
    session.save_session(
        str(tmp_path), {"run_id": "run-gong", "api_url": "https://api.argalabs.com", "api_key": "arga-test"}
    )
    calls = []

    class Client:
        def __init__(self, api_url, *, api_key):
            assert api_url == "https://api.argalabs.com" and api_key == "arga-test"

        def get_twin_provision_status(self, run_id):
            calls.append(run_id)
            return copy.deepcopy(READY_STATUS)

        def close(self):
            calls.append("close")

    monkeypatch.setattr(main, "ApiClient", Client)
    monkeypatch.setattr(main, "load_api_key", lambda: "arga-test")
    monkeypatch.setattr(prompts, "select_twins", lambda: ["gong"])
    assert main.run_wizard_env(argparse.Namespace(no_shape_detect=True)) == 0
    assert calls == ["run-gong", "close"]
    assert f"GONG_API_BASE_URL={RETURNED_ENV['GONG_API_BASE_URL']}" in file_path.read_text()
    assert "GONG_ACCESS_TOKEN=scenario-access-token" in file_path.read_text()


def test_wizard_env_without_gong_session_leaves_real_config_intact(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    file_path = tmp_path / ".env"
    file_path.write_text(original_env())
    monkeypatch.setattr(prompts, "select_twins", lambda: ["gong"])
    monkeypatch.setattr(env, "rewrite_env_files", lambda *_args, **_kwargs: pytest.fail("Missing session rewritten"))
    with pytest.raises(main.CliError, match="No active session"):
        main.run_wizard_env(argparse.Namespace(no_shape_detect=True))
    assert file_path.read_text() == original_env() and not (tmp_path / ".env.arga-backup").exists()


@pytest.mark.parametrize(
    "saved",
    [
        None,
        [],
        {},
        {"api_url": "https://api.argalabs.com", "api_key": "arga-test"},
        {"api_url": "https://api.argalabs.com", "api_key": [], "run_id": "run-gong"},
    ],
)
def test_wizard_env_validates_saved_session_before_api_or_file_changes(monkeypatch, tmp_path, saved):
    monkeypatch.chdir(tmp_path)
    file_path = tmp_path / ".env"
    file_path.write_text(original_env())
    monkeypatch.setattr(prompts, "select_twins", lambda: ["gong"])
    monkeypatch.setattr(session, "load_session", lambda *_args: saved)
    monkeypatch.setattr(main, "ApiClient", lambda *_args, **_kwargs: pytest.fail("Malformed session reached API"))
    with pytest.raises(main.CliError, match="valid session"):
        main.run_wizard_env(argparse.Namespace(no_shape_detect=True))
    assert file_path.read_text() == original_env() and not (tmp_path / ".env.arga-backup").exists()
