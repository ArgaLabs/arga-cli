from __future__ import annotations

from arga_cli.wizard import env
from arga_cli.wizard.constants import (
    QUICKSTART_SUMMARIES,
    TWIN_CATALOG,
    TWIN_ENV_MAPPINGS,
)

DEFAULT_TOKEN = "00000000-0000-4000-8000-000000000001"


def test_kandji_twin_is_in_cli_catalog() -> None:
    assert TWIN_CATALOG["kandji"] == {
        "label": "Iru (Kandji)",
        "port": 12147,
        "intercept_domains": [
            "twin.api.iru.com",
            "twin.api.eu.iru.com",
            "twin.api.kandji.io",
            "twin.api.eu.kandji.io",
        ],
        "show_in_ui": True,
    }
    summary = QUICKSTART_SUMMARIES["kandji"]
    assert "Iru API URL: https://twin.api.iru.com" in summary
    assert "Kandji API URL: https://twin.api.kandji.io" in summary
    assert f"Token: {DEFAULT_TOKEN}" in summary


def test_kandji_env_vars_resolve_to_twin_defaults() -> None:
    mapping = TWIN_ENV_MAPPINGS["kandji"]
    token_vars = [
        "IRU_API_TOKEN",
        "IRUCTL_TOKEN",
        "IRUPKG_TOKEN",
        "IOTA_TOKEN",
        "KST_TOKEN",
        "KANDJI_TOKEN",
        "KANDJI_API_TOKEN",
    ]
    url_vars = [
        "IRU_API_URL",
        "IRU_API_BASE_URL",
        "IRUCTL_TENANT",
        "KST_TENANT",
        "KANDJI_API_URL",
        "KANDJI_API_BASE_URL",
        "KANDJI_TWIN_BASE_URL",
    ]

    assert mapping["token_vars"] == token_vars
    assert mapping["url_vars"] == url_vars
    for variable in token_vars:
        assert env.resolve_env_var(variable, ["kandji"]) == {
            "twin": "kandji",
            "default_value": DEFAULT_TOKEN,
        }
    for variable in url_vars:
        assert env.resolve_env_var(variable, ["kandji"]) == {
            "twin": "kandji",
            "default_value": "",
        }


def test_kandji_uuid_token_is_not_detected_by_value_alone() -> None:
    assert env.match_value_shape(DEFAULT_TOKEN, ["kandji"]) is None
