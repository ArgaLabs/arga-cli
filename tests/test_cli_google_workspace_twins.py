from __future__ import annotations

from arga_cli import main
from arga_cli.wizard import env, prompts
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
    assert TWIN_CATALOG["google_workspace"] == {
        "label": "Google Workspace",
        "port": 12138,
        "intercept_domains": ["people.googleapis.com", "workspaceevents.googleapis.com"],
        "show_in_ui": False,
    }
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
        assert "GOOGLE_ACCESS_TOKEN" in TWIN_ENV_MAPPINGS[twin]["token_vars"]
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


def test_wizard_groups_google_editors_under_api_and_ui(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Answer:
        @staticmethod
        def ask() -> list[str]:
            return ["google_docs", "google_sheets"]

    def fake_checkbox(message: str, *, choices: list[object], validate) -> Answer:
        captured.update(message=message, choices=choices, validate=validate)
        return Answer()

    monkeypatch.setattr(prompts.questionary, "checkbox", fake_checkbox)

    assert prompts.select_twins() == ["google_docs", "google_sheets"]

    choices = captured["choices"]
    assert isinstance(choices, list)
    titles = [getattr(choice, "title", "") for choice in choices]
    values = [getattr(choice, "value", None) for choice in choices]
    api_only_index = titles.index("── API-only Twins ──")

    assert titles[0] == "── API + UI Twins (interactive browser interface) ──"
    assert values.index("google_docs") < api_only_index
    assert values.index("google_sheets") < api_only_index
    assert values.index("google_workspace") > api_only_index
