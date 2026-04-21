"""Print the final summary and save session state."""

from __future__ import annotations

from datetime import datetime

from arga_cli.wizard.constants import DASHBOARD_BASE_URL, SESSION_FILE, TWIN_CATALOG
from arga_cli.wizard.output import console, dim, print_summary_box
from arga_cli.wizard.session import save_session


def print_summary(cwd: str, status: dict, api_url: str, api_key: str, scenario_id: str | None = None) -> None:
    """Print the final summary and write the session state file."""
    dashboard_url = status.get("dashboard_url") or f"{DASHBOARD_BASE_URL}/runs/{status['run_id']}"
    proxy_token = status.get("proxy_token")

    lines = [
        "[bold green]Arga Twins \u2014 Ready![/bold green]",
        "",
        "Commands:",
        "  [cyan]arga wizard status[/cyan]      Check health",
        "  [cyan]arga wizard reset[/cyan]       Reset twin state",
        "  [cyan]arga wizard extend[/cyan]      Extend by 10 min",
        "  [cyan]arga wizard teardown[/cyan]    Destroy session",
    ]

    print_summary_box(lines)

    console.print(f"Dashboard: [underline]{dashboard_url}[/underline]", soft_wrap=True, overflow="ignore")
    console.print()

    for name, info in status.get("twins", {}).items():
        label = TWIN_CATALOG.get(name, {}).get("label", name)
        url = info.get("base_url", "")
        console.print(
            f"  [bold cyan]{label}[/bold cyan]: [underline]{url}[/underline]", soft_wrap=True, overflow="ignore"
        )

    if status.get("expires_at"):
        console.print()
        dim(f"Session expires: {status['expires_at']}")

    console.print()

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
    if scenario_id is not None:
        session["scenario_id"] = scenario_id

    save_session(cwd, session)
    dim(f"Session saved to {SESSION_FILE}")
