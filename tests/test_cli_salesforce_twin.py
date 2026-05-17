from __future__ import annotations

from arga_cli.wizard import env
from arga_cli.wizard.constants import QUICKSTART_SUMMARIES, TWIN_CATALOG, TWIN_ENV_MAPPINGS


def test_salesforce_twin_is_in_cli_catalog() -> None:
    assert TWIN_CATALOG["salesforce"] == {
        "label": "Salesforce",
        "port": 12125,
        "intercept_domains": ["login.salesforce.com", "test.salesforce.com", "my.salesforce.com"],
        "show_in_ui": False,
    }
    assert "Access token: 00D000000000001!salesforce-twin-token" in QUICKSTART_SUMMARIES["salesforce"]


def test_salesforce_env_vars_resolve_to_twin_defaults() -> None:
    mapping = TWIN_ENV_MAPPINGS["salesforce"]

    assert "SALESFORCE_ACCESS_TOKEN" in mapping["token_vars"]
    assert "SALESFORCE_INSTANCE_URL" in mapping["url_vars"]
    assert "SALESFORCE_CLIENT_SECRET" in mapping["secret_vars"]
    assert env.resolve_env_var("SALESFORCE_ACCESS_TOKEN", ["salesforce"]) == {
        "twin": "salesforce",
        "default_value": "00D000000000001!salesforce-twin-token",
    }
    assert env.resolve_env_var("SALESFORCE_CONSUMER_SECRET", ["salesforce"]) == {
        "twin": "salesforce",
        "default_value": "salesforce-twin-client-secret",
    }
    assert env.resolve_env_var("SALESFORCE_INSTANCE_URL", ["salesforce"]) == {
        "twin": "salesforce",
        "default_value": "",
    }


def test_salesforce_token_shape_detection_rewrites_real_tokens() -> None:
    session_token = env.match_value_shape("00D5f000000ABC1!AQ0AQExampleSession", ["salesforce"])
    consumer_key = env.match_value_shape("3MVG9exampleConnectedAppKey", ["salesforce"])

    assert session_token is not None
    assert session_token["twin"] == "salesforce"
    assert session_token["default_value"] == "00D000000000001!salesforce-twin-token"
    assert consumer_key is not None
    assert consumer_key["twin"] == "salesforce"
    assert consumer_key["default_value"] == "salesforce-twin-client-id"
