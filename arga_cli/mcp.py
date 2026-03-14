from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

SERVER_NAME = "arga-context"


@dataclass(frozen=True)
class McpTarget:
    key: str
    label: str
    config_path: Path


def get_targets(home: Path | None = None) -> list[McpTarget]:
    home = home or Path.home()
    return [
        McpTarget("cursor", "Cursor", home / ".cursor" / "mcp.json"),
        McpTarget("claude", "Claude Code", home / ".claude" / "mcp.json"),
        McpTarget("codex", "Codex CLI", home / ".config" / "codex" / "mcp.json"),
    ]


def build_mcp_config(api_url: str, api_key: str) -> dict[str, object]:
    return {
        "mcpServers": {
            SERVER_NAME: {
                "url": f"{api_url.rstrip('/')}/mcp",
                "headers": {
                    "Authorization": f"Bearer {api_key}",
                },
            }
        }
    }


def detect_installed_targets(home: Path | None = None) -> list[McpTarget]:
    detected: list[McpTarget] = []
    for target in get_targets(home):
        if target.config_path.exists() or target.config_path.parent.exists():
            detected.append(target)
    return detected


def load_existing_config(config_path: Path) -> dict[str, object]:
    if not config_path.exists():
        return {}

    try:
        data = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {config_path}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected top-level object in {config_path}")
    return data


def merge_mcp_config(existing: dict[str, object], mcp_config: dict[str, object]) -> dict[str, object]:
    merged = dict(existing)
    existing_servers = merged.get("mcpServers")
    if existing_servers is None:
        merged_servers: dict[str, object] = {}
    elif isinstance(existing_servers, dict):
        merged_servers = dict(existing_servers)
    else:
        raise ValueError("Expected `mcpServers` to be an object")

    new_servers = mcp_config.get("mcpServers")
    if not isinstance(new_servers, dict):
        raise ValueError("Generated MCP config is invalid")

    merged_servers.update(new_servers)
    merged["mcpServers"] = merged_servers
    return merged


def write_mcp_config(config_path: Path, config: dict[str, object]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config, indent=2) + "\n"
    temp_path = config_path.with_suffix(f"{config_path.suffix}.tmp")
    temp_path.write_text(payload)
    temp_path.replace(config_path)


def install_mcp_configuration(
    *,
    api_url: str,
    api_key: str,
    home: Path | None = None,
    echo: Callable[[str], None] = print,
) -> tuple[int, int]:
    detected = detect_installed_targets(home)

    echo("Detected:")
    if not detected:
        echo("No supported IDE agents detected.")
        return 0, 0

    for target in detected:
        echo(f"✓ {target.label}")

    echo("")
    echo("Installing MCP configuration...")
    echo("")

    installed = 0
    failures = 0
    generated_config = build_mcp_config(api_url, api_key)

    for target in detected:
        try:
            existing = load_existing_config(target.config_path)
            merged = merge_mcp_config(existing, generated_config)
            write_mcp_config(target.config_path, merged)
            echo(f"✓ {target.label} configured")
            installed += 1
        except ValueError as exc:
            echo(f"✗ {target.label} not configured: {exc}")
            failures += 1

    return installed, failures
