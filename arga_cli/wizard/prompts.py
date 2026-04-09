"""Interactive prompts for the wizard."""

from __future__ import annotations

import json
from pathlib import Path

import questionary

from arga_cli.wizard.constants import TWIN_CATALOG
from arga_cli.wizard.output import dim, green, yellow

CONFIG_PATH = Path.home() / ".config" / "arga" / "config.json"


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")


def prompt_api_key(api_url: str, flag_api_key: str | None = None) -> str | None:
    """Resolve API key: from flag, saved config, or interactive prompt."""
    from arga_cli.main import ApiClient

    # 1. Try flag
    if flag_api_key:
        client = ApiClient(api_url, api_key=flag_api_key)
        try:
            me = client.get_me()
            green(f"  Authenticated as {me.get('email', 'unknown')}")
            return flag_api_key
        finally:
            client.close()

    # 2. Try saved config
    config = _load_config()
    saved_key = config.get("api_key")
    if saved_key:
        client = ApiClient(api_url, api_key=saved_key)
        try:
            me = client.get_me()
            green(f"  Using saved API key for {me.get('email', 'unknown')}")
            return saved_key
        except Exception:
            yellow("  Saved API key is invalid. Please enter a new one.")
        finally:
            client.close()

    # 3. Prompt
    api_key = questionary.text(
        "Enter your Arga API key:",
        validate=lambda val: len(val.strip()) > 0 or "API key is required",
    ).ask()

    if not api_key:
        return None

    trimmed = api_key.strip()
    client = ApiClient(api_url, api_key=trimmed)
    try:
        me = client.get_me()
    finally:
        client.close()

    green(f"  Authenticated as {me.get('email', 'unknown')}")

    # Save for future use
    _save_config({**config, "api_key": trimmed})
    dim(f"  Saved to {CONFIG_PATH}")

    return trimmed


def select_twins(max_twins: int | None = None) -> list[str]:
    """Show twin selection prompt, adapted to the user's plan."""
    ui_choices = []
    backend_choices = []

    for name, meta in TWIN_CATALOG.items():
        domains = ", ".join(meta["intercept_domains"][:2])
        label = f"{meta['label']:<18} {domains}"
        choice = questionary.Choice(title=label, value=name)
        if meta["show_in_ui"]:
            ui_choices.append(choice)
        else:
            backend_choices.append(choice)

    # Free plan: single-select (max 1 twin per run)
    if max_twins == 1:
        dim("  Free plan: select one twin per run.\n")
        all_choices = ui_choices + backend_choices
        selected = questionary.select(
            "Which API twin do you need?",
            choices=all_choices,
        ).ask()
        return [selected] if selected else []

    # Team / Paid: multi-select
    all_choices = (
        [questionary.Separator("── UI Twins (with interactive dashboard) ──")]
        + ui_choices
        + [questionary.Separator("── Backend-only Twins ──")]
        + backend_choices
    )
    selected = questionary.checkbox(
        "Which API twins do you need?",
        choices=all_choices,
        validate=lambda items: len(items) > 0 or "Select at least one twin",
    ).ask()
    return selected if selected else []


def describe_scenario(
    selected_twins: list[str],
    api_client: object | None = None,
) -> tuple[str | None, str | None]:
    """Ask the user to describe desired twin state or pick a saved scenario.

    Returns a (scenario_prompt, scenario_id) tuple. At most one will be set.
    """
    twin_labels = ", ".join(TWIN_CATALOG.get(t, {}).get("label", t) for t in selected_twins)

    from arga_cli.wizard.output import header

    header("Describe your test data")

    # Try to fetch saved scenarios
    saved_scenarios: list[dict] = []
    if api_client is not None:
        try:
            saved_scenarios = api_client.list_scenarios()  # type: ignore[attr-defined]
        except Exception:
            pass  # Non-fatal — fall back to manual entry

    if saved_scenarios:
        choices = [
            questionary.Choice(title="Describe a new scenario", value="__new__"),
            questionary.Choice(title="Skip (use default state)", value="__skip__"),
            questionary.Separator("-- Saved scenarios --"),
        ]
        for s in saved_scenarios:
            label = s.get("name", "Unnamed")
            tags = s.get("tags") or []
            tag_suffix = f"  [{', '.join(tags)}]" if tags else ""
            choices.append(questionary.Choice(title=f"{label}{tag_suffix}", value=s.get("id", "")))

        selected = questionary.select(
            "Use a saved scenario or describe a new one?",
            choices=choices,
        ).ask()

        if selected is None or selected == "__skip__":
            dim("  Skipped \u2014 twins will use default quickstart data.\n")
            return None, None

        if selected != "__new__":
            # User picked a saved scenario
            picked = next((s for s in saved_scenarios if s.get("id") == selected), None)
            picked_name = picked.get("name", selected) if picked else selected
            green(f"  Using saved scenario: {picked_name}\n")
            return None, str(selected)

    # New scenario / no saved scenarios available
    dim(
        f"  Selected twins: {twin_labels}\n"
        "  Describe what data you want each twin to have.\n"
        "  Press Enter to skip and use default state.\n"
    )

    description = questionary.text("Twin state description:", default="").ask()

    if not description or not description.strip():
        dim("  Skipped \u2014 twins will use default quickstart data.\n")
        return None, None

    green("  Scenario noted \u2014 will be applied after provisioning.\n")
    return description.strip(), None
