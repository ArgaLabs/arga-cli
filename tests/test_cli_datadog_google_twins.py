from __future__ import annotations

from arga_cli.wizard import env
from arga_cli.wizard.constants import QUICKSTART_SUMMARIES, TWIN_CATALOG, TWIN_ENV_MAPPINGS


def test_datadog_twin_is_in_cli_catalog() -> None:
    assert TWIN_CATALOG["datadog"] == {
        "label": "Datadog",
        "port": 12136,
        "intercept_domains": ["api.datadoghq.com", "http-intake.logs.datadoghq.com"],
        "show_in_ui": True,
    }
    assert "Datadog REST and monitoring UI twin ready" in QUICKSTART_SUMMARIES["datadog"]


def test_datadog_env_vars_and_credential_shapes_use_twin_defaults() -> None:
    mapping = TWIN_ENV_MAPPINGS["datadog"]
    assert {"DD_API_KEY", "DD_APP_KEY", "DD_ACCESS_TOKEN"} <= set(mapping["token_vars"])
    assert env.resolve_env_var("DD_API_KEY", ["datadog"]) == {
        "twin": "datadog",
        "default_value": "ddapi_twin_0000000000000000000000000001",
    }
    assert env.resolve_env_var("DD_API_URL", ["datadog"]) == {
        "twin": "datadog",
        "default_value": "",
    }
    assert env.match_value_shape("ddapp_live_key", ["datadog"])["default_value"] == (
        "ddapp_twin_0000000000000000000000000001"
    )


def test_google_sheets_and_workspace_are_separate_cli_choices() -> None:
    assert TWIN_CATALOG["google_sheets"] == {
        "label": "Google Sheets",
        "port": 12137,
        "intercept_domains": ["sheets.googleapis.com"],
        "show_in_ui": False,
    }
    assert TWIN_CATALOG["google_workspace"] == {
        "label": "Google Workspace",
        "port": 12138,
        "intercept_domains": [
            "people.googleapis.com",
            "workspaceevents.googleapis.com",
            "script.googleapis.com",
            "pubsub.googleapis.com",
        ],
        "show_in_ui": False,
    }
    assert "GOOGLE_CLIENT_ID" in TWIN_ENV_MAPPINGS["google_sheets"]["token_vars"]
    assert "GOOGLE_CLIENT_SECRET" in TWIN_ENV_MAPPINGS["google_workspace"]["token_vars"]
    assert "GOOGLE_SHEETS_API_URL" in TWIN_ENV_MAPPINGS["google_sheets"]["url_vars"]
    assert "GOOGLE_WORKSPACE_API_URL" in TWIN_ENV_MAPPINGS["google_workspace"]["url_vars"]
