"""Twin catalog, env mappings, token shapes, and scenario summaries."""

from __future__ import annotations

SESSION_FILE = ".arga-session.json"
ENV_BACKUP_SUFFIX = ".arga-backup"
DASHBOARD_BASE_URL = "https://app.argalabs.com"

ENV_FILE_NAMES = [
    ".env",
    ".env.local",
    ".env.development",
    ".env.staging",
    ".env.test",
]

# ---------------------------------------------------------------------------
# Twin catalog
# ---------------------------------------------------------------------------

TWIN_CATALOG: dict[str, dict] = {
    "discord": {
        "label": "Discord",
        "port": 12110,
        "intercept_domains": ["discord.com", "api.discord.com", "discordapp.com"],
        "show_in_ui": True,
    },
    "slack": {
        "label": "Slack",
        "port": 12112,
        "intercept_domains": ["api.slack.com", "slack.com", "files.slack.com"],
        "show_in_ui": True,
    },
    "google_drive": {
        "label": "Google Drive",
        "port": 12115,
        "intercept_domains": ["www.googleapis.com/drive/v3", "content.googleapis.com"],
        "show_in_ui": True,
    },
    "dropbox": {
        "label": "Dropbox",
        "port": 12119,
        "intercept_domains": ["api.dropboxapi.com", "content.dropboxapi.com", "notify.dropboxapi.com"],
        "show_in_ui": True,
    },
    "notion": {
        "label": "Notion",
        "port": 12114,
        "intercept_domains": ["api.notion.com", "notion.so"],
        "show_in_ui": True,
    },
    "github": {
        "label": "GitHub",
        "port": 12120,
        "intercept_domains": ["api.github.com", "github.com"],
        "show_in_ui": True,
    },
    "unstructured": {
        "label": "Unstructured",
        "port": 12118,
        "intercept_domains": ["api.unstructuredapp.io", "platform.unstructuredapp.io"],
        "show_in_ui": False,
    },
    "stripe": {
        "label": "Stripe",
        "port": 12111,
        "intercept_domains": ["api.stripe.com", "files.stripe.com", "connect.stripe.com"],
        "show_in_ui": True,
    },
    "box": {
        "label": "Box",
        "port": 12116,
        "intercept_domains": ["api.box.com", "upload.box.com", "app.box.com"],
        "show_in_ui": False,
    },
    "google_calendar": {
        "label": "Google Calendar",
        "port": 12117,
        "intercept_domains": ["www.googleapis.com/calendar/v3"],
        "show_in_ui": True,
    },
    "unified": {
        "label": "Unified",
        "port": 12113,
        "intercept_domains": ["api.unified.to", "unified.to"],
        "show_in_ui": False,
    },
}

# ---------------------------------------------------------------------------
# Environment variable mappings per twin
# ---------------------------------------------------------------------------

TWIN_ENV_MAPPINGS: dict[str, dict] = {
    "discord": {
        "token_vars": ["DISCORD_TOKEN", "DISCORD_BOT_TOKEN"],
        "url_vars": ["DISCORD_API_URL", "DISCORD_BASE_URL"],
        "secret_vars": [],
        "defaults": {"DISCORD_TOKEN": "fake-bot-token"},
    },
    "slack": {
        "token_vars": ["SLACK_BOT_TOKEN", "SLACK_TOKEN", "SLACK_API_TOKEN", "SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET"],
        "url_vars": ["SLACK_API_URL", "SLACK_BASE_URL", "SLACK_TWIN_BASE_URL"],
        "secret_vars": ["SLACK_SIGNING_SECRET"],
        "defaults": {
            "SLACK_BOT_TOKEN": "xoxb-F9SXMECOSFOGYR3XKXWN",
            "SLACK_SIGNING_SECRET": "slack-signing-secret",
        },
    },
    "stripe": {
        "token_vars": ["STRIPE_SECRET_KEY", "STRIPE_API_KEY", "STRIPE_KEY"],
        "url_vars": ["STRIPE_API_URL", "STRIPE_BASE_URL", "STRIPE_TWIN_BASE_URL"],
        "secret_vars": ["STRIPE_TWIN_WEBHOOK_SECRET"],
        "defaults": {},
    },
    "google_drive": {
        "token_vars": [
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "GOOGLE_DRIVE_TOKEN",
            "GOOGLE_ACCESS_TOKEN",
            "GOOGLE_DRIVE_ACCESS_TOKEN",
        ],
        "url_vars": ["GOOGLE_DRIVE_API_URL"],
        "secret_vars": [],
        "defaults": {
            "GOOGLE_CLIENT_ID": "google-twin-client-id",
            "GOOGLE_CLIENT_SECRET": "google-twin-client-secret",
            "GOOGLE_ACCESS_TOKEN": "ya29.drive-twin-owner",
        },
    },
    "dropbox": {
        "token_vars": ["DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_ACCESS_TOKEN", "DROPBOX_TOKEN"],
        "url_vars": ["DROPBOX_API_URL", "DROPBOX_BASE_URL"],
        "secret_vars": [],
        "defaults": {
            "DROPBOX_APP_KEY": "dropbox-twin-app-key",
            "DROPBOX_APP_SECRET": "dropbox-twin-app-secret",
        },
    },
    "notion": {
        "token_vars": ["NOTION_API_KEY", "NOTION_TOKEN", "NOTION_INTEGRATION_TOKEN"],
        "url_vars": ["NOTION_API_URL", "NOTION_BASE_URL"],
        "secret_vars": [],
        "defaults": {
            "NOTION_API_KEY": "secret_notion-twin_seed",
            "NOTION_TOKEN": "secret_notion-twin_seed",
        },
    },
    "github": {
        "token_vars": ["GITHUB_TOKEN", "GITHUB_ACCESS_TOKEN", "GH_TOKEN"],
        "url_vars": ["GITHUB_API_URL", "GITHUB_BASE_URL"],
        "secret_vars": [],
        "defaults": {"GITHUB_TOKEN": "ghp_test-github-twin-token"},
    },
    "box": {
        "token_vars": ["BOX_CLIENT_ID", "BOX_CLIENT_SECRET", "BOX_DEVELOPER_TOKEN", "BOX_ACCESS_TOKEN"],
        "url_vars": ["BOX_API_URL", "BOX_BASE_URL"],
        "secret_vars": [],
        "defaults": {
            "BOX_CLIENT_ID": "box-twin-client-id",
            "BOX_CLIENT_SECRET": "box-twin-client-secret",
            "BOX_DEVELOPER_TOKEN": "box-developer-token",
        },
    },
    "google_calendar": {
        "token_vars": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_CALENDAR_TOKEN", "GOOGLE_ACCESS_TOKEN"],
        "url_vars": ["GOOGLE_CALENDAR_API_URL"],
        "secret_vars": [],
        "defaults": {
            "GOOGLE_CLIENT_ID": "google-twin-client-id",
            "GOOGLE_CLIENT_SECRET": "google-twin-client-secret",
        },
    },
    "unified": {
        "token_vars": ["UNIFIED_API_KEY", "UNIFIED_TOKEN"],
        "url_vars": ["UNIFIED_API_URL", "UNIFIED_BASE_URL"],
        "secret_vars": [],
        "defaults": {},
    },
    "unstructured": {
        "token_vars": ["UNSTRUCTURED_API_KEY"],
        "url_vars": ["UNSTRUCTURED_API_URL", "UNSTRUCTURED_BASE_URL"],
        "secret_vars": [],
        "defaults": {"UNSTRUCTURED_API_KEY": "test-unstructured-key"},
    },
}

# ---------------------------------------------------------------------------
# Token shapes — for heuristic value-based detection
# ---------------------------------------------------------------------------

TOKEN_SHAPES: list[dict] = [
    # Slack
    {
        "twin": "slack",
        "label": "Slack bot token (xoxb-...)",
        "pattern": r"^xoxb-",
        "category": "token",
        "default_value": "xoxb-F9SXMECOSFOGYR3XKXWN",
        "confidence": "high",
    },
    {
        "twin": "slack",
        "label": "Slack user token (xoxp-...)",
        "pattern": r"^xoxp-",
        "category": "token",
        "default_value": "xoxb-F9SXMECOSFOGYR3XKXWN",
        "confidence": "high",
    },
    {
        "twin": "slack",
        "label": "Slack app token (xapp-...)",
        "pattern": r"^xapp-",
        "category": "token",
        "default_value": "xoxb-F9SXMECOSFOGYR3XKXWN",
        "confidence": "high",
    },
    # Stripe
    {
        "twin": "stripe",
        "label": "Stripe secret key (sk_live/sk_test)",
        "pattern": r"^sk_(live|test)_",
        "category": "token",
        "default_value": "",
        "confidence": "high",
    },
    {
        "twin": "stripe",
        "label": "Stripe publishable key (pk_live/pk_test)",
        "pattern": r"^pk_(live|test)_",
        "category": "token",
        "default_value": "",
        "confidence": "high",
    },
    # Notion
    {
        "twin": "notion",
        "label": "Notion API key (ntn_...)",
        "pattern": r"^ntn_",
        "category": "token",
        "default_value": "secret_notion-twin_seed",
        "confidence": "high",
    },
    {
        "twin": "notion",
        "label": "Notion API key (secret_...)",
        "pattern": r"^secret_[A-Za-z0-9]",
        "category": "token",
        "default_value": "secret_notion-twin_seed",
        "confidence": "medium",
    },
    # Google OAuth
    {
        "twin": "google_drive",
        "label": "Google OAuth client ID (*.apps.googleusercontent.com)",
        "pattern": r"\.apps\.googleusercontent\.com$",
        "category": "token",
        "default_value": "google-twin-client-id",
        "confidence": "high",
    },
    # Dropbox
    {
        "twin": "dropbox",
        "label": "Dropbox access token (sl....)",
        "pattern": r"^sl\.",
        "category": "token",
        "default_value": "dropbox-twin-app-key",
        "confidence": "high",
    },
]

# ---------------------------------------------------------------------------
# Quickstart scenario summaries
# ---------------------------------------------------------------------------

QUICKSTART_SUMMARIES: dict[str, list[str]] = {
    "discord": [
        'Server: "Discord Twin Server"',
        "Channels: #general, #random, #voice",
        "Users: twin-bot (bot), twin-user",
        "Roles: @everyone, Admin",
        "Bot token: fake-bot-token",
    ],
    "slack": [
        'Workspace: "Slack Twin Workspace"',
        "Channels: #returns-demo, #general",
        "Users: slack-twin-bot (bot), slack-twin-user",
        "Bot token: xoxb-F9SXMECOSFOGYR3XKXWN",
        "User token: xoxp-slack-twin-user-token",
    ],
    "google_drive": [
        "Principals: Drive Twin Owner, Drive Twin Editor",
        'Seed files: "Quarterly Plan.txt", "Reports" (folder)',
        "Owner token: ya29.drive-twin-owner",
        "Editor token: ya29.drive-twin-editor",
    ],
    "dropbox": [
        "Root folder initialized",
        "Default filesystem ready",
    ],
    "notion": [
        'Workspace: "Notion Twin Workspace"',
        "API key: secret_notion-twin_seed",
    ],
    "github": [
        'User: "testuser" (Test User)',
        'Organization: "test-org" (Test Organization)',
        'Repository: "test-org/demo-repo" (public, Python)',
        "Token: ghp_test-github-twin-token",
    ],
    "unstructured": [
        "Partition endpoint: /general/v0/general",
        "Jobs endpoint: /api/v1/jobs/",
        "API key: test-unstructured-key",
    ],
    "stripe": [
        "Stripe API emulator ready",
        "Supports charges, customers, subscriptions",
    ],
    "box": [
        'Enterprise: "Box Twin Enterprise" (id: 11446498)',
        "File/folder management ready",
        "Webhook and event stream support",
    ],
    "google_calendar": [
        "Calendar v3 API emulator ready",
        "Event CRUD operations supported",
    ],
    "unified": [
        "Unified API gateway ready",
        "Bridges to: Slack, Dropbox, Google Calendar, Notion, Google Drive",
    ],
}
