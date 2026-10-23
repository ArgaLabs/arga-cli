from __future__ import annotations

import pytest

from arga_cli import main, wizard
from arga_cli.wizard import env, prompts
from arga_cli.wizard.constants import QUICKSTART_SUMMARIES, TWIN_CATALOG, TWIN_ENV_MAPPINGS

EXPECTED_TWINS = {
    "twilio",
    "attio",
    "box",
    "calendly",
    "checkhq",
    "datadog",
    "discord",
    "documenso",
    "dropbox",
    "github",
    "gitlab",
    "gmail",
    "google_calendar",
    "google_docs",
    "google_drive",
    "google_sheets",
    "google_workspace",
    "hubspot",
    "jira",
    "kandji",
    "linear",
    "linkedin",
    "notion",
    "okta",
    "quickbooks",
    "resend",
    "salesforce",
    "slack",
    "slack_enterprise",
    "stripe",
    "trolley",
    "unified",
    "unstructured",
    "waterfall",
    "workday",
}


def test_bundled_wizard_catalog_covers_every_current_selectable_twin() -> None:
    assert set(TWIN_CATALOG) == EXPECTED_TWINS
    assert set(TWIN_ENV_MAPPINGS) == EXPECTED_TWINS
    assert set(QUICKSTART_SUMMARIES) == EXPECTED_TWINS


@pytest.mark.parametrize(
    ("key", "expected_default"),
    [
        ("TWILIO_ACCOUNT_SID", "AC" + "a" * 32),
        ("TWILIO_AUTH_TOKEN", "twilio-twin-auth-token"),
        ("TWILIO_API_KEY", "SK" + "b" * 32),
        ("TWILIO_API_SECRET", "twilio-twin-api-secret"),
        ("TWILIO_PHONE_NUMBER", "+15005550006"),
        ("TWILIO_OAUTH_CLIENT_ID", "twilio-twin-client"),
        ("TWILIO_OAUTH_CLIENT_SECRET", "twilio-twin-client-secret"),
        ("TWILIO_MESSAGING_BASE_URL", ""),
        ("TWILIO_VERIFY_BASE_URL", ""),
        ("TWILIO_VOICE_BASE_URL", ""),
        ("TWILIO_CONVERSATIONS_BASE_URL", ""),
    ],
)
def test_twilio_env_vars_resolve_only_when_selected(key: str, expected_default: str) -> None:
    assert env.resolve_env_var(key, ["twilio"]) == {"twin": "twilio", "default_value": expected_default}
    assert env.resolve_env_var(key, ["slack"]) is None


def test_twilio_catalog_routes_messaging_to_the_local_twin() -> None:
    assert TWIN_CATALOG["twilio"]["port"] == 12152
    assert any(host == "messaging.twilio.com" for host in TWIN_CATALOG["twilio"]["intercept_domains"])


def test_new_twin_credentials_resolve_to_local_defaults() -> None:
    assert env.resolve_env_var("GMAIL_ACCESS_TOKEN", ["gmail"]) == {
        "twin": "gmail",
        "default_value": "ya29.gmail-twin-owner",
    }
    assert env.resolve_env_var("DD_API_KEY", ["datadog"]) == {
        "twin": "datadog",
        "default_value": "ddapi_twin_0000000000000000000000000001",
    }
    assert env.resolve_env_var("OKTA_API_TOKEN", ["okta"]) == {
        "twin": "okta",
        "default_value": "00okta_twin_api_token",
    }


def test_select_twins_uses_server_catalog_and_groups_by_kind(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Answer:
        @staticmethod
        def ask() -> list[str]:
            return ["future_twin", "okta"]

    def fake_checkbox(message: str, *, choices: list[object], validate) -> Answer:
        captured.update(message=message, choices=choices, validate=validate)
        return Answer()

    monkeypatch.setattr(prompts.questionary, "checkbox", fake_checkbox)

    catalog = [
        {"name": "future_twin", "label": "Future Twin", "kind": "frontend", "show_in_ui": True},
        {"name": "okta", "label": "Okta", "kind": "backend", "show_in_ui": True},
    ]
    assert prompts.select_twins(catalog=catalog) == ["future_twin", "okta"]

    choices = captured["choices"]
    assert isinstance(choices, list)
    titles = [getattr(choice, "title", "") for choice in choices]
    values = [getattr(choice, "value", None) for choice in choices]
    api_only_index = titles.index("── API-only Twins ──")

    assert values.index("future_twin") < api_only_index
    assert values.index("okta") > api_only_index
    assert "slack" not in values


def test_run_wizard_passes_authoritative_catalog_to_selector(monkeypatch, tmp_path) -> None:
    catalog = [{"name": "future_twin", "label": "Future Twin", "kind": "frontend", "show_in_ui": True}]
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, api_url: str, *, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

        @staticmethod
        def get_me() -> dict:
            return {"billing_plan": "paid", "plan_limits": {}}

        @staticmethod
        def list_twins() -> list[dict]:
            return catalog

    def fake_select(max_twins: int | None, *, catalog: list[dict] | None) -> list[str]:
        captured.update(max_twins=max_twins, catalog=catalog)
        return []

    monkeypatch.setattr(main, "ApiClient", FakeClient)
    monkeypatch.setattr(wizard, "prompt_api_key", lambda api_url, api_key: "arga_test_key")
    monkeypatch.setattr(wizard, "select_twins", fake_select)

    assert wizard.run_wizard(api_url="https://api.example.com", cwd=str(tmp_path)) == 1
    assert captured == {"max_twins": None, "catalog": catalog}
