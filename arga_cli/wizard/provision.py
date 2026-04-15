"""Twin provisioning, polling, and seeding."""

from __future__ import annotations

import sys
import time
from typing import Any

from arga_cli.wizard.constants import QUICKSTART_SUMMARIES, TWIN_CATALOG
from arga_cli.wizard.output import console, dim, header


def with_proxy_token(url: str, proxy_token: str | None) -> str:
    """Append proxy token as query parameter to a URL."""
    if not proxy_token:
        return url
    from urllib.parse import urlparse, urlunparse

    try:
        parsed = urlparse(url)
        separator = "&" if parsed.query else ""
        new_query = f"{parsed.query}{separator}token={proxy_token}" if parsed.query else f"token={proxy_token}"
        return urlunparse(parsed._replace(query=new_query))
    except Exception:
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}token={proxy_token}"


def provision_twins(
    client: Any,
    twins: list[str],
    *,
    ttl_minutes: int = 10,
    scenario_prompt: str | None = None,
) -> dict:
    """Provision twins and poll until ready, showing progress."""
    header("Provisioning twin instances...")

    payload: dict[str, Any] = {"twins": twins, "ttl_minutes": ttl_minutes, "scenario": "quickstart"}
    if scenario_prompt:
        payload["scenario_prompt"] = scenario_prompt

    response = client._client.post(
        f"{client._api_url}/validate/twins/provision",
        json=payload,
        headers=client._auth_headers(),
    )
    data = client._parse_json(response, "Failed to provision twins")
    run_id = data["run_id"]
    dim(f"  Run ID: {run_id}")

    # Poll until ready
    ready_set: set[str] = set()
    deadline = time.monotonic() + 300  # 5 minute timeout
    interval = 3.0

    while time.monotonic() < deadline:
        status_response = client._client.get(
            f"{client._api_url}/validate/twins/provision/{run_id}/status",
            headers=client._auth_headers(),
        )
        status = client._parse_json(status_response, f"Failed to check provisioning status for run {run_id}")

        # Print progress as twins come online
        for name, info in status.get("twins", {}).items():
            if info.get("base_url") and name not in ready_set:
                ready_set.add(name)
                label = TWIN_CATALOG.get(name, {}).get("label", name)
                idx = len(ready_set)
                sys.stdout.write(f"  [{idx}/{len(twins)}] {label} twin .".ljust(40) + " ready\n")
                sys.stdout.flush()

        if status.get("status") == "ready":
            # Print any twins we didn't see in progress
            for name in twins:
                if name not in ready_set:
                    label = TWIN_CATALOG.get(name, {}).get("label", name)
                    sys.stdout.write(f"  {label} twin ".ljust(40) + " ready\n")
                    sys.stdout.flush()

            if status.get("expires_at"):
                try:
                    from datetime import datetime

                    expires = datetime.fromisoformat(status["expires_at"].replace("Z", "+00:00"))
                    minutes = round((expires.timestamp() - time.time()) / 60)
                    dim(f"\n  Session expires in {minutes} minutes.")
                except Exception:
                    pass

            return status

        if status.get("status") == "failed":
            detail = (status.get("error") or "").strip()
            msg = (
                f"Twin provisioning failed for run {run_id}: {detail}"
                if detail
                else f"Twin provisioning failed for run {run_id}."
            )
            raise RuntimeError(msg)

        if status.get("status") == "expired":
            raise RuntimeError(f"Twin session {run_id} expired before becoming ready.")

        time.sleep(interval)

    raise RuntimeError(f"Timed out waiting for twins to provision for run {run_id}.")


def _format_seed_summary(seed_info: dict) -> list[str]:
    """Render a server-reported seed result as a list of display lines."""
    status_value = seed_info.get("status")
    if status_value == "seeded":
        counts = [
            f"{key.replace('_', ' ')}: {value}"
            for key, value in seed_info.items()
            if key not in {"status", "twin"} and isinstance(value, (int, str))
        ]
        return [f"Seeded — {', '.join(counts)}"] if counts else ["Seeded."]
    if status_value == "skipped":
        return [f"Skipped ({seed_info.get('reason', 'unknown')})"]
    if status_value == "error":
        return [f"Seed error: {seed_info.get('error', 'unknown')}"]
    return ["Default configuration loaded."]


def seed_and_report(client: Any, status: dict) -> None:
    """Seed quickstart data for UI twins, print default config for backend-only twins."""
    header("Quickstart setup...")

    ui_twins = []
    backend_twins = []

    for name, info in status.get("twins", {}).items():
        if info.get("show_in_ui"):
            ui_twins.append(name)
        else:
            backend_twins.append(name)

    proxy_token = status.get("proxy_token")
    seed_results = status.get("seed_results") or {}

    # Seed and report UI twins
    for name in ui_twins:
        info = status["twins"][name]
        label = TWIN_CATALOG.get(name, {}).get("label", name)

        seed_info = seed_results.get(name)
        if seed_info is None:
            # No server-side seeding happened — fall back to the legacy client-side reset.
            try:
                admin_url = info.get("admin_url", "")
                reset_url = with_proxy_token(f"{admin_url}/admin/reset", proxy_token)
                client._client.post(reset_url, json={}, headers={"Content-Type": "application/json"})
            except Exception:
                pass

        console.print(f"  [bold cyan]{label}[/bold cyan]:")
        if seed_info is not None:
            summary_lines = _format_seed_summary(seed_info)
        else:
            summary_lines = QUICKSTART_SUMMARIES.get(name, ["Default configuration loaded."])
        for line in summary_lines:
            console.print(f"    {line}")

        # Print env vars
        env_vars = info.get("env_vars", {})
        for key, val in env_vars.items():
            console.print(f"    [dim]{key}[/dim]: {val}")
        console.print()

    # Report backend-only twins
    for name in backend_twins:
        info = status["twins"][name]
        label = TWIN_CATALOG.get(name, {}).get("label", name)

        console.print(f"  [bold cyan]{label}[/bold cyan] [dim](backend-only)[/dim]:")
        base_url = info.get("base_url", "")
        console.print(f"    Base URL: [underline]{base_url}[/underline]", soft_wrap=True, overflow="ignore")
        seed_info = seed_results.get(name)
        if seed_info is not None:
            for line in _format_seed_summary(seed_info):
                console.print(f"    {line}")
        env_vars = info.get("env_vars", {})
        if env_vars:
            for key, val in env_vars.items():
                console.print(f"    [dim]{key}[/dim]: {val}")
        elif seed_info is None:
            dim("    No UI dashboard. Use API calls directly.")
        console.print()
