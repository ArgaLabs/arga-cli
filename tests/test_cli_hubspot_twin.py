from __future__ import annotations

from arga_cli.wizard import env
from arga_cli.wizard.constants import QUICKSTART_SUMMARIES, TWIN_CATALOG, TWIN_ENV_MAPPINGS


def test_hubspot_twin_is_in_cli_catalog() -> None:
    assert TWIN_CATALOG["hubspot"] == {
        "label": "HubSpot",
        "port": 12128,
        "intercept_domains": ["api.hubapi.com", "api.hsforms.com", "app.hubspot.com"],
        "show_in_ui": True,
    }
    assert "Private app token: hubspot-twin-private-app-token" in QUICKSTART_SUMMARIES["hubspot"]


def test_hubspot_env_vars_resolve_to_twin_defaults() -> None:
    mapping = TWIN_ENV_MAPPINGS["hubspot"]

    assert "HUBSPOT_ACCESS_TOKEN" in mapping["token_vars"]
    assert "HUBSPOT_API_URL" in mapping["url_vars"]
    assert env.resolve_env_var("HUBSPOT_ACCESS_TOKEN", ["hubspot"]) == {
        "twin": "hubspot",
        "default_value": "hubspot-twin-access-token",
    }
    assert env.resolve_env_var("HUBSPOT_CLIENT_SECRET", ["hubspot"]) == {
        "twin": "hubspot",
        "default_value": "",
    }


def test_hubspot_token_shape_detection_rewrites_private_app_tokens() -> None:
    private_app_token = env.match_value_shape("".join(["pat", "-na1-real-user-token"]), ["hubspot"])

    assert private_app_token is not None
    assert private_app_token["twin"] == "hubspot"
    assert private_app_token["default_value"] == "hubspot-twin-private-app-token"
