from __future__ import annotations

from arga_cli.wizard.constants import TWIN_CATALOG


def test_cli_twin_catalog_matches_validation_server_surface_snapshot() -> None:
    assert TWIN_CATALOG == {
        "box": {
            "label": "Box",
            "port": 12116,
            "intercept_domains": ["api.box.com", "upload.box.com", "app.box.com"],
            "show_in_ui": True,
        },
        "discord": {
            "label": "Discord",
            "port": 12110,
            "intercept_domains": ["discord.com", "api.discord.com", "discordapp.com"],
            "show_in_ui": True,
        },
        "dropbox": {
            "label": "Dropbox",
            "port": 12119,
            "intercept_domains": ["api.dropboxapi.com", "content.dropboxapi.com", "notify.dropboxapi.com"],
            "show_in_ui": True,
        },
        "github": {
            "label": "GitHub",
            "port": 12120,
            "intercept_domains": ["api.github.com", "github.com"],
            "show_in_ui": True,
        },
        "gitlab": {
            "label": "GitLab",
            "port": 12127,
            "intercept_domains": ["gitlab.com"],
            "show_in_ui": True,
        },
        "gmail": {
            "label": "Gmail",
            "port": 12123,
            "intercept_domains": ["gmail.googleapis.com", "gmailmcp.googleapis.com", "people.googleapis.com"],
            "show_in_ui": True,
        },
        "google_calendar": {
            "label": "Google Calendar",
            "port": 12117,
            "intercept_domains": ["www.googleapis.com/calendar/v3"],
            "show_in_ui": True,
        },
        "google_drive": {
            "label": "Google Drive",
            "port": 12115,
            "intercept_domains": ["www.googleapis.com/drive/v3", "content.googleapis.com"],
            "show_in_ui": True,
        },
        "jira": {
            "label": "Jira",
            "port": 12122,
            "intercept_domains": ["atlassian.net", "auth.atlassian.com", "api.atlassian.com"],
            "show_in_ui": True,
        },
        "hubspot": {
            "label": "HubSpot",
            "port": 12128,
            "intercept_domains": ["api.hubapi.com", "api.hsforms.com", "app.hubspot.com"],
            "show_in_ui": True,
        },
        "linkedin": {
            "label": "LinkedIn",
            "port": 12124,
            "intercept_domains": ["api.linkedin.com", "www.linkedin.com", "linkedin.com", "media.licdn.com"],
            "show_in_ui": True,
        },
        "linear": {
            "label": "Linear",
            "port": 12126,
            "intercept_domains": ["api.linear.app", "linear.app"],
            "show_in_ui": True,
        },
        "notion": {
            "label": "Notion",
            "port": 12114,
            "intercept_domains": ["api.notion.com", "notion.so"],
            "show_in_ui": True,
        },
        "salesforce": {
            "label": "Salesforce",
            "port": 12125,
            "intercept_domains": ["login.salesforce.com", "test.salesforce.com", "my.salesforce.com"],
            "show_in_ui": True,
        },
        "slack": {
            "label": "Slack",
            "port": 12112,
            "intercept_domains": ["api.slack.com", "slack.com", "files.slack.com"],
            "show_in_ui": True,
        },
        "stripe": {
            "label": "Stripe",
            "port": 12111,
            "intercept_domains": ["api.stripe.com", "files.stripe.com", "connect.stripe.com"],
            "show_in_ui": True,
        },
        "unified": {
            "label": "Unified",
            "port": 12113,
            "intercept_domains": ["api.unified.to", "unified.to"],
            "show_in_ui": True,
        },
        "unstructured": {
            "label": "Unstructured",
            "port": 12118,
            "intercept_domains": ["api.unstructuredapp.io", "platform.unstructuredapp.io"],
            "show_in_ui": True,
        },
        "waterfall": {
            "label": "Waterfall",
            "port": 12129,
            "intercept_domains": ["api.waterfall.io"],
            "show_in_ui": True,
        },
    }
