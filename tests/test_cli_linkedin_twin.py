from __future__ import annotations

from arga_cli.wizard import env
from arga_cli.wizard.constants import QUICKSTART_SUMMARIES, TWIN_CATALOG, TWIN_ENV_MAPPINGS


def test_linkedin_twin_is_in_cli_catalog() -> None:
    assert TWIN_CATALOG["linkedin"] == {
        "label": "LinkedIn",
        "port": 12124,
        "intercept_domains": ["api.linkedin.com", "www.linkedin.com", "linkedin.com", "media.licdn.com"],
        "show_in_ui": True,
    }
    assert "Client ID: linkedin-twin-client" in QUICKSTART_SUMMARIES["linkedin"]


def test_linkedin_env_vars_resolve_to_twin_defaults() -> None:
    mapping = TWIN_ENV_MAPPINGS["linkedin"]

    assert "LINKEDIN_ACCESS_TOKEN" in mapping["token_vars"]
    assert "LINKEDIN_API_URL" in mapping["url_vars"]
    assert env.resolve_env_var("LINKEDIN_CLIENT_ID", ["linkedin"]) == {
        "twin": "linkedin",
        "default_value": "linkedin-twin-client",
    }
    assert env.resolve_env_var("LINKEDIN_CLIENT_SECRET", ["linkedin"]) == {
        "twin": "linkedin",
        "default_value": "linkedin-twin-secret",
    }


def test_linkedin_token_shape_detection_matches_real_tokens() -> None:
    access_token = env.match_value_shape("AQXrealLinkedInAccessToken", ["linkedin"])

    assert access_token is not None
    assert access_token["twin"] == "linkedin"
