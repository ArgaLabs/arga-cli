from __future__ import annotations

from arga_cli.wizard import env
from arga_cli.wizard.constants import QUICKSTART_SUMMARIES, TWIN_CATALOG, TWIN_ENV_MAPPINGS


def test_datadog_twin_is_in_cli_catalog() -> None:
    assert TWIN_CATALOG["datadog"] == {
        "label": "Datadog",
        "port": 12136,
        "intercept_domains": [
            "api.datadoghq.com",
            "api.datadoghq.eu",
            "api.us3.datadoghq.com",
            "api.us5.datadoghq.com",
            "api.ap1.datadoghq.com",
            "api.ap2.datadoghq.com",
            "api.ddog-gov.com",
            "api.us2.ddog-gov.com",
            "api.uk1.datadoghq.com",
            "api.datad0g.com",
            "intake.synthetics.datadoghq.com",
            "http-intake.logs.datadoghq.com",
            "http-intake.logs.datadoghq.eu",
            "http-intake.logs.us3.datadoghq.com",
            "http-intake.logs.us5.datadoghq.com",
            "http-intake.logs.ap1.datadoghq.com",
            "http-intake.logs.ap2.datadoghq.com",
            "http-intake.logs.ddog-gov.com",
            "http-intake.logs.us2.ddog-gov.com",
            "http-intake.logs.uk1.datadoghq.com",
            "http-intake.logs.datad0g.com",
        ],
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
