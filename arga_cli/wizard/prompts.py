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


def describe_scenario(selected_twins: list[str]) -> str | None:
    """Ask the user to describe desired twin state in natural language."""
    twin_labels = ", ".join(TWIN_CATALOG.get(t, {}).get("label", t) for t in selected_twins)

    from arga_cli.wizard.output import header

    header("Describe your test data")
    dim(
        f"  Selected twins: {twin_labels}\n"
        "  Describe what data you want each twin to have.\n"
        "  Press Enter to skip and use default state.\n"
    )

    description = questionary.text("Twin state description:", default="").ask()

    if not description or not description.strip():
        dim("  Skipped \u2014 twins will use default quickstart data.\n")
        return None

    green("  Scenario noted \u2014 will be applied after provisioning.\n")
    return description.strip()


def prompt_save_scenario() -> str | None:
    """Ask whether to save the scenario to the user's library.

    Returns the chosen name if the user wants to save, or None if declined.
    """
    save = questionary.confirm("Save this scenario to your library?", default=False).ask()
    if not save:
        return None

    name = questionary.text(
        "Scenario name:",
        validate=lambda val: len(val.strip()) > 0 or "Name is required",
    ).ask()

    if not name or not name.strip():
        return None

    return name.strip()
