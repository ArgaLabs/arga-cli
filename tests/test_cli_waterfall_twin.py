from __future__ import annotations

from arga_cli.wizard import env
from arga_cli.wizard.constants import QUICKSTART_SUMMARIES, TWIN_CATALOG, TWIN_ENV_MAPPINGS


def test_waterfall_twin_is_in_cli_catalog() -> None:
    assert TWIN_CATALOG["waterfall"] == {
        "label": "Waterfall",
        "port": 12129,
        "intercept_domains": ["api.waterfall.io"],
        "show_in_ui": True,
    }
    assert "API key: ad18e456-0dd7-45e1-b094-43a0361aedfa" in QUICKSTART_SUMMARIES["waterfall"]


def test_waterfall_env_vars_resolve_to_twin_defaults() -> None:
    mapping = TWIN_ENV_MAPPINGS["waterfall"]

    assert "WATERFALL_API_KEY" in mapping["token_vars"]
    assert "WATERFALL_API_BASE_URL" in mapping["url_vars"]
    assert env.resolve_env_var("WATERFALL_API_KEY", ["waterfall"]) == {
        "twin": "waterfall",
        "default_value": "ad18e456-0dd7-45e1-b094-43a0361aedfa",
    }
    assert env.resolve_env_var("WATERFALL_API_BASE_URL", ["waterfall"]) == {
        "twin": "waterfall",
        "default_value": "",
    }


def test_waterfall_api_key_shape_detection_rewrites_real_keys() -> None:
    api_key = env.match_value_shape("9c7a2e81-0d0a-4183-92ea-d013c1adf710", ["waterfall"])

    assert api_key is not None
    assert api_key["twin"] == "waterfall"
    assert api_key["default_value"] == "ad18e456-0dd7-45e1-b094-43a0361aedfa"
