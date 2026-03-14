from __future__ import annotations

import json

from arga_cli import mcp


def test_detect_installed_targets_uses_existing_config_dirs(tmp_path) -> None:
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".config" / "codex").mkdir(parents=True)

    detected = mcp.detect_installed_targets(home=tmp_path)

    assert [target.label for target in detected] == ["Cursor", "Claude Code", "Codex CLI"]


def test_merge_mcp_config_preserves_existing_servers() -> None:
    existing = {
        "mcpServers": {
            "existing-server": {
                "url": "https://example.com/mcp",
            }
        },
        "other": True,
    }

    merged = mcp.merge_mcp_config(
        existing,
        mcp.build_mcp_config("https://api.argalabs.com", "arga_sk_test"),
    )

    assert merged["other"] is True
    assert merged["mcpServers"]["existing-server"]["url"] == "https://example.com/mcp"
    assert merged["mcpServers"]["arga-context"]["url"] == "https://api.argalabs.com/mcp"


def test_install_mcp_configuration_writes_detected_targets_and_reports_status(tmp_path) -> None:
    (tmp_path / ".cursor").mkdir()
    codex_dir = tmp_path / ".config" / "codex"
    codex_dir.mkdir(parents=True)
    (codex_dir / "mcp.json").write_text(json.dumps({"mcpServers": {"existing": {"url": "https://example.com"}}}))

    output: list[str] = []
    installed, failures = mcp.install_mcp_configuration(
        api_url="https://api.argalabs.com",
        api_key="arga_sk_test",
        home=tmp_path,
        echo=output.append,
    )

    assert installed == 2
    assert failures == 0
    assert output == [
        "Detected:",
        "✓ Cursor",
        "✓ Codex CLI",
        "",
        "Installing MCP configuration...",
        "",
        "✓ Cursor configured",
        "✓ Codex CLI configured",
    ]

    cursor_config = json.loads((tmp_path / ".cursor" / "mcp.json").read_text())
    assert cursor_config["mcpServers"]["arga-context"]["headers"]["Authorization"] == "Bearer arga_sk_test"

    codex_config = json.loads((codex_dir / "mcp.json").read_text())
    assert codex_config["mcpServers"]["existing"]["url"] == "https://example.com"
    assert codex_config["mcpServers"]["arga-context"]["url"] == "https://api.argalabs.com/mcp"


def test_install_mcp_configuration_returns_zero_when_no_targets_detected(tmp_path) -> None:
    output: list[str] = []

    installed, failures = mcp.install_mcp_configuration(
        api_url="https://api.argalabs.com",
        api_key="arga_sk_test",
        home=tmp_path,
        echo=output.append,
    )

    assert installed == 0
    assert failures == 0
    assert output == [
        "Detected:",
        "No supported IDE agents detected.",
    ]
