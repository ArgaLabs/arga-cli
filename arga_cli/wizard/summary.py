"""Print the final summary and save session state."""

from __future__ import annotations

from datetime import datetime

from arga_cli.wizard.constants import DASHBOARD_BASE_URL, SESSION_FILE, TWIN_CATALOG
from arga_cli.wizard.output import dim, print_summary_box
from arga_cli.wizard.provision import with_proxy_token
from arga_cli.wizard.session import save_session


def print_summary(cwd: str, status: dict, api_url: str, api_key: str) -> None:
    """Print the final summary and write the session state file."""
    dashboard_url = status.get("dashboard_url") or f"{DASHBOARD_BASE_URL}/runs/{status['run_id']}"
    proxy_token = status.get("proxy_token")

    lines = [
        "[bold green]Arga Twins \u2014 Ready![/bold green]",
        "",
        f"Dashboard: [underline]{dashboard_url}[/underline]",
        "",
    ]

    # Twin URLs
    for name, info in status.get("twins", {}).items():
        label = TWIN_CATALOG.get(name, {}).get("label", name).ljust(16)
        url = with_proxy_token(info.get("base_url", ""), proxy_token)
        lines.append(f"{label} [underline]{url}[/underline]")

    lines.append("")

    if status.get("expires_at"):
        lines.append(f"Session expires: {status['expires_at']}")
        lines.append("")

    lines.append("Commands:")
    lines.append("  [cyan]arga wizard status[/cyan]      Check health")
    lines.append("  [cyan]arga wizard reset[/cyan]       Reset twin state")
    lines.append("  [cyan]arga wizard extend[/cyan]      Extend by 10 min")
    lines.append("  [cyan]arga wizard teardown[/cyan]    Destroy session")

    print_summary_box(lines)

    # Write session state
    session = {
        "run_id": status["run_id"],
        "created_at": datetime.now().isoformat(),
        "expires_at": status.get("expires_at"),
        "api_url": api_url,
        "api_key": api_key,
        "proxy_token": proxy_token,
        "twins": {
            name: {"base_url": info.get("base_url", ""), "admin_url": info.get("admin_url", "")}
            for name, info in status.get("twins", {}).items()
        },
    }

    save_session(cwd, session)
    dim(f"Session saved to {SESSION_FILE}")
