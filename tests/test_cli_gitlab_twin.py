from __future__ import annotations

from arga_cli.wizard import env
from arga_cli.wizard.constants import QUICKSTART_SUMMARIES, TWIN_CATALOG, TWIN_ENV_MAPPINGS


def test_gitlab_twin_is_in_cli_catalog() -> None:
    assert TWIN_CATALOG["gitlab"] == {
        "label": "GitLab",
        "port": 12127,
        "intercept_domains": ["gitlab.com"],
        "show_in_ui": True,
    }
    assert "Token: glpat-gitlab-twin-token" in QUICKSTART_SUMMARIES["gitlab"]


def test_gitlab_env_vars_resolve_to_twin_defaults() -> None:
    mapping = TWIN_ENV_MAPPINGS["gitlab"]

    assert "GITLAB_TOKEN" in mapping["token_vars"]
    assert "GITLAB_PRIVATE_TOKEN" in mapping["token_vars"]
    assert "GL_TOKEN" in mapping["token_vars"]
    assert "GITLAB_API_URL" in mapping["url_vars"]
    assert "CI_SERVER_URL" in mapping["url_vars"]
    assert env.resolve_env_var("GITLAB_TOKEN", ["gitlab"]) == {
        "twin": "gitlab",
        "default_value": "glpat-gitlab-twin-token",
    }
    assert env.resolve_env_var("GITLAB_PRIVATE_TOKEN", ["gitlab"]) == {
        "twin": "gitlab",
        "default_value": "glpat-gitlab-twin-token",
    }
    assert env.resolve_env_var("GITLAB_API_URL", ["gitlab"]) == {
        "twin": "gitlab",
        "default_value": "",
    }


def test_gitlab_token_shape_detection_rewrites_real_tokens() -> None:
    personal_access_token = env.match_value_shape("glpat-real-user-token", ["gitlab"])
    service_account_token = env.match_value_shape("glsoat-real-service-token", ["gitlab"])

    assert personal_access_token is not None
    assert personal_access_token["twin"] == "gitlab"
    assert personal_access_token["default_value"] == "glpat-gitlab-twin-token"
    assert service_account_token is not None
    assert service_account_token["twin"] == "gitlab"
