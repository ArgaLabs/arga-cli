from __future__ import annotations

from arga_cli import main
from arga_cli.wizard import env
from arga_cli.wizard.constants import QUICKSTART_SUMMARIES, TWIN_CATALOG, TWIN_ENV_MAPPINGS


def test_google_workspace_services_are_independent_cli_twins() -> None:
    assert TWIN_CATALOG["google_docs"] == {
        "label": "Google Docs",
        "port": 12139,
        "intercept_domains": ["docs.googleapis.com", "www.googleapis.com/discovery/v1/apis/docs/v1/rest"],
        "show_in_ui": True,
    }
    assert TWIN_CATALOG["google_sheets"] == {
        "label": "Google Sheets",
        "port": 12137,
        "intercept_domains": ["sheets.googleapis.com", "www.googleapis.com/discovery/v1/apis/sheets/v4/rest"],
        "show_in_ui": True,
    }
    assert TWIN_CATALOG["google_workspace"]["port"] == 12138
    assert "Preset metadata" in QUICKSTART_SUMMARIES["google_drive"][1]
    assert "editor UI" in QUICKSTART_SUMMARIES["google_docs"][0]
    assert "google-docs-launch-notes" in QUICKSTART_SUMMARIES["google_docs"][1]
    assert "spreadsheet UI" in QUICKSTART_SUMMARIES["google_sheets"][0]
    assert "google-sheets-launch-plan" in QUICKSTART_SUMMARIES["google_sheets"][1]


def test_google_workspace_service_env_vars_share_auth_but_not_api_urls() -> None:
    assert TWIN_ENV_MAPPINGS["google_docs"]["url_vars"] == ["GOOGLE_DOCS_API_URL"]
    assert TWIN_ENV_MAPPINGS["google_sheets"]["url_vars"] == ["GOOGLE_SHEETS_API_URL"]
    assert TWIN_ENV_MAPPINGS["google_workspace"]["url_vars"] == ["GOOGLE_WORKSPACE_API_URL"]

    for twin in ("google_drive", "google_docs", "google_sheets", "google_workspace"):
        assert TWIN_ENV_MAPPINGS[twin]["defaults"]["GOOGLE_ACCESS_TOKEN"] == "ya29.drive-twin-owner"

    assert env.resolve_env_var("GOOGLE_DOCS_API_URL", ["google_docs"]) == {
        "twin": "google_docs",
        "default_value": "",
    }
    assert env.resolve_env_var("GOOGLE_SHEETS_API_URL", ["google_sheets"]) == {
        "twin": "google_sheets",
        "default_value": "",
    }


def test_twin_run_parser_accepts_all_google_editor_twins() -> None:
    args = main.build_parser().parse_args(
        [
            "twin-runs",
            "create",
            "--twins",
            "google_drive,google_docs,google_sheets",
            "--ttl",
            "60",
            "--wait",
        ]
    )

    assert args.twins == "google_drive,google_docs,google_sheets"
    assert args.ttl == 60
    assert args.wait is True
