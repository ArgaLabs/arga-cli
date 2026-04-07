from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import webbrowser
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from arga_cli.entry import build_entry_parser
from arga_cli.mcp import install_mcp_configuration

DEFAULT_API_URL = os.environ.get("ARGA_API_URL", "https://api.argalabs.com")
CONFIG_PATH = Path.home() / ".config" / "arga" / "config.json"
WIZARD_SESSION_FILE = ".arga-session.json"
WIZARD_SESSION_PATH = Path(WIZARD_SESSION_FILE)
POLL_INTERVAL_SECONDS = 2.0
POLL_TIMEOUT_SECONDS = 600.0
SKIP_TRAILER = "[skip arga]"


def _cli_version() -> str:
    try:
        return version("arga-cli")
    except PackageNotFoundError:
        return "unknown"


class CliError(Exception):
    """Base CLI error."""


class NotAuthenticatedError(CliError):
    """Raised when no local API key is available."""


class ApiClient:
    def __init__(self, api_url: str, api_key: str | None = None) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(timeout=10.0)

    def close(self) -> None:
        self._client.close()

    def start_device_authorization(self, device_name: str | None = None) -> dict[str, str]:
        payload = {"device_name": device_name} if device_name else {}
        response = self._client.post(f"{self._api_url}/auth/device/start", json=payload)
        return self._parse_json(response, "Failed to start device authorization")

    def poll_device_authorization(self, device_code: str) -> dict[str, str]:
        response = self._client.post(
            f"{self._api_url}/auth/device/poll",
            json={"device_code": device_code},
        )
        return self._parse_json(response, "Failed to poll device authorization")

    def get_me(self) -> dict[str, str]:
        response = self._client.get(
            f"{self._api_url}/auth/me",
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to load current user")

    def revoke_cli_device(self, cli_api_key_id: str) -> dict[str, str]:
        response = self._client.post(
            f"{self._api_url}/auth/cli/devices/{cli_api_key_id}/revoke",
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to revoke CLI device")

    def start_url_validation(
        self,
        *,
        url: str,
        prompt: str,
        email: str | None = None,
        password: str | None = None,
        ttl_minutes: int | None = None,
        repo: str | None = None,
        branch: str | None = None,
        pr_url: str | None = None,
        provision_id: str | None = None,
        twins: list[str] | None = None,
    ) -> dict[str, str]:
        payload: dict[str, object] = {
            "url": url,
            "prompt": prompt,
        }
        if email or password:
            payload["credentials"] = {
                "email": email or "",
                "password": password or "",
            }
        if ttl_minutes is not None:
            payload["ttl_minutes"] = ttl_minutes
        if repo is not None:
            payload["repo"] = repo
        if branch is not None:
            payload["branch"] = branch
        if pr_url is not None:
            payload["pr_url"] = pr_url
        if provision_id is not None:
            payload["provision_id"] = provision_id
        if twins:
            payload["twins"] = twins
        response = self._client.post(
            f"{self._api_url}/validate/url-run",
            json=payload,
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to start URL validation")

    def provision_twins(
        self,
        *,
        twins: list[str],
        ttl_minutes: int = 60,
        scenario_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, object] = {
            "twins": twins,
            "ttl_minutes": ttl_minutes,
        }
        if scenario_id is not None:
            payload["scenario_id"] = scenario_id
        response = self._client.post(
            f"{self._api_url}/validate/twins/provision",
            json=payload,
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to provision twins")

    def get_twin_provision_status(self, run_id: str) -> dict[str, Any]:
        response = self._client.get(
            f"{self._api_url}/validate/twins/provision/{run_id}/status",
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to get provision status")

    def extend_twin_provision(self, run_id: str, *, ttl_minutes: int = 60) -> dict[str, Any]:
        response = self._client.post(
            f"{self._api_url}/validate/twins/provision/{run_id}/extend",
            json={"ttl_minutes": ttl_minutes},
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to extend provision")

    def teardown_twin_provision(self, run_id: str) -> dict[str, Any]:
        response = self._client.post(
            f"{self._api_url}/validate/twins/provision/{run_id}/teardown",
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to teardown provision")

    def start_pr_validation(
        self,
        *,
        repo: str,
        pr_number: int,
    ) -> dict[str, str]:
        response = self._client.post(
            f"{self._api_url}/validation/pr",
            json={"repo": repo, "pr_number": pr_number},
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to start PR validation")

    def start_redteam_scan(self, *, url: str, action_budget: int, focus: str | None = None) -> dict[str, Any]:
        response = self._client.post(
            f"{self._api_url}/validate/agent-run",
            json={"url": url, "action_budget": action_budget, "focus": focus},
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to start agent run")

    def approve_redteam_scan(self, run_id: str) -> dict[str, Any]:
        response = self._client.post(
            f"{self._api_url}/redteam/{run_id}/approve",
            json={},
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to approve agent run")

    def get_run(self, run_id: str) -> dict[str, Any]:
        response = self._client.get(
            f"{self._api_url}/runs/{run_id}",
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to load run details")

    def get_run_logs(self, run_id: str) -> dict[str, Any]:
        response = self._client.get(
            f"{self._api_url}/runs/{run_id}/logs",
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to load run logs")

    def get_redteam_report(self, run_id: str) -> dict[str, Any]:
        response = self._client.get(
            f"{self._api_url}/redteam/{run_id}/report",
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to load agent run report")

    def list_pr_validation_runs(
        self,
        *,
        repo: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, object] = {"limit": limit, "offset": offset}
        if repo:
            params["repo"] = repo
        response = self._client.get(
            f"{self._api_url}/validation/runs",
            params=params,
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to load validation runs")

    def cancel_validation_run(self, run_id: str) -> dict[str, Any]:
        response = self._client.post(
            f"{self._api_url}/validate/{run_id}/cancel",
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to cancel validation run")

    def install_github_validation(self, *, repo: str) -> dict[str, Any]:
        response = self._client.post(
            f"{self._api_url}/validation/github/install",
            json={"repo": repo},
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to install validation webhook")

    def get_github_validation_config(self, *, repo: str) -> dict[str, Any]:
        response = self._client.get(
            f"{self._api_url}/validation/github/config",
            params={"repo": repo},
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to load validation config")

    def save_github_validation_config(
        self,
        *,
        repo: str,
        trigger_mode: str,
        branch: str | None,
        comment_on_pr: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "repo": repo,
            "trigger_mode": trigger_mode,
            "comment_on_pr": comment_on_pr,
        }
        if branch is not None:
            payload["branch"] = branch
        response = self._client.post(
            f"{self._api_url}/validation/github/config",
            json=payload,
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to save validation config")

    def _auth_headers(self) -> dict[str, str]:
        if not self._api_key:
            raise NotAuthenticatedError("Error: Not authenticated. Run `arga login`.")
        return {"Authorization": f"Bearer {self._api_key}"}

    @staticmethod
    def _parse_json(response: httpx.Response, fallback: str) -> dict[str, str]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise CliError(fallback) from exc

        if response.is_success:
            return payload

        detail = payload.get("detail") if isinstance(payload, dict) else None
        if response.status_code == 401:
            raise NotAuthenticatedError("Error: Not authenticated. Run `arga login`.")
        raise CliError(str(detail or fallback))


def load_config() -> dict[str, str]:
    try:
        data = json.loads(CONFIG_PATH.read_text())
    except FileNotFoundError as exc:
        raise NotAuthenticatedError("Error: Not authenticated. Run `arga login`.") from exc
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid config file: {CONFIG_PATH}") from exc

    if not isinstance(data, dict):
        raise CliError(f"Invalid config file: {CONFIG_PATH}")
    return {str(key): str(value) for key, value in data.items() if isinstance(value, str)}


def load_api_key() -> str:
    data = load_config()
    api_key = data.get("api_key")
    if not api_key:
        raise NotAuthenticatedError("Error: Not authenticated. Run `arga login`.")
    return api_key


def save_config(config: dict[str, str]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")


def delete_api_key() -> bool:
    if not CONFIG_PATH.exists():
        return False
    CONFIG_PATH.unlink()
    return True


def load_wizard_session(path: Path = WIZARD_SESSION_PATH) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid wizard session file: {path}") from exc

    if not isinstance(data, dict):
        raise CliError(f"Invalid wizard session file: {path}")
    return data


def resolve_logs_run_id(run_id: str | None, *, session_path: Path = WIZARD_SESSION_PATH) -> str:
    if run_id:
        return run_id
    session = load_wizard_session(session_path)
    session_run_id = str((session or {}).get("run_id") or "").strip()
    if session_run_id:
        return session_run_id
    raise CliError(
        f"Run ID is required. Pass one explicitly or run this command from a directory containing {WIZARD_SESSION_FILE}."
    )


def build_verification_url(start_payload: dict[str, str]) -> str:
    verification_url = start_payload["verification_url"]
    device_code = start_payload["device_code"]
    return f"{verification_url}?{urlencode({'device_code': device_code})}"


def run_login(args: argparse.Namespace) -> int:
    client = ApiClient(args.api_url)
    try:
        device_name = socket.gethostname()
        start_payload = client.start_device_authorization(device_name=device_name)
        verification_url = build_verification_url(start_payload)

        print("Opening browser for authentication...\n")
        print("If it does not open automatically, visit:\n")
        print(verification_url)

        try:
            webbrowser.open(verification_url)
        except webbrowser.Error:
            pass

        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            payload = client.poll_device_authorization(start_payload["device_code"])
            api_key = payload.get("api_key")
            cli_api_key_id = payload.get("cli_api_key_id")
            if api_key and cli_api_key_id:
                save_config(
                    {
                        "api_key": api_key,
                        "cli_api_key_id": cli_api_key_id,
                        "device_name": payload.get("device_name", device_name),
                    }
                )
                print("\nAuthentication complete.")
                return 0
            time.sleep(POLL_INTERVAL_SECONDS)

        raise CliError("Timed out waiting for authentication approval.")
    finally:
        client.close()


def run_logout(args: argparse.Namespace) -> int:
    config: dict[str, str] | None = None
    try:
        config = load_config()
    except (NotAuthenticatedError, CliError):
        config = None

    if config and config.get("api_key") and config.get("cli_api_key_id"):
        client = ApiClient(args.api_url, api_key=config["api_key"])
        try:
            client.revoke_cli_device(config["cli_api_key_id"])
        except (CliError, httpx.HTTPError):
            # Always remove the local credential even if server-side revoke fails.
            pass
        finally:
            client.close()

    removed = delete_api_key()
    if removed:
        print("Logged out.")
    else:
        print("No saved login found.")
    return 0


def run_whoami(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        payload = client.get_me()
    finally:
        client.close()

    print(f"Logged in as: {payload.get('github_login', 'unknown')}")
    print(f"Workspace: {payload.get('workspace', 'Unknown')}")

    billing_plan = payload.get("billing_plan", "free")
    print(f"Plan: {billing_plan}")

    plan_limits = payload.get("plan_limits")
    if plan_limits:
        runs_remaining = plan_limits.get("validation_runs_remaining")
        runs_limit = plan_limits.get("validation_runs_limit")
        if runs_limit is not None:
            print(f"Validation runs: {runs_remaining}/{runs_limit} remaining this month")
        else:
            print("Validation runs: unlimited")

        ci_limit = plan_limits.get("ci_checks_limit")
        ci_remaining = plan_limits.get("ci_checks_remaining")
        if ci_limit is not None:
            print(f"CI checks: {ci_remaining}/{ci_limit} remaining this month")
        elif billing_plan in ("team", "paid"):
            print("CI checks: unlimited")

        max_twins = plan_limits.get("max_twins_per_run")
        if max_twins is not None:
            print(f"Twins per run: {max_twins}")
        elif billing_plan in ("team", "paid"):
            print("Twins per run: unlimited")

        max_ttl = plan_limits.get("max_ttl_minutes")
        if max_ttl is not None:
            print(f"Max run TTL: {max_ttl} minutes")
        elif billing_plan in ("team", "paid"):
            print("Max run TTL: 480 minutes")

    return 0


def _resolve_ttl(client: ApiClient, requested_ttl: int | None) -> int | None:
    """Resolve TTL based on user plan. Free users are capped at 10 minutes."""
    FREE_TTL = 10

    me = client.get_me()
    billing_plan = me.get("billing_plan", "free")

    if billing_plan in ("team", "paid"):
        return requested_ttl  # None means server default (30 min)

    # Free tier — locked to 10 minutes
    if requested_ttl is not None and requested_ttl != FREE_TTL:
        raise CliError(
            f"Free plan runs are limited to {FREE_TTL} minutes. Upgrade to Team for custom TTL (up to 480 minutes)."
        )
    return FREE_TTL


def run_test_url(args: argparse.Namespace) -> int:
    if bool(args.email) != bool(args.password):
        raise CliError("Both --email and --password must be provided together.")

    # Read arga.yaml for defaults
    from arga_cli.init import load_arga_yaml

    arga_config = load_arga_yaml(Path.cwd())

    # Auto-populate twins from arga.yaml if not explicitly provided
    twins: list[str] | None = None
    if arga_config and arga_config.get("integrations") and not getattr(args, "twins", None):
        twins = [i["twin"] for i in arga_config["integrations"] if isinstance(i, dict) and "twin" in i]

    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        ttl_minutes = _resolve_ttl(client, getattr(args, "ttl", None))
        payload = client.start_url_validation(
            url=args.url,
            prompt=args.prompt,
            email=args.email,
            password=args.password,
            ttl_minutes=ttl_minutes,
            repo=args.repo,
            branch=args.branch,
            provision_id=getattr(args, "provision_id", None),
            twins=twins if twins else None,
        )
    finally:
        client.close()

    if getattr(args, "json", False):
        print(json.dumps({"run_id": payload.get("run_id"), "status": payload.get("status")}))
        return 0

    print("Starting validation...\n")
    print(f"URL: {args.url}")
    print(f"Prompt: {args.prompt}")
    if args.repo:
        print(f"Repository: {args.repo}")
    if args.branch:
        print(f"Branch: {args.branch}")
    print(f"TTL: {ttl_minutes} minutes\n")
    print(f"Run ID: {payload.get('run_id', 'unknown')}")
    print(f"Status: {payload.get('status', 'unknown')}")
    return 0


def run_twins_provision(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        twins = [t.strip() for t in args.twins.split(",") if t.strip()]
        if not twins:
            raise CliError("At least one twin name is required.")
        payload = client.provision_twins(
            twins=twins,
            ttl_minutes=getattr(args, "ttl", 60),
            scenario_id=getattr(args, "scenario", None),
        )
    finally:
        client.close()

    if getattr(args, "json", False):
        print(json.dumps(payload))
        return 0

    print("Provisioning twins...\n")
    print(f"Twins: {args.twins}")
    print(f"Provision ID: {payload.get('run_id', 'unknown')}")
    print("\nPoll status with: arga twins status " + payload.get("run_id", "<id>"))
    return 0


def run_twins_status(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        payload = client.get_twin_provision_status(args.provision_id)
    finally:
        client.close()

    if getattr(args, "json", False):
        print(json.dumps(payload))
        return 0

    status = payload.get("status", "unknown")
    print(f"Status: {status}")
    twins_info = payload.get("twins", {})
    if twins_info:
        print("\nTwin endpoints:")
        for name, info in twins_info.items():
            base_url = info.get("base_url", "")
            print(f"  {name}: {base_url}")
            env_vars = info.get("env_vars", {})
            for k, v in env_vars.items():
                print(f"    {k}={v}")
    if payload.get("expires_at"):
        print(f"\nExpires: {payload['expires_at']}")
    return 0


def run_twins_extend(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        client.extend_twin_provision(args.provision_id, ttl_minutes=args.minutes)
    finally:
        client.close()

    print(f"Extended by {args.minutes} minutes.")
    return 0


def run_twins_teardown(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        payload = client.teardown_twin_provision(args.provision_id)
    finally:
        client.close()

    print(f"Teardown initiated. Status: {payload.get('status', 'unknown')}")
    return 0


def run_validate_pr(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        payload = client.start_pr_validation(repo=args.repo, pr_number=args.pr)
    finally:
        client.close()

    if args.json:
        print(json.dumps({"run_id": payload.get("run_id"), "status": payload.get("status")}))
        return 0

    print("Starting PR validation...\n")
    print(f"Repository: {args.repo}")
    print(f"PR: #{args.pr}\n")
    print("Validation run started.")
    print(f"Run ID: {payload.get('run_id', 'unknown')}")
    print(f"Status: {payload.get('status', 'unknown')}")
    return 0


def _validate_help_text() -> str:
    return (
        "usage: arga validate pr --repo <owner/repo> --pr <number>\n"
        "       arga validate install <repo>\n"
        "       arga validate config <repo>\n"
        "       arga validate config set <repo> [--trigger pr|branch] [--branch <name>] [--comments on|off]\n\n"
        "Start validations or manage automatic validation settings."
    )


def _build_validate_pr_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arga validate pr",
        description="Run PR validation.",
        allow_abbrev=False,
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    parser.add_argument("--repo", required=True, help="Repository in owner/repo format")
    parser.add_argument("--pr", required=True, type=int, help="Pull request number")
    return parser


def _build_validate_install_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arga validate install",
        description="Install the GitHub webhook for automatic validation.",
        allow_abbrev=False,
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    parser.add_argument("repo", help="Repository in owner/repo format")
    return parser


def _build_validate_config_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arga validate config",
        description="Show validation config for a repository.",
        allow_abbrev=False,
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    parser.add_argument("repo", help="Repository in owner/repo format")
    return parser


def _build_validate_config_set_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arga validate config set",
        description="Save validation config for a repository.",
        allow_abbrev=False,
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    parser.add_argument("repo", help="Repository in owner/repo format")
    parser.add_argument("--trigger", choices=("pr", "branch"), help="Validation trigger mode")
    parser.add_argument("--branch", help="Branch to monitor when using branch trigger mode")
    parser.add_argument("--comments", choices=("on", "off"), help="Whether PR comments are enabled")
    return parser


def _bool_label(value: bool) -> str:
    return "yes" if value else "no"


def _comments_label(value: bool) -> str:
    return "on" if value else "off"


def _print_validation_config(payload: dict[str, Any]) -> None:
    print(f"Repository: {payload.get('repo', '-')}")
    print(f"Installed: {_bool_label(bool(payload.get('installed')))}")
    print(f"Enabled: {_bool_label(bool(payload.get('enabled')))}")
    print(f"Installation ID: {payload.get('installation_id') or '-'}")
    print(f"Trigger Mode: {payload.get('trigger_mode') or '-'}")
    print(f"Branch: {payload.get('branch') or '-'}")
    print(f"Default Branch: {payload.get('default_branch') or '-'}")
    print(f"PR Comments: {_comments_label(bool(payload.get('comment_on_pr', True)))}")


def run_validate_install(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        payload = client.install_github_validation(repo=args.repo)
    finally:
        client.close()

    print("Installed validation webhook.\n")
    print(f"Repository: {payload.get('repo', args.repo)}")
    print(f"Webhook ID: {payload.get('webhook_id', '-')}")
    print(f"Enabled: {_bool_label(bool(payload.get('enabled')))}")
    return 0


def run_validate_config(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        payload = client.get_github_validation_config(repo=args.repo)
    finally:
        client.close()

    _print_validation_config(payload)
    return 0


def run_validate_config_set(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        current = client.get_github_validation_config(repo=args.repo)
        trigger_mode = args.trigger or str(current.get("trigger_mode") or "pr")
        comment_on_pr = current.get("comment_on_pr", True) if args.comments is None else args.comments == "on"
        branch: str | None = None
        if trigger_mode == "branch":
            branch = args.branch or str(current.get("branch") or current.get("default_branch") or "").strip() or None
        payload = client.save_github_validation_config(
            repo=args.repo,
            trigger_mode=trigger_mode,
            branch=branch if trigger_mode == "branch" else None,
            comment_on_pr=bool(comment_on_pr),
        )
    finally:
        client.close()

    print("Saved validation config.\n")
    _print_validation_config(payload)
    return 0


def run_mcp_install(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    installed, failures = install_mcp_configuration(
        api_url=args.api_url,
        api_key=api_key,
    )
    if installed == 0 and failures == 0:
        print("\nInstall Arga MCP manually by adding the generated config to your IDE.")
        return 1
    return 1 if failures else 0


def run_init(args: argparse.Namespace) -> int:
    from arga_cli.init import detect_integrations, generate_arga_yaml

    repo_root = Path.cwd()
    print("Scanning repository for integrations...\n")

    detected = detect_integrations(repo_root)

    if not detected:
        print("No integrations detected.")
        print("You can manually create an arga.yaml file.")
        return 0

    print("Found integrations:")
    for d in detected:
        marker = "\u2713" if d["confidence"] == "high" else "?"
        print(f"  [{marker}] {d['name']} \u2014 {d['source']}")

    print()
    confirm = input("Generate arga.yaml with these integrations? (Y/n): ").strip().lower()
    if confirm and confirm != "y":
        print("Aborted.")
        return 0

    yaml_content = generate_arga_yaml(detected)
    output_path = repo_root / "arga.yaml"
    output_path.write_text(yaml_content)
    print(f"\nGenerated {output_path}")

    # Also run MCP install
    try:
        api_key = load_api_key()
        api_url = args.api_url if hasattr(args, "api_url") else DEFAULT_API_URL
        installed, _failed = install_mcp_configuration(api_url=api_url, api_key=api_key)
        if installed:
            print(f"Installed MCP config for {installed} IDE(s).")
    except Exception:
        pass  # MCP install is best-effort

    print("\nDone! Next steps:")
    print("  1. Review arga.yaml and adjust as needed")
    print("  2. Run: arga test url --url <your-staging-url> --prompt 'test the app'")
    return 0


def _scan_help_text() -> str:
    return (
        "usage: arga scan <url> [--budget 200]\n"
        "       arga scan status <run_id>\n"
        "       arga scan report <run_id>\n\n"
        "Start or inspect Arga agent runs."
    )


def _build_scan_start_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arga scan",
        description="Start an Arga agent run.",
        allow_abbrev=False,
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    parser.add_argument("url", help="Public application URL to explore")
    parser.add_argument("--budget", type=int, default=200, help="Total action budget for the scan")
    return parser


def _build_scan_status_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arga scan status",
        description="Check the status of an Arga agent run.",
        allow_abbrev=False,
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    parser.add_argument("run_id", help="App scan run ID")
    return parser


def _build_scan_report_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arga scan report",
        description="View the final report for an Arga agent run.",
        allow_abbrev=False,
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    parser.add_argument("run_id", help="App scan run ID")
    return parser


def _status_from_run(run: dict[str, Any]) -> str:
    return str(run.get("status") or "unknown")


def _wait_for_scan_approval(client: ApiClient, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last_run: dict[str, Any] = {"id": run_id, "status": "planning"}
    while time.monotonic() < deadline:
        run = client.get_run(run_id)
        last_run = run
        status = _status_from_run(run)
        if status in {"queued", "running", "completed", "failed", "cancelled"}:
            return run

        if status in {"planning", "awaiting_approval"}:
            try:
                approval = client.approve_redteam_scan(run_id)
                run["status"] = approval.get("status", run.get("status"))
                return run
            except CliError as exc:
                if str(exc) != "Scan plan is not ready yet":
                    raise

        time.sleep(POLL_INTERVAL_SECONDS)

    raise CliError(f"Timed out waiting for the scan plan to be ready for run {last_run.get('id', run_id)}.")


def _print_scan_summary(run_id: str, run: dict[str, Any]) -> None:
    report = run.get("redteam_report_json")
    anomaly_count = len(report.get("anomalies") or []) if isinstance(report, dict) else 0
    print(f"Run ID: {run_id}")
    print(f"Status: {_status_from_run(run)}")
    print(f"URL: {run.get('frontend_url') or run.get('pr_url') or 'unknown'}")
    print(f"Mode: {run.get('mode') or 'unknown'}")
    print(f"Anomalies: {anomaly_count}")


def run_scan_start(args: argparse.Namespace) -> int:
    if args.budget <= 0:
        raise CliError("Budget must be a positive integer.")

    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        payload = client.start_redteam_scan(url=args.url, action_budget=args.budget)
        run_id = str(payload.get("run_id") or "")
        if not run_id:
            raise CliError("Agent run started but no run ID was returned.")
        run = _wait_for_scan_approval(client, run_id)
    finally:
        client.close()

    print("Starting agent run...\n")
    print(f"URL: {args.url}")
    print(f"Budget: {args.budget}")
    print(f"Run ID: {run_id}")
    print(f"Status: {_status_from_run(run)}")
    return 0


def run_scan_status(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        run = client.get_run(args.run_id)
    finally:
        client.close()

    _print_scan_summary(args.run_id, run)
    return 0


def run_scan_report(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        report = client.get_redteam_report(args.run_id)
    finally:
        client.close()

    if not report:
        raise CliError("Scan report is not ready yet.")

    print(json.dumps(report, indent=2))
    return 0


def run_scan_cli(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(_scan_help_text())
        return 0

    if argv[0] == "status":
        return run_scan_status(_build_scan_status_parser().parse_args(argv[1:]))
    if argv[0] == "report":
        return run_scan_report(_build_scan_report_parser().parse_args(argv[1:]))
    return run_scan_start(_build_scan_start_parser().parse_args(argv))


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "-"
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M")


def _run_ref_label(run: dict[str, Any]) -> str:
    pr_number = run.get("pr_number") or run.get("github_pr_number")
    if pr_number is not None:
        return f"PR #{pr_number}"
    branch = run.get("branch") or run.get("git_branch")
    if branch:
        return str(branch)
    return "-"


def _matches_runs_status_filter(run_status: str, requested_status: str | None) -> bool:
    if requested_status is None:
        return True
    normalized = run_status.strip().lower()
    if requested_status == "running":
        return normalized not in {"completed", "failed", "cancelled"}
    return normalized == requested_status


def _collect_runs_for_listing(
    client: ApiClient,
    *,
    repo: str | None,
    requested_status: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    offset = 0
    page_size = min(max(limit, 10), 100)

    while len(collected) < limit:
        page = client.list_pr_validation_runs(repo=repo, limit=page_size, offset=offset)
        items = page.get("items")
        if not isinstance(items, list) or not items:
            break

        for item in items:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "")
            if _matches_runs_status_filter(status, requested_status):
                collected.append(item)
                if len(collected) >= limit:
                    break

        has_more = bool(page.get("has_more"))
        if not has_more:
            break
        offset += int(page.get("limit") or page_size)

    return collected[:limit]


def _print_runs_table(runs: list[dict[str, Any]]) -> None:
    headers = ["RUN_ID", "STATUS", "REPO", "PR/BRANCH", "CREATED"]
    rows = [
        [
            str(run.get("run_id") or "-"),
            str(run.get("status") or "-"),
            str(run.get("repo") or "-"),
            _run_ref_label(run),
            _format_timestamp(run.get("created_at")),
        ]
        for run in runs
    ]
    widths = [
        max(len(headers[index]), max((len(row[index]) for row in rows), default=0)) for index in range(len(headers))
    ]

    def format_row(values: list[str]) -> str:
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(values))

    print(format_row(headers))
    print(" | ".join("-" * width for width in widths))
    for row in rows:
        print(format_row(row))


def _print_worker_logs(worker_logs: list[dict[str, Any]]) -> None:
    print("Worker Logs:")
    if not worker_logs:
        print("None")
        return

    for index, worker_log in enumerate(worker_logs):
        job_id = str(worker_log.get("job_id") or "-")
        metadata = [
            str(worker_log.get("job_type") or "").strip(),
            str(worker_log.get("target_role") or "").strip(),
            str(worker_log.get("status") or "").strip(),
        ]
        metadata_label = " / ".join(value for value in metadata if value)
        print(f"{job_id}: {metadata_label or 'worker log'}")

        error = str(worker_log.get("error") or "").strip()
        content = str(worker_log.get("content") or "").rstrip()
        if error:
            print(f"Error: {error}")
        elif content:
            print(content)
        else:
            print("No log content available.")

        if index < len(worker_logs) - 1:
            print()


def _print_runtime_logs(runtime_logs: list[dict[str, Any]]) -> None:
    print("Runtime Logs:")
    if not runtime_logs:
        print("None")
        return

    for index, runtime_log in enumerate(runtime_logs):
        header_parts = [
            _format_timestamp(runtime_log.get("timestamp")),
            str(runtime_log.get("severity") or "").strip(),
            str(runtime_log.get("service_name") or "").strip(),
            str(runtime_log.get("event") or "").strip(),
            str(runtime_log.get("code") or "").strip(),
        ]
        header = " | ".join(part for part in header_parts if part and part != "-")
        print(header or "Log entry")

        message = str(runtime_log.get("message") or "").strip()
        if message:
            print(message)

        metadata: list[str] = []
        request_id = str(runtime_log.get("request_id") or "").strip()
        if request_id:
            metadata.append(f"request_id={request_id}")
        job_id = str(runtime_log.get("job_id") or "").strip()
        if job_id:
            metadata.append(f"job_id={job_id}")
        surface_name = str(runtime_log.get("surface_name") or "").strip()
        if surface_name:
            metadata.append(f"surface={surface_name}")
        if metadata:
            print(" ".join(metadata))

        if index < len(runtime_logs) - 1:
            print()


def _is_error_runtime_log(runtime_log: dict[str, Any]) -> bool:
    severity = str(runtime_log.get("severity") or "").strip().upper()
    return severity in {"WARNING", "ERROR", "CRITICAL", "ALERT", "EMERGENCY"}


def _is_error_worker_log(worker_log: dict[str, Any]) -> bool:
    status = str(worker_log.get("status") or "").strip().lower()
    error = str(worker_log.get("error") or "").strip()
    return status in {"failed", "error", "cancelled"} or bool(error)


def _filter_run_logs_payload(payload: dict[str, Any], *, errors_only: bool) -> dict[str, Any]:
    if not errors_only:
        return payload

    filtered_payload = dict(payload)
    worker_logs = payload.get("worker_logs")
    runtime_logs = payload.get("runtime_logs")
    warnings = payload.get("warnings")

    filtered_payload["worker_logs"] = (
        [item for item in worker_logs if isinstance(item, dict) and _is_error_worker_log(item)]
        if isinstance(worker_logs, list)
        else []
    )
    filtered_payload["runtime_logs"] = (
        [item for item in runtime_logs if isinstance(item, dict) and _is_error_runtime_log(item)]
        if isinstance(runtime_logs, list)
        else []
    )
    filtered_payload["warnings"] = warnings if isinstance(warnings, list) else []
    return filtered_payload


def _print_run_logs(payload: dict[str, Any], fallback_run_id: str) -> None:
    run = payload.get("run")
    run_data = run if isinstance(run, dict) else {}
    worker_logs = payload.get("worker_logs")
    runtime_logs = payload.get("runtime_logs")
    warnings = payload.get("warnings")
    timeline_events = run_data.get("event_log_json")

    print(f"Run ID: {run_data.get('id', fallback_run_id)}")
    print(f"Status: {run_data.get('status', 'unknown')}")
    print(f"Type: {run_data.get('run_type', 'unknown')}")
    print(f"Mode: {run_data.get('mode', 'unknown')}")
    print(f"Repository: {run_data.get('repo_full_name') or '-'}")
    print(f"PR/Branch: {_run_ref_label(run_data)}")
    print(f"Commit: {run_data.get('commit_sha') or '-'}")
    print(f"Created: {_format_timestamp(run_data.get('created_at'))}")
    print(f"Environment URL: {run_data.get('environment_url') or '-'}")
    if isinstance(timeline_events, list):
        print(f"Timeline Events: {len(timeline_events)}")

    print()
    _print_worker_logs(worker_logs if isinstance(worker_logs, list) else [])
    print()
    _print_runtime_logs(runtime_logs if isinstance(runtime_logs, list) else [])

    if isinstance(warnings, list) and warnings:
        print()
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")


def run_runs_list(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        runs = _collect_runs_for_listing(
            client,
            repo=args.repo,
            requested_status=args.status,
            limit=args.limit,
        )
    finally:
        client.close()

    if args.json:
        print(json.dumps(runs))
        return 0

    if not runs:
        print("No matching validation runs found.")
        return 0

    _print_runs_table(runs)
    return 0


def run_runs_status(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        run = client.get_run(args.run_id)
    finally:
        client.close()

    if args.json:
        print(json.dumps(run))
        return 0

    print(f"Run ID: {run.get('id', args.run_id)}")
    print(f"Status: {run.get('status', 'unknown')}")
    print(f"Type: {run.get('run_type', 'unknown')}")
    print(f"Mode: {run.get('mode', 'unknown')}")
    print(f"Repository: {run.get('repo_full_name') or '-'}")
    print(f"PR/Branch: {_run_ref_label(run)}")
    print(f"Commit: {run.get('commit_sha') or '-'}")
    print(f"Created: {_format_timestamp(run.get('created_at'))}")
    print(f"Environment URL: {run.get('environment_url') or '-'}")
    print(f"Session ID: {run.get('session_id') or '-'}")
    return 0


def run_runs_logs(args: argparse.Namespace) -> int:
    run_id = resolve_logs_run_id(args.run_id)
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        payload = client.get_run_logs(run_id)
    finally:
        client.close()

    payload = _filter_run_logs_payload(payload, errors_only=args.errors_only)

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    _print_run_logs(payload, run_id)
    return 0


def run_runs_cancel(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        payload = client.cancel_validation_run(args.run_id)
    finally:
        client.close()

    print(f"Run ID: {args.run_id}")
    print(f"Status: {payload.get('status', 'cancelled')}")
    return 0


def run_validate_cli(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(_validate_help_text())
        return 0

    if argv[0] == "pr":
        return run_validate_pr(_build_validate_pr_parser().parse_args(argv[1:]))
    if argv[0] == "install":
        return run_validate_install(_build_validate_install_parser().parse_args(argv[1:]))
    if argv[0] == "config":
        if len(argv) > 1 and argv[1] == "set":
            return run_validate_config_set(_build_validate_config_set_parser().parse_args(argv[2:]))
        return run_validate_config(_build_validate_config_parser().parse_args(argv[1:]))

    raise CliError(f"Unknown validate subcommand: {argv[0]}")


def _parse_git_wrapper_args(command: str, argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        prog=f"arga {command}",
        description=f"Wrap `git {command}` with optional Arga-specific behavior.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--skip",
        action="store_true",
        help="Mark the head commit to skip Arga validation.",
    )
    return parser.parse_known_args(argv)


def _run_git_command(args: list[str], *, input_text: str | None = None) -> int:
    try:
        completed = subprocess.run(["git", *args], text=True, input=input_text, check=False)
    except FileNotFoundError as exc:
        raise CliError("Error: `git` is not installed or not available on PATH.") from exc
    return int(completed.returncode)


def _get_head_commit_message() -> str:
    try:
        completed = subprocess.run(
            ["git", "log", "-1", "--pretty=%B"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CliError("Error: `git` is not installed or not available on PATH.") from exc

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise CliError(stderr or "Error: Failed to read the HEAD commit message.")
    return completed.stdout


def _commit_args_contain_message_flag(git_args: list[str]) -> bool:
    for arg in git_args:
        if arg in {"-m", "--message"}:
            return True
        if arg.startswith("-m") and arg != "-m":
            return True
        if arg.startswith("--message="):
            return True
    return False


def _extract_commit_file_path(git_args: list[str]) -> str | None:
    i = 0
    while i < len(git_args):
        arg = git_args[i]
        if arg in {"-F", "--file"}:
            if i + 1 >= len(git_args):
                raise CliError("Error: Missing value for git commit message file.")
            return git_args[i + 1]
        if arg.startswith("-F") and arg != "-F":
            return arg[2:]
        if arg.startswith("--file="):
            return arg.split("=", 1)[1]
        i += 1
    return None


def _build_skip_commit_args(git_args: list[str]) -> tuple[list[str], str | None, list[Path]]:
    if _commit_args_contain_message_flag(git_args):
        return [*git_args, "-m", SKIP_TRAILER], None, []

    file_path = _extract_commit_file_path(git_args)
    if file_path is None:
        raise CliError("Error: `arga commit --skip` requires a commit message via `-m/--message` or `-F/--file`.")

    if file_path == "-":
        stdin_message = sys.stdin.read()
        stripped = stdin_message.rstrip()
        trailer = SKIP_TRAILER if not stripped else f"{stripped}\n\n{SKIP_TRAILER}"
        return git_args, trailer, []

    source = Path(file_path)
    message = source.read_text()
    stripped = message.rstrip()
    trailer = SKIP_TRAILER if not stripped else f"{stripped}\n\n{SKIP_TRAILER}"

    temp_file = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
    try:
        temp_file.write(trailer)
    finally:
        temp_file.close()

    rewritten_args: list[str] = []
    i = 0
    while i < len(git_args):
        arg = git_args[i]
        if arg in {"-F", "--file"}:
            rewritten_args.extend([arg, temp_file.name])
            i += 2
            continue
        if arg.startswith("-F") and arg != "-F":
            rewritten_args.append(f"-F{temp_file.name}")
            i += 1
            continue
        if arg.startswith("--file="):
            rewritten_args.append(f"--file={temp_file.name}")
            i += 1
            continue
        rewritten_args.append(arg)
        i += 1

    return rewritten_args, None, [Path(temp_file.name)]


def run_commit_cli(argv: list[str]) -> int:
    args, git_args = _parse_git_wrapper_args("commit", argv)
    input_text: str | None = None
    temp_paths: list[Path] = []
    commit_args = git_args

    if args.skip:
        commit_args, input_text, temp_paths = _build_skip_commit_args(git_args)

    try:
        return _run_git_command(["commit", *commit_args], input_text=input_text)
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)


def run_push_cli(argv: list[str]) -> int:
    args, git_args = _parse_git_wrapper_args("push", argv)

    if args.skip:
        commit_message = _get_head_commit_message()
        if SKIP_TRAILER not in commit_message.lower():
            raise CliError(
                "Error: HEAD is not marked to skip Arga validation. Create the commit with `arga commit --skip` first."
            )

    return _run_git_command(["push", *git_args])


def _wizard_help_text() -> str:
    return (
        "usage: arga wizard [command] [options]\n\n"
        "Commands:\n"
        "  init        Run the quickstart wizard (default)\n"
        "  status      Check twin session health\n"
        "  reset       Reset all twins to seed state\n"
        "  extend      Extend session by 10 minutes\n"
        "  teardown    Destroy session and clean up\n"
        "  env         Re-run .env rewriting step\n\n"
        "Options:\n"
        "  --api-url            API base URL\n"
        "  --no-shape-detect    Disable heuristic detection of API keys by value pattern\n"
        "  -h, --help           Show this help"
    )


def _build_wizard_init_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arga wizard", allow_abbrev=False)
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    parser.add_argument("--no-shape-detect", action="store_true", default=False)
    return parser


def _build_wizard_session_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, allow_abbrev=False)
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    return parser


def run_wizard_init(args: argparse.Namespace) -> int:
    """Run the full quickstart wizard natively."""
    from arga_cli.wizard import run_wizard

    try:
        api_key = load_api_key()
    except (NotAuthenticatedError, CliError):
        api_key = None

    return run_wizard(
        api_url=args.api_url,
        api_key=api_key,
        cwd=os.getcwd(),
        shape_detect=not getattr(args, "no_shape_detect", False),
    )


def run_wizard_status(_args: argparse.Namespace) -> int:
    from arga_cli.wizard.constants import TWIN_CATALOG
    from arga_cli.wizard.output import print_summary_box
    from arga_cli.wizard.provision import with_proxy_token
    from arga_cli.wizard.session import load_session

    session = load_session(os.getcwd())
    client = ApiClient(session["api_url"], api_key=session["api_key"])
    try:
        response = client._client.get(
            f"{client._api_url}/validate/twins/provision/{session['run_id']}/status",
            headers=client._auth_headers(),
        )
        status = client._parse_json(response, "Failed to get status")
    finally:
        client.close()

    lines = [
        "[bold]Twin Session Status[/bold]",
        "",
        f"Run ID:  {status['run_id']}",
        f"Status:  {'[green]' + status['status'] + '[/green]' if status['status'] == 'ready' else '[yellow]' + status['status'] + '[/yellow]'}",
        "",
    ]
    for name, info in status.get("twins", {}).items():
        label = TWIN_CATALOG.get(name, {}).get("label", name).ljust(16)
        url = with_proxy_token(info.get("base_url", ""), status.get("proxy_token"))
        lines.append(f"{label} [underline]{url}[/underline]")
    if status.get("expires_at"):
        lines.append("")
        lines.append(f"Expires: {status['expires_at']}")
    print_summary_box(lines)
    return 0


def run_wizard_reset(_args: argparse.Namespace) -> int:
    from arga_cli.wizard.constants import TWIN_CATALOG
    from arga_cli.wizard.output import console, green, header
    from arga_cli.wizard.provision import with_proxy_token
    from arga_cli.wizard.session import load_session

    session = load_session(os.getcwd())
    client = ApiClient(session["api_url"], api_key=session["api_key"])
    header("Resetting all twins...")

    twins = session.get("twins", {})
    proxy_token = session.get("proxy_token")

    # Refresh from API if possible
    try:
        response = client._client.get(
            f"{client._api_url}/validate/twins/provision/{session['run_id']}/status",
            headers=client._auth_headers(),
        )
        status = client._parse_json(response, "Failed to get status")
        if status.get("status") == "ready":
            twins = {
                name: {"base_url": info.get("base_url", ""), "admin_url": info.get("admin_url", "")}
                for name, info in status.get("twins", {}).items()
            }
            proxy_token = status.get("proxy_token", proxy_token)
    except Exception:
        pass

    for name, twin in twins.items():
        label = TWIN_CATALOG.get(name, {}).get("label", name)
        try:
            reset_url = with_proxy_token(f"{twin['admin_url']}/admin/reset", proxy_token)
            client._client.post(reset_url, json={}, headers={"Content-Type": "application/json"})
            console.print(f"  {label}: [green]reset[/green]")
        except Exception as exc:
            console.print(f"  {label}: [red]failed \u2014 {exc}[/red]")

    client.close()
    green("\nDone.")
    return 0


def run_wizard_extend(_args: argparse.Namespace) -> int:
    from arga_cli.wizard.output import error, green
    from arga_cli.wizard.session import load_session

    session = load_session(os.getcwd())
    client = ApiClient(session["api_url"], api_key=session["api_key"])
    try:
        response = client._client.post(
            f"{client._api_url}/validate/twins/provision/{session['run_id']}/extend",
            json={"ttl_minutes": 10},
            headers=client._auth_headers(),
        )
        client._parse_json(response, "Failed to extend session")
        green("\nSession extended by 10 minutes.")
    except Exception as exc:
        error(f"Failed to extend: {exc}")
        return 1
    finally:
        client.close()
    return 0


def run_wizard_teardown(_args: argparse.Namespace) -> int:
    from arga_cli.wizard.output import error, green
    from arga_cli.wizard.session import delete_session, load_session

    session = load_session(os.getcwd())
    client = ApiClient(session["api_url"], api_key=session["api_key"])
    try:
        response = client._client.post(
            f"{client._api_url}/validate/{session['run_id']}/cancel",
            headers=client._auth_headers(),
        )
        client._parse_json(response, "Failed to cancel run")
        delete_session(os.getcwd())
        green("\nSession destroyed. .arga-session.json removed.")
    except Exception as exc:
        error(f"Failed to teardown: {exc}")
        return 1
    finally:
        client.close()
    return 0


def run_wizard_env(args: argparse.Namespace) -> int:
    from arga_cli.wizard.env import rewrite_env_files
    from arga_cli.wizard.prompts import select_twins

    selected = select_twins()
    if not selected:
        return 1
    rewrite_env_files(
        os.getcwd(),
        selected,
        shape_detect=not getattr(args, "no_shape_detect", False),
    )
    return 0


def run_wizard_cli(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(_wizard_help_text())
        return 0

    command = argv[0]

    if command == "init":
        return run_wizard_init(_build_wizard_init_parser().parse_args(argv[1:]))
    if command == "status":
        return run_wizard_status(_build_wizard_session_parser("arga wizard status").parse_args(argv[1:]))
    if command == "reset":
        return run_wizard_reset(_build_wizard_session_parser("arga wizard reset").parse_args(argv[1:]))
    if command == "extend":
        return run_wizard_extend(_build_wizard_session_parser("arga wizard extend").parse_args(argv[1:]))
    if command == "teardown":
        return run_wizard_teardown(_build_wizard_session_parser("arga wizard teardown").parse_args(argv[1:]))
    if command == "env":
        return run_wizard_env(_build_wizard_init_parser().parse_args(argv[1:]))

    # No recognized subcommand — treat everything as flags for `init`
    if command.startswith("-"):
        return run_wizard_init(_build_wizard_init_parser().parse_args(argv))

    raise CliError(f"Unknown wizard subcommand: {command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arga")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_cli_version()}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser("login", help="Authenticate the CLI")
    login_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    login_parser.set_defaults(func=run_login)

    logout_parser = subparsers.add_parser("logout", help="Remove the saved API key")
    logout_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    logout_parser.set_defaults(func=run_logout)

    whoami_parser = subparsers.add_parser("whoami", help="Show the authenticated user")
    whoami_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    whoami_parser.set_defaults(func=run_whoami)

    init_parser = subparsers.add_parser("init", help="Scan repo and generate arga.yaml")
    init_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    init_parser.set_defaults(func=run_init)

    test_parser = subparsers.add_parser("test", help="Start validation runs")
    test_subparsers = test_parser.add_subparsers(dest="test_command", required=True)

    test_url_parser = test_subparsers.add_parser("url", help="Run a browser validation against a deployed URL")
    test_url_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    test_url_parser.add_argument("--url", required=True, help="Deployed application URL")
    test_url_parser.add_argument("--prompt", required=True, help="Natural language instructions for the agent")
    test_url_parser.add_argument("--email", help="Optional login email")
    test_url_parser.add_argument("--password", help="Optional login password")
    test_url_parser.add_argument(
        "--ttl",
        type=int,
        default=None,
        help="Run duration in minutes (Team/Paid: 1-480, default 30; Free: fixed at 10)",
    )
    test_url_parser.add_argument("--json", action="store_true", default=False, help="Output result as JSON")
    test_url_parser.add_argument("--repo", default=None, help="Repository (owner/repo) for diff-aware test planning")
    test_url_parser.add_argument("--branch", default=None, help="Branch name for diff-aware test planning")
    test_url_parser.add_argument(
        "--provision-id", default=None, help="Link to an existing twin provision (from 'arga twins provision')"
    )
    test_url_parser.set_defaults(func=run_test_url)

    validate_parser = subparsers.add_parser("validate", help="Start PR or URL validation runs")
    validate_subparsers = validate_parser.add_subparsers(dest="validate_command", required=True)

    validate_pr_parser = validate_subparsers.add_parser("pr", help="Run PR validation")
    validate_pr_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    validate_pr_parser.add_argument("--repo", required=True, help="Repository in owner/repo format")
    validate_pr_parser.add_argument("--pr", required=True, type=int, help="Pull request number")
    validate_pr_parser.add_argument("--json", action="store_true", default=False, help="Output result as JSON")
    validate_pr_parser.set_defaults(func=run_validate_pr)

    mcp_parser = subparsers.add_parser("mcp", help="Manage MCP integrations")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command", required=True)

    mcp_install_parser = mcp_subparsers.add_parser(
        "install",
        help="Install Arga MCP config into supported IDE agents",
    )
    mcp_install_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    mcp_install_parser.set_defaults(func=run_mcp_install)

    runs_parser = subparsers.add_parser("runs", help="List, inspect, cancel, or read validation run logs")
    runs_subparsers = runs_parser.add_subparsers(dest="runs_command", required=True)

    runs_list_parser = runs_subparsers.add_parser("list", help="List recent validation runs")
    runs_list_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    runs_list_parser.add_argument("--repo", help="Filter by repository in owner/repo format")
    runs_list_parser.add_argument(
        "--status",
        choices=("completed", "failed", "running"),
        help="Filter by validation status",
    )
    runs_list_parser.add_argument("--limit", type=int, default=20, help="Maximum number of runs to show")
    runs_list_parser.add_argument("--json", action="store_true", default=False, help="Output result as JSON")
    runs_list_parser.set_defaults(func=run_runs_list)

    runs_status_parser = runs_subparsers.add_parser("status", help="Show detailed status for a validation run")
    runs_status_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    runs_status_parser.add_argument("run_id", help="Validation run ID")
    runs_status_parser.add_argument("--json", action="store_true", default=False, help="Output result as JSON")
    runs_status_parser.set_defaults(func=run_runs_status)

    runs_logs_parser = runs_subparsers.add_parser("logs", help="Show worker and runtime logs for a validation run")
    runs_logs_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    runs_logs_parser.add_argument(
        "run_id",
        nargs="?",
        help=f"Validation run ID. Defaults to {WIZARD_SESSION_FILE} in the current directory when available.",
    )
    runs_logs_parser.add_argument("--json", action="store_true", help="Print the raw JSON response")
    runs_logs_parser.add_argument(
        "--errors-only",
        action="store_true",
        help="Show only failed worker logs and warning/error runtime logs",
    )
    runs_logs_parser.set_defaults(func=run_runs_logs)

    runs_cancel_parser = runs_subparsers.add_parser("cancel", help="Cancel a validation run")
    runs_cancel_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    runs_cancel_parser.add_argument("run_id", help="Validation run ID")
    runs_cancel_parser.set_defaults(func=run_runs_cancel)

    twins_parser = subparsers.add_parser("twins", help="Manage digital twin instances")
    twins_subparsers = twins_parser.add_subparsers(dest="twins_command", required=True)

    twins_provision_parser = twins_subparsers.add_parser("provision", help="Provision twin instances")
    twins_provision_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    twins_provision_parser.add_argument("--twins", required=True, help="Comma-separated twin names (e.g. stripe,slack)")
    twins_provision_parser.add_argument("--ttl", type=int, default=60, help="TTL in minutes (default 60)")
    twins_provision_parser.add_argument("--scenario", default=None, help="Scenario ID for pre-seeding")
    twins_provision_parser.add_argument("--json", action="store_true", default=False, help="Output as JSON")
    twins_provision_parser.set_defaults(func=run_twins_provision)

    twins_status_parser = twins_subparsers.add_parser("status", help="Check provision status")
    twins_status_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    twins_status_parser.add_argument("provision_id", help="Provision ID")
    twins_status_parser.add_argument("--json", action="store_true", default=False, help="Output as JSON")
    twins_status_parser.set_defaults(func=run_twins_status)

    twins_extend_parser = twins_subparsers.add_parser("extend", help="Extend provision TTL")
    twins_extend_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    twins_extend_parser.add_argument("provision_id", help="Provision ID")
    twins_extend_parser.add_argument("--minutes", type=int, default=60, help="Minutes to extend (default 60)")
    twins_extend_parser.set_defaults(func=run_twins_extend)

    twins_teardown_parser = twins_subparsers.add_parser("teardown", help="Tear down provision")
    twins_teardown_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    twins_teardown_parser.add_argument("provision_id", help="Provision ID")
    twins_teardown_parser.set_defaults(func=run_twins_teardown)

    build_entry_parser(subparsers)

    subparsers.add_parser("wizard", help="Twins quickstart wizard (run `arga wizard --help` for subcommands)")

    subparsers.add_parser("commit", help="Wrap git commit and optionally mark it to skip Arga validation")
    subparsers.add_parser("push", help="Wrap git push and verify skip state when requested")
    subparsers.add_parser("scan", help="Start an agent run or inspect a scan run")
    return parser


def main() -> None:
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "commit":
            exit_code = run_commit_cli(sys.argv[2:])
        elif len(sys.argv) > 1 and sys.argv[1] == "push":
            exit_code = run_push_cli(sys.argv[2:])
        elif len(sys.argv) > 1 and sys.argv[1] == "validate":
            exit_code = run_validate_cli(sys.argv[2:])
        elif len(sys.argv) > 1 and sys.argv[1] == "scan":
            exit_code = run_scan_cli(sys.argv[2:])
        elif len(sys.argv) > 1 and sys.argv[1] == "wizard":
            exit_code = run_wizard_cli(sys.argv[2:])
        else:
            parser = build_parser()
            args = parser.parse_args()
            exit_code = args.func(args)
    except CliError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    except httpx.HTTPError as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
