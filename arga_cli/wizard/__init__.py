"""Arga Twins quickstart wizard — native Python implementation."""

from __future__ import annotations

from arga_cli.wizard.env import rewrite_env_files
from arga_cli.wizard.output import console, dim, error, header, yellow
from arga_cli.wizard.prompts import describe_scenario, prompt_api_key, select_twins
from arga_cli.wizard.provision import provision_twins, seed_and_report
from arga_cli.wizard.summary import print_summary


def run_wizard(
    *,
    api_url: str,
    api_key: str | None = None,
    cwd: str,
    shape_detect: bool = True,
) -> int:
    """Run the full quickstart wizard."""
    from arga_cli.main import ApiClient

    header("Welcome to Arga Twins quickstart!")
    dim(
        "Twins are lightweight API doubles that simulate third-party services\n"
        "(Discord, Slack, Stripe, etc.) for your staging environment.\n"
    )

    # Step 1: API key
    resolved_key = prompt_api_key(api_url, api_key)
    if not resolved_key:
        return 1
    client = ApiClient(api_url, api_key=resolved_key)

    # Fetch plan info
    billing_plan = "paid"
    max_twins: int | None = None
    try:
        me = client.get_me()
        billing_plan = me.get("billing_plan", "paid")
        plan_limits = me.get("plan_limits") or {}
        max_twins = plan_limits.get("max_twins_per_run")
        if billing_plan == "free" and plan_limits:
            remaining = plan_limits.get("validation_runs_remaining", "?")
            yellow(f"  Free plan: {remaining} validation run(s) remaining this month.\n")
    except Exception:
        pass  # Non-fatal — fall back to unlimited behavior

    # Step 2: Twin selection (plan-aware)
    selected = select_twins(max_twins)
    if not selected:
        return 1

    # Step 3: Describe desired twin state (optional)
    scenario_prompt = describe_scenario(selected)

    # Step 4: .env rewriting
    env_changes = rewrite_env_files(cwd, selected, shape_detect=shape_detect)

    # Step 5: Provision
    try:
        status = provision_twins(client, selected, ttl_minutes=10, scenario_prompt=scenario_prompt)
    except Exception as exc:
        error(f"\n  Provisioning failed: {exc}")
        if env_changes:
            yellow("  Your .env has been updated. You can re-run the wizard to retry provisioning.")
            yellow("  To restore your original .env: cp .env.arga-backup .env")
        else:
            dim("  No local .env files were changed.")
        dim("  Use `arga runs logs <run-id>` for worker and runtime logs.\n")
        return 1

    # Step 6: Quickstart seeding
    try:
        seed_and_report(client, status)
    except Exception as exc:
        yellow(f"\n  Warning: quickstart seeding failed: {exc}")
        dim("  Twins are running but may not have seed data. You can continue.\n")

    # Step 7: Summary
    print_summary(cwd, status, api_url, resolved_key)

    # Step 8: CLI examples for free plan users
    if billing_plan == "free":
        console.print("\n  [bold]Run validations from the CLI:[/bold]\n")
        console.print('    [cyan]arga test url https://your-app.com "verify the login flow works"[/cyan]')
        console.print('    [cyan]arga test url https://your-app.com "check payments process correctly"[/cyan]')
        console.print('    [cyan]arga test url https://your-app.com "test the search feature returns results"[/cyan]')
        dim("\n  Your free plan includes 10 prompted validation runs/month.\n")

    return 0
