"""arga init — scan a repository and generate arga.yaml."""

from __future__ import annotations

import json
from pathlib import Path

INTEGRATION_PATTERNS: dict[str, dict] = {
    "stripe": {
        "packages": ["stripe", "@stripe/stripe-js", "@stripe/react-stripe-js"],
        "env_vars": ["STRIPE_SECRET_KEY", "STRIPE_API_KEY", "STRIPE_KEY", "STRIPE_PUBLISHABLE_KEY"],
        "twin": "stripe",
    },
    "slack": {
        "packages": ["slack-sdk", "@slack/bolt", "@slack/web-api", "slack_sdk", "slack-bolt"],
        "env_vars": ["SLACK_BOT_TOKEN", "SLACK_TOKEN", "SLACK_API_TOKEN", "SLACK_SIGNING_SECRET", "SLACK_WEBHOOK_URL"],
        "twin": "slack",
    },
    "discord": {
        "packages": ["discord.py", "discord.js", "discordjs", "discord"],
        "env_vars": ["DISCORD_TOKEN", "DISCORD_BOT_TOKEN", "DISCORD_CLIENT_ID"],
        "twin": "discord",
    },
    "notion": {
        "packages": ["@notionhq/client", "notion-client"],
        "env_vars": ["NOTION_API_KEY", "NOTION_TOKEN", "NOTION_INTEGRATION_TOKEN"],
        "twin": "notion",
    },
    "google_drive": {
        "packages": ["googleapis", "@googleapis/drive", "google-api-python-client"],
        "env_vars": ["GOOGLE_DRIVE_TOKEN", "GOOGLE_ACCESS_TOKEN", "GOOGLE_CLIENT_ID"],
        "twin": "google_drive",
    },
    "dropbox": {
        "packages": ["dropbox"],
        "env_vars": ["DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_ACCESS_TOKEN", "DROPBOX_TOKEN"],
        "twin": "dropbox",
    },
    "box": {
        "packages": ["box-sdk-gen", "boxsdk", "box-node-sdk"],
        "env_vars": ["BOX_CLIENT_ID", "BOX_CLIENT_SECRET", "BOX_DEVELOPER_TOKEN"],
        "twin": "box",
    },
    "google_calendar": {
        "packages": ["@googleapis/calendar"],
        "env_vars": ["GOOGLE_CALENDAR_TOKEN"],
        "twin": "google_calendar",
    },
    "unstructured": {
        "packages": ["unstructured", "unstructured-client"],
        "env_vars": ["UNSTRUCTURED_API_KEY"],
        "twin": "unstructured",
    },
}


def detect_integrations(repo_root: Path) -> list[dict]:
    """Scan repo for integration patterns. Returns list of detected integrations."""
    detected: list[dict] = []

    # 1. Scan package files
    _scan_package_json(repo_root, detected)
    _scan_requirements_txt(repo_root, detected)
    _scan_pyproject_toml(repo_root, detected)

    # 2. Scan env files
    _scan_env_files(repo_root, detected)

    # 3. Deduplicate by integration name
    seen: set[str] = set()
    unique: list[dict] = []
    for d in detected:
        if d["name"] not in seen:
            seen.add(d["name"])
            unique.append(d)

    return unique


def _scan_package_json(root: Path, detected: list[dict]) -> None:
    pkg = root / "package.json"
    if not pkg.exists():
        return
    try:
        data = json.loads(pkg.read_text())
    except (json.JSONDecodeError, OSError):
        return
    all_deps: set[str] = set()
    for key in ("dependencies", "devDependencies"):
        all_deps.update(data.get(key, {}).keys())
    for name, info in INTEGRATION_PATTERNS.items():
        for pkg_name in info["packages"]:
            if pkg_name in all_deps:
                detected.append(
                    {
                        "name": name,
                        "twin": info["twin"],
                        "env_var": info["env_vars"][0] if info["env_vars"] else None,
                        "source": f"package.json ({pkg_name})",
                        "confidence": "high",
                    }
                )
                break


def _scan_requirements_txt(root: Path, detected: list[dict]) -> None:
    for fname in ("requirements.txt", "requirements-dev.txt"):
        req_file = root / fname
        if not req_file.exists():
            continue
        try:
            lines = req_file.read_text().splitlines()
        except OSError:
            continue
        pkg_names: set[str] = set()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                # Extract package name (before ==, >=, etc.)
                pkg = line.split("==")[0].split(">=")[0].split("<=")[0].split("[")[0].strip()
                pkg_names.add(pkg.lower())
        for name, info in INTEGRATION_PATTERNS.items():
            for pkg_name in info["packages"]:
                if pkg_name.lower() in pkg_names:
                    detected.append(
                        {
                            "name": name,
                            "twin": info["twin"],
                            "env_var": info["env_vars"][0] if info["env_vars"] else None,
                            "source": f"{fname} ({pkg_name})",
                            "confidence": "high",
                        }
                    )
                    break


def _scan_pyproject_toml(root: Path, detected: list[dict]) -> None:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return
    try:
        content = pyproject.read_text()
    except OSError:
        return
    # Simple text scan — no toml parser dependency needed
    content_lower = content.lower()
    for name, info in INTEGRATION_PATTERNS.items():
        for pkg_name in info["packages"]:
            if pkg_name.lower() in content_lower:
                detected.append(
                    {
                        "name": name,
                        "twin": info["twin"],
                        "env_var": info["env_vars"][0] if info["env_vars"] else None,
                        "source": f"pyproject.toml ({pkg_name})",
                        "confidence": "medium",
                    }
                )
                break


def _scan_env_files(root: Path, detected: list[dict]) -> None:
    env_names = [".env", ".env.example", ".env.local", ".env.development", ".env.staging"]
    env_vars_found: set[str] = set()
    for env_name in env_names:
        env_file = root / env_name
        if not env_file.exists():
            continue
        try:
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    var_name = line.split("=", 1)[0].strip()
                    env_vars_found.add(var_name)
        except OSError:
            continue

    for name, info in INTEGRATION_PATTERNS.items():
        for env_var in info["env_vars"]:
            if env_var in env_vars_found:
                detected.append(
                    {
                        "name": name,
                        "twin": info["twin"],
                        "env_var": env_var,
                        "source": f"env file ({env_var})",
                        "confidence": "high",
                    }
                )
                break


def _yaml_escape(value: str) -> str:
    """Escape a string value for YAML output if needed."""
    if not value:
        return '""'
    # Quote if the value contains special characters
    needs_quoting = any(ch in value for ch in ":{}\n\t\"'[]&*!|>%@`")
    if needs_quoting:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def generate_arga_yaml(integrations: list[dict], staging_url: str | None = None) -> str:
    """Generate arga.yaml content from detected integrations."""
    lines: list[str] = ["version: 1"]

    if staging_url:
        lines.append("staging:")
        lines.append(f"  url: {_yaml_escape(staging_url)}")

    if integrations:
        lines.append("integrations:")
        for i in integrations:
            lines.append(f"  - name: {_yaml_escape(i['name'])}")
            lines.append(f"    twin: {_yaml_escape(i['twin'])}")
            if i.get("env_var"):
                lines.append(f"    env_var: {_yaml_escape(i['env_var'])}")

    lines.append("")  # trailing newline
    return "\n".join(lines)


def _parse_yaml_value(raw: str) -> str | int | bool | None:
    """Parse a simple YAML scalar value."""
    raw = raw.strip()
    if not raw:
        return None
    # Handle quoted strings
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    # Handle booleans
    if raw.lower() in ("true", "yes"):
        return True
    if raw.lower() in ("false", "no"):
        return False
    # Handle integers
    try:
        return int(raw)
    except ValueError:
        pass
    return raw


def _parse_simple_yaml(text: str) -> dict:
    """Minimal YAML parser for arga.yaml — supports top-level keys, nested mappings, and lists of mappings."""
    result: dict = {}
    lines = text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        indent = len(line) - len(line.lstrip())

        if indent == 0 and ":" in stripped:
            key, _, rest = stripped.partition(":")
            key = key.strip()
            rest = rest.strip()

            if rest:
                # Simple key: value
                result[key] = _parse_yaml_value(rest)
                i += 1
            else:
                # Check what follows: list or nested mapping
                i += 1
                # Peek ahead to determine structure
                if i < len(lines):
                    next_stripped = lines[i].strip()
                    if next_stripped.startswith("- "):
                        # List of mappings
                        items: list[dict] = []
                        while i < len(lines):
                            ls = lines[i].strip()
                            if not ls or ls.startswith("#"):
                                i += 1
                                continue
                            li = len(lines[i]) - len(lines[i].lstrip())
                            if li == 0:
                                break  # Back to top level
                            if ls.startswith("- "):
                                item: dict = {}
                                # Parse "- key: value"
                                first_pair = ls[2:].strip()
                                if ":" in first_pair:
                                    k, _, v = first_pair.partition(":")
                                    item[k.strip()] = _parse_yaml_value(v)
                                i += 1
                                # Parse continuation keys at deeper indent
                                while i < len(lines):
                                    cls = lines[i].strip()
                                    if not cls or cls.startswith("#"):
                                        i += 1
                                        continue
                                    ci = len(lines[i]) - len(lines[i].lstrip())
                                    if ci <= li and not cls.startswith("- "):
                                        break
                                    if cls.startswith("- "):
                                        break  # Next list item
                                    if ":" in cls:
                                        k, _, v = cls.partition(":")
                                        item[k.strip()] = _parse_yaml_value(v)
                                    i += 1
                                items.append(item)
                            else:
                                i += 1
                        result[key] = items
                    elif ":" in next_stripped:
                        # Nested mapping
                        nested: dict = {}
                        while i < len(lines):
                            ls = lines[i].strip()
                            if not ls or ls.startswith("#"):
                                i += 1
                                continue
                            li = len(lines[i]) - len(lines[i].lstrip())
                            if li == 0:
                                break
                            if ":" in ls:
                                k, _, v = ls.partition(":")
                                nested[k.strip()] = _parse_yaml_value(v)
                            i += 1
                        result[key] = nested
                    else:
                        i += 1
        else:
            i += 1

    return result


def load_arga_yaml(repo_root: Path) -> dict | None:
    """Load arga.yaml from repo root, or None if not found."""
    for name in ("arga.yaml", "arga.yml"):
        path = repo_root / name
        if path.exists():
            try:
                return _parse_simple_yaml(path.read_text())
            except OSError:
                return None
    return None
