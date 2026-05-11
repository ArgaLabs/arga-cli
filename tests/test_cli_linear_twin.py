from __future__ import annotations

from arga_cli.wizard import env
from arga_cli.wizard.constants import QUICKSTART_SUMMARIES, TWIN_CATALOG, TWIN_ENV_MAPPINGS


def test_linear_twin_is_in_cli_catalog() -> None:
    assert TWIN_CATALOG["linear"] == {
        "label": "Linear",
        "port": 12126,
        "intercept_domains": ["api.linear.app", "linear.app"],
        "show_in_ui": True,
    }
    assert "Token: lin_api_twin_owner_personal_key_0001" in QUICKSTART_SUMMARIES["linear"]


def test_linear_env_vars_resolve_to_twin_defaults() -> None:
    mapping = TWIN_ENV_MAPPINGS["linear"]

    assert "LINEAR_API_KEY" in mapping["token_vars"]
    assert "LINEAR_GRAPHQL_URL" in mapping["url_vars"]
    assert env.resolve_env_var("LINEAR_API_KEY", ["linear"]) == {
        "twin": "linear",
        "default_value": "lin_api_twin_owner_personal_key_0001",
    }
    assert env.resolve_env_var("LINEAR_CLIENT_SECRET", ["linear"]) == {
        "twin": "linear",
        "default_value": "",
    }


def test_linear_token_shape_detection_rewrites_real_tokens() -> None:
    personal_key = env.match_value_shape("lin_api_real_user_key", ["linear"])
    oauth_token = env.match_value_shape("lin_oauth_real_access_token", ["linear"])

    assert personal_key is not None
    assert personal_key["twin"] == "linear"
    assert personal_key["default_value"] == "lin_api_twin_owner_personal_key_0001"
    assert oauth_token is not None
    assert oauth_token["twin"] == "linear"
