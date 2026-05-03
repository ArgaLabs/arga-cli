from __future__ import annotations

import argparse
import copy
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

from arga_cli.mcp import install_mcp_configuration

DEFAULT_API_URL = os.environ.get("ARGA_API_URL", "https://api.argalabs.com")
CONFIG_PATH = Path.home() / ".config" / "arga" / "config.json"
WIZARD_SESSION_FILE = ".arga-session.json"
WIZARD_SESSION_PATH = Path(WIZARD_SESSION_FILE)
POLL_INTERVAL_SECONDS = 2.0
POLL_TIMEOUT_SECONDS = 600.0
URL_VALIDATION_START_TIMEOUT_SECONDS = 60.0
SKIP_TRAILER = "[skip arga]"
TEST_CONFIG_ACTIONS = {"goto", "fill", "click", "press", "select", "hover", "expect", "wait", "ask_user_question"}
TEST_CONFIG_EXPECT_TYPES = {"text", "url", "visible"}


def _cli_version() -> str:
    try:
        return version("arga-cli")
    except PackageNotFoundError:
        return "unknown"


VERSION_CHECK_PATH = Path.home() / ".config" / "arga" / "version_check.json"
VERSION_CHECK_TTL_SECONDS = 86400  # 24 hours


def _check_for_update() -> None:
    """Print a warning if a newer version is available on PyPI. Caches for 24h."""
    try:
        current = _cli_version()
        if current == "unknown":
            return

        now = time.time()
        cached_latest: str | None = None
        if VERSION_CHECK_PATH.exists():
            data = json.loads(VERSION_CHECK_PATH.read_text())
            if now - data.get("checked_at", 0) < VERSION_CHECK_TTL_SECONDS:
                cached_latest = data.get("latest")

        if cached_latest is None:
            resp = httpx.get("https://pypi.org/pypi/arga-cli/json", timeout=3.0)
            resp.raise_for_status()
            cached_latest = resp.json()["info"]["version"]
            VERSION_CHECK_PATH.parent.mkdir(parents=True, exist_ok=True)
            VERSION_CHECK_PATH.write_text(json.dumps({"latest": cached_latest, "checked_at": now}))

        if cached_latest and cached_latest != current:
            latest_parts = tuple(int(x) for x in cached_latest.split("."))
            current_parts = tuple(int(x) for x in current.split("."))
            if latest_parts > current_parts:
                print(
                    f"\033[33mwarning: arga-cli {cached_latest} available (you have {current}). "
                    f"Update with: uv tool upgrade arga-cli\033[0m",
                    file=sys.stderr,
                )
    except Exception:
        pass


class CliError(Exception):
    """Base CLI error."""


class NotAuthenticatedError(CliError):
    """Raised when no local API key is available."""


class ApiClient:
    def __init__(self, api_url: str, api_key: str | None = None) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(timeout=60.0)

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
        prompt: str | None = None,
        email: str | None = None,
        password: str | None = None,
        ttl_minutes: int | None = None,
        scenario_id: str | None = None,
        provision_id: str | None = None,
        twins: list[str] | None = None,
        runner_mode: str | None = None,
        repo: str | None = None,
        branch: str | None = None,
        pr_url: str | None = None,
    ) -> dict[str, str]:
        payload: dict[str, object] = {"url": url}
        if prompt is not None:
            payload["prompt"] = prompt
        if email or password:
            payload["credentials"] = {
                "email": email or "",
                "password": password or "",
            }
        if ttl_minutes is not None:
            payload["ttl_minutes"] = ttl_minutes
        if scenario_id:
            payload["scenario_id"] = scenario_id
        if provision_id:
            payload["provision_id"] = provision_id
        if twins:
            payload["twins"] = twins
        if runner_mode:
            payload["runner_mode"] = runner_mode
        if repo:
            payload["repo"] = repo
        if branch:
            payload["branch"] = branch
        if pr_url:
            payload["pr_url"] = pr_url
        response = self._client.post(
            f"{self._api_url}/validate/url-run",
            json=payload,
            headers=self._auth_headers(),
            timeout=URL_VALIDATION_START_TIMEOUT_SECONDS,
        )
        return self._parse_json(response, "Failed to start URL validation")

    def list_scenarios(
        self,
        *,
        include_presets: bool = False,
        twin: str | None = None,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if include_presets:
            params["include_presets"] = "true"
        if twin:
            params["twin"] = twin
        if tag:
            params["tag"] = tag
        response = self._client.get(
            f"{self._api_url}/scenarios",
            params=params,
            headers=self._auth_headers(),
        )
        data = self._parse_json(response, "Failed to list scenarios")
        if not isinstance(data, list):
            raise CliError("Unexpected response from /scenarios")
        return data

    def create_scenario(
        self,
        *,
        name: str,
        prompt: str | None = None,
        description: str | None = None,
        twins: list[str] | None = None,
        seed_config: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name}
        if prompt is not None:
            payload["prompt"] = prompt
        if description is not None:
            payload["description"] = description
        if twins:
            payload["twins"] = twins
        if seed_config is not None:
            payload["seed_config"] = seed_config
        if tags:
            payload["tags"] = tags
        response = self._client.post(
            f"{self._api_url}/scenarios",
            json=payload,
            headers=self._auth_headers(),
            timeout=URL_VALIDATION_START_TIMEOUT_SECONDS,
        )
        return self._parse_json(response, "Failed to create scenario")

    def get_scenario(self, scenario_id: str) -> dict[str, Any]:
        response = self._client.get(
            f"{self._api_url}/scenarios/{scenario_id}",
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to load scenario")

    def update_scenario(self, scenario_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.put(
            f"{self._api_url}/scenarios/{scenario_id}",
            json=payload,
            headers=self._auth_headers(),
            timeout=URL_VALIDATION_START_TIMEOUT_SECONDS,
        )
        return self._parse_json(response, "Failed to update scenario")

    def delete_scenario(self, scenario_id: str) -> dict[str, str]:
        response = self._client.delete(
            f"{self._api_url}/scenarios/{scenario_id}",
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to delete scenario")

    def start_pr_run(
        self,
        *,
        repo: str,
        branch: str | None = None,
        pr_url: str | None = None,
        frontend_url: str | None = None,
        context_notes: str | None = None,
        scenario_prompt: str | None = None,
        scenario_id: str | None = None,
        twins: list[str] | None = None,
        session_id: str | None = None,
        run_type: str = "pr_run",
        stream: bool = True,
    ) -> dict[str, str]:
        payload: dict[str, Any] = {"repo": repo, "run_type": run_type}
        if branch:
            payload["branch"] = branch
        if pr_url:
            payload["pr_url"] = pr_url
        if frontend_url:
            payload["frontend_url"] = frontend_url
        if context_notes:
            payload["context_notes"] = context_notes
        if scenario_prompt:
            payload["scenario_prompt"] = scenario_prompt
        if scenario_id:
            payload["scenario_id"] = scenario_id
        if twins:
            payload["twins"] = twins
        if session_id:
            payload["session_id"] = session_id

        if not stream:
            response = self._client.post(
                f"{self._api_url}/validate/pr-run",
                json=payload,
                headers=self._auth_headers(),
            )
            return self._parse_json(response, "Failed to start preview run")

        with self._client.stream(
            "POST",
            f"{self._api_url}/validate/pr-run",
            json=payload,
            headers=self._auth_headers(),
            timeout=URL_VALIDATION_START_TIMEOUT_SECONDS,
        ) as response:
            if not response.is_success:
                try:
                    detail_payload = json.loads(response.read().decode("utf-8"))
                except ValueError as exc:
                    raise CliError("Failed to start preview run") from exc
                self._parse_json(
                    httpx.Response(response.status_code, json=detail_payload),
                    "Failed to start preview run",
                )
            run_id = response.headers.get("X-Run-Id")
            session_id_header = response.headers.get("X-Session-Id")
            # Drain the story stream so the server can finish its initial planning work.
            for _ in response.iter_text():
                pass
            return {"run_id": run_id or "unknown", "session_id": session_id_header or "", "status": "generating_story"}

    def start_pr_validation(
        self,
        *,
        repo: str,
        pr_number: int,
        context_notes: str | None = None,
    ) -> dict[str, str]:
        return self.start_pr_run(
            repo=repo,
            pr_url=f"https://github.com/{repo}/pull/{pr_number}",
            context_notes=context_notes,
            run_type="pr_run",
        )

    def provision_twins_start(
        self,
        *,
        twins: list[str],
        ttl_minutes: int,
        scenario_prompt: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"twins": twins, "ttl_minutes": ttl_minutes, "scenario": "quickstart"}
        if scenario_prompt:
            payload["scenario_prompt"] = scenario_prompt
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
        return self._parse_json(response, "Failed to load twin provision status")

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

    def create_demo_run(
        self,
        *,
        prompt: str,
        start_url: str | None = None,
        test_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"prompt": prompt}
        if start_url:
            payload["start_url"] = start_url
        if test_config is not None:
            payload["test_config"] = test_config
        response = self._client.post(
            f"{self._api_url}/demo-runner/runs",
            json=payload,
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to create test runner run")

    def list_demo_runs(self) -> list[dict[str, Any]]:
        response = self._client.get(
            f"{self._api_url}/demo-runner/runs",
            headers=self._auth_headers(),
        )
        payload = self._parse_json(response, "Failed to list test runner runs")
        runs = payload.get("runs") if isinstance(payload, dict) else None
        if not isinstance(runs, list):
            raise CliError("Unexpected response from /demo-runner/runs")
        return runs

    def get_demo_run(self, run_id: str) -> dict[str, Any]:
        response = self._client.get(
            f"{self._api_url}/demo-runner/runs/{run_id}",
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to load test runner run")

    def rerun_demo_run(
        self,
        run_id: str,
        *,
        prompt: str | None = None,
        start_url: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if prompt:
            payload["prompt"] = prompt
        if start_url:
            payload["start_url"] = start_url
        response = self._client.post(
            f"{self._api_url}/demo-runner/runs/{run_id}/rerun",
            json=payload,
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to rerun test runner run")

    def update_demo_run_config(self, run_id: str, test_config: dict[str, Any]) -> dict[str, Any]:
        response = self._client.patch(
            f"{self._api_url}/demo-runner/runs/{run_id}/config",
            json={"test_config": test_config},
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to update test runner config")

    def send_demo_run_message(self, run_id: str, message: str) -> dict[str, Any]:
        response = self._client.post(
            f"{self._api_url}/demo-runner/runs/{run_id}/messages",
            json={"message": message},
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to send test runner message")

    def list_demo_tests(self, *, repo: str | None = None) -> list[dict[str, Any]]:
        params = {"repo_full_name": repo} if repo else None
        response = self._client.get(
            f"{self._api_url}/demo-runner/tests",
            params=params,
            headers=self._auth_headers(),
        )
        payload = self._parse_json(response, "Failed to list saved tests")
        tests = payload.get("tests") if isinstance(payload, dict) else None
        if not isinstance(tests, list):
            raise CliError("Unexpected response from /demo-runner/tests")
        return tests

    def create_demo_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(
            f"{self._api_url}/demo-runner/tests",
            json=payload,
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to create saved test")

    def get_demo_test(self, test_id: str) -> dict[str, Any]:
        response = self._client.get(
            f"{self._api_url}/demo-runner/tests/{test_id}",
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to load saved test")

    def update_demo_test(self, test_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.patch(
            f"{self._api_url}/demo-runner/tests/{test_id}",
            json=payload,
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to update saved test")

    def delete_demo_test(self, test_id: str) -> dict[str, Any]:
        response = self._client.delete(
            f"{self._api_url}/demo-runner/tests/{test_id}",
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to delete saved test")

    def run_demo_test(
        self,
        test_id: str,
        *,
        start_url: str | None = None,
        prompt: str | None = None,
        twins: list[str] | None = None,
        ttl_minutes: int | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if start_url:
            payload["start_url"] = start_url
        if prompt:
            payload["prompt"] = prompt
        if twins:
            payload["twins"] = twins
        if ttl_minutes is not None:
            payload["ttl_minutes"] = ttl_minutes
        if session_id:
            payload["session_id"] = session_id
        response = self._client.post(
            f"{self._api_url}/demo-runner/tests/{test_id}/run",
            json=payload,
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to run saved test")

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
        message = str(detail) if detail else fallback
        if response.status_code == 401:
            raise NotAuthenticatedError("Error: Not authenticated. Run `arga login`.")
        if response.status_code == 403:
            if not detail:
                message += " Your plan may not support this feature. Check with `arga whoami`."
        elif response.status_code == 404:
            message += " Check that your plan supports this feature with `arga whoami`."
        elif response.status_code == 429:
            message += " Rate limit exceeded. Please wait and try again."
        elif response.status_code >= 500:
            message += " Server error. Please try again later."
        raise CliError(message)


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
    print(f"Email: {payload.get('email', 'not set')}")
    print(f"Email verified: {payload.get('email_verified', False)}")

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


def _warn_deprecated_alias(args: argparse.Namespace, replacement: str) -> None:
    if not getattr(args, "json", False) and getattr(args, "deprecated_alias", False):
        print(f"warning: this command is deprecated; use `{replacement}`.", file=sys.stderr)


def _split_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


def _read_json_file(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    try:
        payload = json.loads(file_path.read_text())
    except FileNotFoundError as exc:
        raise CliError(f"File not found: {file_path}") from exc
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid JSON in {file_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"Expected a JSON object in {file_path}")
    return payload


def _write_json_output(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).write_text(text)
    else:
        print(text, end="")


def _extract_test_config(payload: dict[str, Any]) -> dict[str, Any]:
    config = payload.get("test_config_json", payload.get("test_config", payload))
    if not isinstance(config, dict):
        raise CliError("Expected a TestConfig object or an object containing test_config/test_config_json.")
    return config


def _validate_test_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    steps = config.get("steps")
    if not isinstance(steps, list):
        errors.append("steps must be a list")
        return errors
    if "starting_url" in config and config["starting_url"] is not None and not isinstance(config["starting_url"], str):
        errors.append("starting_url must be a string")
    if "prompt" in config and config["prompt"] is not None and not isinstance(config["prompt"], str):
        errors.append("prompt must be a string")
    parameters = config.get("parameters", [])
    if parameters is not None and not isinstance(parameters, list):
        errors.append("parameters must be a list")

    for index, raw_step in enumerate(steps, start=1):
        label = f"steps[{index - 1}]"
        if not isinstance(raw_step, dict):
            errors.append(f"{label} must be an object")
            continue
        action = raw_step.get("action")
        if action not in TEST_CONFIG_ACTIONS:
            errors.append(f"{label}.action must be one of {', '.join(sorted(TEST_CONFIG_ACTIONS))}")
        if action == "expect":
            expect = raw_step.get("expect")
            if not isinstance(expect, dict):
                errors.append(f"{label}.expect must be an object")
                continue
            expect_type = expect.get("type")
            if expect_type not in TEST_CONFIG_EXPECT_TYPES:
                errors.append(f"{label}.expect.type must be one of text, url, visible")
            if expect_type in {"text", "url"} and not str(expect.get("contains") or "").strip():
                errors.append(f"{label}.expect.contains is required for {expect_type} assertions")
            if expect_type == "visible" and not str(raw_step.get("selector") or expect.get("selector") or "").strip():
                errors.append(f"{label}.selector is required for visible assertions")
    return errors


def _normalized_test_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(config)
    normalized.setdefault("version", 1)
    normalized.setdefault("fallback", "agent")
    normalized.setdefault("defaults", {})
    normalized.setdefault("parameters", [])
    steps = normalized.setdefault("steps", [])
    if not isinstance(steps, list):
        return normalized
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        step.setdefault("id", f"step_{index}")
        step.setdefault("ordinal", index)
        if step.get("action") == "expect" and isinstance(step.get("expect"), dict):
            expect = step["expect"]
            if expect.get("type") == "visible" and expect.get("selector") and not step.get("selector"):
                step["selector"] = expect.get("selector")
    return normalized


def _assert_valid_test_config(config: dict[str, Any]) -> None:
    errors = _validate_test_config(config)
    if errors:
        raise CliError("Invalid TestConfig:\n" + "\n".join(f"- {error}" for error in errors))


def _step_target(step: dict[str, Any]) -> str:
    return str(step.get("selector") or step.get("target") or step.get("wait_for") or step.get("value") or "-")


def _step_value(step: dict[str, Any]) -> str:
    action = step.get("action")
    if action == "expect":
        expect = step.get("expect") if isinstance(step.get("expect"), dict) else {}
        expect_type = str(expect.get("type") or "-")
        if expect_type == "visible":
            selector = str(step.get("selector") or expect.get("selector") or "-")
            return f"{selector} is visible"
        contains = str(expect.get("contains") or "")
        return f"{expect_type} contains {contains}" if contains else expect_type
    value = step.get("value")
    return "-" if value is None else str(value)


def _print_test_config_summary(config: dict[str, Any]) -> None:
    steps = config.get("steps") if isinstance(config.get("steps"), list) else []
    print(f"Prompt: {config.get('prompt') or '-'}")
    print(f"Starting URL: {config.get('starting_url') or '-'}")
    print(f"Fallback: {config.get('fallback') or '-'}")
    print(f"Parameters: {len(config.get('parameters') or [])}")
    print(f"Blocks: {len(steps)}")
    print()
    headers = ["#", "ACTION", "TARGET", "VALUE", "PARAMS"]
    rows: list[list[str]] = []
    for index, raw_step in enumerate(steps, start=1):
        step = raw_step if isinstance(raw_step, dict) else {}
        param_refs = step.get("parameter_refs")
        rows.append(
            [
                str(index),
                str(step.get("action") or "-"),
                _step_target(step),
                _step_value(step),
                ", ".join(str(item) for item in param_refs) if isinstance(param_refs, list) else "-",
            ]
        )
    widths = [
        max(len(headers[index]), max((len(row[index]) for row in rows), default=0)) for index in range(len(headers))
    ]
    print(" | ".join(headers[index].ljust(widths[index]) for index in range(len(headers))))
    print(" | ".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(row[index].ljust(widths[index]) for index in range(len(headers))))


def _print_twin_env_vars(status: dict) -> None:
    """Print twin URLs and env vars so the user can configure their app."""
    from arga_cli.wizard.provision import with_proxy_token

    proxy_token = status.get("proxy_token")
    # Public `pub-` hosts don't do proxy auth, so the base_url is directly
    # callable from any native SDK (Slack, Stripe, Discord, …). Appending
    # `?token=…` would be harmless but misleading — it'd suggest the token
    # is required, which is exactly the friction public twins eliminate.
    is_public = bool(status.get("is_public"))
    print("\nTwin environment variables — update your app's config to point at these:\n")
    for name, info in status.get("twins", {}).items():
        label = info.get("label", name)
        base_url = info.get("base_url", "")
        if not is_public and proxy_token and base_url:
            base_url = with_proxy_token(base_url, proxy_token)
        print(f"  {label}:")
        print(f"    Base URL: {base_url}")
        env_vars = info.get("env_vars", {})
        for key, val in env_vars.items():
            print(f"    {key}={val}")
        print()


def run_test_url(args: argparse.Namespace) -> int:
    _warn_deprecated_alias(args, "arga test-runner runs url")
    if bool(args.email) != bool(args.password):
        raise CliError("Both --email and --password must be provided together.")

    scenario_id = getattr(args, "scenario", None)
    test_config: dict[str, Any] | None = None
    test_config_file = getattr(args, "test_config", None)
    if test_config_file:
        test_config = _normalized_test_config(_extract_test_config(_read_json_file(test_config_file)))
        _assert_valid_test_config(test_config)

    if not args.prompt and not scenario_id and not test_config:
        raise CliError("Either --prompt or --scenario must be provided.")

    twins_arg = _split_csv(getattr(args, "twins", None))

    if not args.url and not twins_arg and not (test_config and test_config.get("starting_url")):
        raise CliError("--url is required (or use --twins to provision twins first).")

    url: str = args.url or ""

    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        ttl_minutes = _resolve_ttl(client, getattr(args, "ttl", None))

        provision_id: str | None = None
        if twins_arg:
            from arga_cli.wizard.provision import provision_twins

            status = provision_twins(client, twins_arg, ttl_minutes=ttl_minutes or 30)
            provision_id = status.get("run_id")
            _print_twin_env_vars(status)

            if not url:
                print("Deploy your app with the environment variables above.")
                print("Press Ctrl+C to cancel.\n")
                try:
                    url = input("Enter your staging URL: ").strip()
                except KeyboardInterrupt:
                    print("\nCancelled.")
                    return 1
                if not url:
                    raise CliError("A URL is required to start the validation run.")
                print()
            else:
                print(
                    "Deploy your app with the environment variables above, then press Enter to start the validation run."
                )
                print("Press Ctrl+C to cancel.\n")
                try:
                    input()
                except KeyboardInterrupt:
                    print("\nCancelled.")
                    return 1

        if test_config is not None:
            prompt = args.prompt or str(test_config.get("prompt") or "Run this saved browser test.")
            start_url = url or str(test_config.get("starting_url") or "")
            if not start_url:
                raise CliError("--url is required when --test-config has no starting_url.")
            payload = client.create_demo_run(prompt=prompt, start_url=start_url, test_config=test_config)
        else:
            start_kwargs: dict[str, Any] = {
                "url": url,
                "prompt": args.prompt,
                "email": args.email,
                "password": args.password,
                "ttl_minutes": ttl_minutes,
                "scenario_id": scenario_id,
                "provision_id": provision_id,
                "twins": twins_arg if not provision_id else None,
            }
            for key in ("runner_mode", "repo", "branch", "pr_url"):
                value = getattr(args, key, None)
                if value:
                    start_kwargs[key] = value
            payload = client.start_url_validation(**start_kwargs)
    finally:
        client.close()

    if getattr(args, "json", False):
        print(json.dumps({"run_id": payload.get("run_id") or payload.get("id"), "status": payload.get("status")}))
        return 0

    print("Starting validation...\n")
    print(f"URL: {url}")
    if args.prompt:
        print(f"Prompt: {args.prompt}")
    if scenario_id:
        print(f"Scenario: {scenario_id}")
    print(f"TTL: {ttl_minutes} minutes\n")
    print(f"Run ID: {payload.get('run_id') or payload.get('id', 'unknown')}")
    print(f"Status: {payload.get('status', 'unknown')}")
    return 0


def run_validate_pr(args: argparse.Namespace) -> int:
    _warn_deprecated_alias(args, "arga previews pr-checks run")
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        if any(
            getattr(args, name, None)
            for name in ("branch", "pr_url", "frontend_url", "scenario_prompt", "scenario_id", "twins", "session_id")
        ) or getattr(args, "run_type", "pr_run") != "pr_run":
            payload = client.start_pr_run(
                repo=args.repo,
                branch=getattr(args, "branch", None),
                pr_url=getattr(args, "pr_url", None)
                or (f"https://github.com/{args.repo}/pull/{args.pr}" if getattr(args, "pr", None) else None),
                frontend_url=getattr(args, "frontend_url", None),
                context_notes=getattr(args, "context_notes", None),
                scenario_prompt=getattr(args, "scenario_prompt", None),
                scenario_id=getattr(args, "scenario_id", None),
                twins=_split_csv(getattr(args, "twins", None)),
                session_id=getattr(args, "session_id", None),
                run_type=getattr(args, "run_type", "pr_run"),
            )
        else:
            kwargs: dict[str, Any] = {"repo": args.repo, "pr_number": args.pr}
            if getattr(args, "context_notes", None):
                kwargs["context_notes"] = args.context_notes
            payload = client.start_pr_validation(**kwargs)
    finally:
        client.close()

    if args.json:
        output = {"run_id": payload.get("run_id"), "status": payload.get("status")}
        if payload.get("session_id"):
            output["session_id"] = payload.get("session_id")
        print(json.dumps(output))
        return 0

    print("Starting PR validation...\n")
    print(f"Repository: {args.repo}")
    if getattr(args, "pr", None):
        print(f"PR: #{args.pr}\n")
    elif getattr(args, "pr_url", None):
        print(f"PR URL: {args.pr_url}\n")
    elif getattr(args, "branch", None):
        print(f"Branch: {args.branch}\n")
    print("Validation run started.")
    print(f"Run ID: {payload.get('run_id', 'unknown')}")
    print(f"Status: {payload.get('status', 'unknown')}")
    if payload.get("session_id"):
        print(f"Session ID: {payload['session_id']}")
    return 0


def run_previews_sandbox_run(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        payload = client.start_pr_run(
            repo=args.repo,
            branch=args.branch,
            pr_url=getattr(args, "pr_url", None),
            frontend_url=getattr(args, "frontend_url", None),
            context_notes=getattr(args, "context_notes", None),
            scenario_prompt=getattr(args, "scenario_prompt", None),
            scenario_id=getattr(args, "scenario_id", None),
            twins=_split_csv(getattr(args, "twins", None)),
            session_id=getattr(args, "session_id", None),
            run_type="agent_run",
        )
    finally:
        client.close()

    if args.json:
        print(json.dumps(payload))
        return 0

    print("Sandbox preview started.")
    print(f"Repository: {args.repo}")
    print(f"Branch: {args.branch}")
    print(f"Run ID: {payload.get('run_id', 'unknown')}")
    print(f"Status: {payload.get('status', 'unknown')}")
    if payload.get("session_id"):
        print(f"Session ID: {payload['session_id']}")
    return 0


def run_twins_provision(args: argparse.Namespace) -> int:
    twins = _split_csv(args.twins)
    if not twins:
        raise CliError("--twins must include at least one twin name.")
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        ttl_minutes = _resolve_ttl(client, args.ttl)
        status = client.provision_twins_start(
            twins=twins,
            ttl_minutes=ttl_minutes or 30,
            scenario_prompt=getattr(args, "scenario_prompt", None),
        )
        run_id = str(status.get("run_id") or "")
        if not run_id:
            raise CliError("Twin provisioning did not return a run_id.")
        if getattr(args, "wait", False):
            deadline = time.monotonic() + float(getattr(args, "timeout", 300))
            while time.monotonic() < deadline:
                status = client.get_twin_provision_status(run_id)
                if status.get("status") in {"ready", "failed"}:
                    break
                time.sleep(3.0)
    finally:
        client.close()

    if args.json:
        print(json.dumps(status, indent=2))
        return 0

    print("Twin provisioning started.")
    print(f"Run ID: {status.get('run_id', run_id)}")
    print(f"Status: {status.get('status', 'queued')}")
    if status.get("status") == "ready":
        _print_twin_env_vars(status)
    return 0


def run_twins_status(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        status = client.get_twin_provision_status(args.run_id)
    finally:
        client.close()

    if args.json:
        print(json.dumps(status, indent=2))
        return 0

    print(f"Run ID: {status.get('run_id', args.run_id)}")
    print(f"Status: {status.get('status', 'unknown')}")
    if status.get("status") == "ready":
        _print_twin_env_vars(status)
    return 0


def run_scenarios_list(args: argparse.Namespace) -> int:
    _warn_deprecated_alias(args, "arga test-runner scenarios list")
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        scenarios = client.list_scenarios(
            include_presets=getattr(args, "include_presets", False),
            twin=getattr(args, "twin", None),
            tag=getattr(args, "tag", None),
        )
    finally:
        client.close()

    if getattr(args, "json", False):
        print(json.dumps(scenarios, indent=2))
        return 0

    if not scenarios:
        print("No scenarios found. Create one with `arga scenarios create`.")
        return 0

    for s in scenarios:
        marker = " (preset)" if s.get("is_preset") else ""
        twins = ", ".join(s.get("twins") or []) or "-"
        tags = ", ".join(s.get("tags") or []) or "-"
        print(f"{s.get('id')}  {s.get('name')}{marker}")
        if s.get("description"):
            print(f"  description: {s['description']}")
        print(f"  twins: {twins}")
        print(f"  tags: {tags}")
        print()
    return 0


def run_scenarios_create(args: argparse.Namespace) -> int:
    _warn_deprecated_alias(args, "arga test-runner scenarios create")
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        scenario = client.create_scenario(
            name=args.name,
            prompt=args.prompt,
            description=getattr(args, "description", None),
            twins=getattr(args, "twin", None),
            seed_config=None,
            tags=getattr(args, "tag", None),
        )
    finally:
        client.close()

    if getattr(args, "json", False):
        print(json.dumps(scenario, indent=2))
        return 0

    print("Scenario created.")
    print(f"  id: {scenario.get('id')}")
    print(f"  name: {scenario.get('name')}")
    if scenario.get("twins"):
        print(f"  twins: {', '.join(scenario['twins'])}")
    return 0


def run_scenarios_get(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        scenario = client.get_scenario(args.scenario_id)
    finally:
        client.close()
    print(json.dumps(scenario, indent=2))
    return 0


def run_scenarios_import(args: argparse.Namespace) -> int:
    payload = _read_json_file(args.file)
    if "name" not in payload:
        raise CliError("Scenario import JSON must include name.")
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        scenario = client.create_scenario(
            name=str(payload["name"]),
            prompt=payload.get("prompt"),
            description=payload.get("description"),
            twins=payload.get("twins"),
            seed_config=payload.get("seed_config"),
            tags=payload.get("tags"),
        )
    finally:
        client.close()
    if args.json:
        print(json.dumps(scenario, indent=2))
    else:
        print("Scenario imported.")
        print(f"  id: {scenario.get('id')}")
        print(f"  name: {scenario.get('name')}")
    return 0


def run_scenarios_export(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        scenario = client.get_scenario(args.scenario_id)
    finally:
        client.close()
    _write_json_output(scenario, args.output)
    return 0


def run_scenarios_update(args: argparse.Namespace) -> int:
    payload = _read_json_file(args.file)
    payload.pop("id", None)
    payload.pop("created_at", None)
    payload.pop("updated_at", None)
    payload.pop("is_preset", None)
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        scenario = client.update_scenario(args.scenario_id, payload)
    finally:
        client.close()
    if args.json:
        print(json.dumps(scenario, indent=2))
    else:
        print("Scenario updated.")
        print(f"  id: {scenario.get('id')}")
        print(f"  name: {scenario.get('name')}")
    return 0


def run_scenarios_delete(args: argparse.Namespace) -> int:
    _warn_deprecated_alias(args, "arga test-runner scenarios delete")
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        result = client.delete_scenario(args.scenario_id)
    finally:
        client.close()

    if getattr(args, "json", False):
        print(json.dumps(result))
        return 0

    print(f"Deleted scenario {args.scenario_id}.")
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
    parser.add_argument(
        "--context-notes",
        help="Optional notes to focus the validation on specific changes",
    )
    parser.add_argument("--json", action="store_true", default=False, help="Output result as JSON")
    parser.set_defaults(deprecated_alias=True)
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


def _print_timeline_events(timeline_events: list[dict[str, Any]], *, limit: int = 50) -> None:
    print("Timeline:")
    if not timeline_events:
        print("None")
        return

    total = len(timeline_events)
    events = timeline_events[-limit:] if total > limit else timeline_events
    if total > limit:
        print(f"(showing last {len(events)} of {total} events)")

    for index, event in enumerate(events):
        if not isinstance(event, dict):
            continue
        timestamp = _format_timestamp(event.get("timestamp") or event.get("created_at"))
        event_type = str(event.get("type") or event.get("event_type") or "").strip()
        header_parts = [part for part in (timestamp, event_type) if part and part != "-"]
        header = " | ".join(header_parts) if header_parts else "event"
        print(header)

        message = str(event.get("message") or "").strip()
        if message:
            print(message)

        details = event.get("details")
        if isinstance(details, dict) and details:
            error_message = str(details.get("error_message") or details.get("error") or "").strip()
            if error_message and error_message != message:
                print(f"Error: {error_message}")

        if index < len(events) - 1:
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

    worker_logs_list = worker_logs if isinstance(worker_logs, list) else []
    runtime_logs_list = runtime_logs if isinstance(runtime_logs, list) else []
    timeline_events_list = timeline_events if isinstance(timeline_events, list) else []

    print()
    _print_worker_logs(worker_logs_list)
    print()
    _print_runtime_logs(runtime_logs_list)

    if not worker_logs_list and not runtime_logs_list and timeline_events_list:
        print()
        _print_timeline_events(timeline_events_list)

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


def _print_demo_runs_table(runs: list[dict[str, Any]]) -> None:
    headers = ["RUN_ID", "STATUS", "MODE", "START_URL", "UPDATED"]
    rows = [
        [
            str(run.get("id") or "-"),
            str(run.get("status") or "-"),
            str(run.get("mode") or "-"),
            str(run.get("start_url") or "-"),
            _format_timestamp(run.get("updated_at") or run.get("created_at")),
        ]
        for run in runs
    ]
    widths = [
        max(len(headers[index]), max((len(row[index]) for row in rows), default=0)) for index in range(len(headers))
    ]
    print(" | ".join(headers[index].ljust(widths[index]) for index in range(len(headers))))
    print(" | ".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(row[index].ljust(widths[index]) for index in range(len(headers))))


def _print_demo_run(run: dict[str, Any]) -> None:
    print(f"Run ID: {run.get('id', '-')}")
    print(f"Status: {run.get('status', '-')}")
    print(f"Mode: {run.get('mode', '-')}")
    print(f"Source Run: {run.get('source_run_id') or '-'}")
    print(f"Start URL: {run.get('start_url') or '-'}")
    print(f"Prompt: {run.get('prompt') or '-'}")
    print(f"Blocks: {len((run.get('test_config_json') or {}).get('steps') or [])}")
    print(f"Events: {len(run.get('events_json') or [])}")
    if run.get("error_message"):
        print(f"Error: {run['error_message']}")


def run_demo_runs_list(args: argparse.Namespace) -> int:
    _warn_deprecated_alias(args, "arga test-runner runs list")
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        runs = client.list_demo_runs()
    finally:
        client.close()
    if args.json:
        print(json.dumps(runs, indent=2))
        return 0
    if not runs:
        print("No test runner runs found.")
        return 0
    _print_demo_runs_table(runs)
    return 0


def run_demo_runs_get(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        run = client.get_demo_run(args.run_id)
    finally:
        client.close()
    if args.json:
        print(json.dumps(run, indent=2))
    else:
        _print_demo_run(run)
    return 0


def run_demo_runs_logs(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        run = client.get_demo_run(args.run_id)
    finally:
        client.close()
    events = run.get("events_json") or []
    if args.json:
        print(json.dumps(events, indent=2))
        return 0
    if not events:
        print("No events recorded for this test runner run.")
        return 0
    for event in events:
        if not isinstance(event, dict):
            continue
        header = " | ".join(
            part
            for part in (
                _format_timestamp(event.get("timestamp")),
                str(event.get("type") or "").strip(),
            )
            if part and part != "-"
        )
        print(header or "event")
        message = str(event.get("message") or "").strip()
        if message:
            print(message)
        print()
    return 0


def run_demo_runs_rerun(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        run = client.rerun_demo_run(args.run_id, prompt=args.prompt, start_url=args.url)
    finally:
        client.close()
    if args.json:
        print(json.dumps(run, indent=2))
    else:
        print("Test runner rerun started.")
        print(f"Run ID: {run.get('id', '-')}")
        print(f"Status: {run.get('status', '-')}")
    return 0


def run_demo_runs_message(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        run = client.send_demo_run_message(args.run_id, args.message)
    finally:
        client.close()
    if args.json:
        print(json.dumps(run, indent=2))
    else:
        print("Message sent.")
        print(f"Run ID: {run.get('id', args.run_id)}")
        print(f"Events: {len(run.get('events_json') or [])}")
    return 0


def _print_tests_table(tests: list[dict[str, Any]]) -> None:
    headers = ["TEST_ID", "NAME", "REPO", "CI", "BLOCKS", "UPDATED"]
    rows = []
    for test in tests:
        config = test.get("test_config_json") if isinstance(test.get("test_config_json"), dict) else {}
        rows.append(
            [
                str(test.get("id") or "-"),
                str(test.get("name") or "-"),
                str(test.get("repo_full_name") or "-"),
                "yes" if test.get("ci_enabled") else "no",
                str(len(config.get("steps") or [])),
                _format_timestamp(test.get("updated_at") or test.get("created_at")),
            ]
        )
    widths = [
        max(len(headers[index]), max((len(row[index]) for row in rows), default=0)) for index in range(len(headers))
    ]
    print(" | ".join(headers[index].ljust(widths[index]) for index in range(len(headers))))
    print(" | ".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(row[index].ljust(widths[index]) for index in range(len(headers))))


def _test_payload_from_file(path: str) -> dict[str, Any]:
    payload = _read_json_file(path)
    if "test_config_json" in payload and "test_config" not in payload:
        payload["test_config"] = payload.pop("test_config_json")
    if "test_config" in payload:
        config = _normalized_test_config(_extract_test_config(payload["test_config"] if isinstance(payload["test_config"], dict) else payload))
        _assert_valid_test_config(config)
        payload["test_config"] = config
    return payload


def run_tests_list(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        tests = client.list_demo_tests(repo=args.repo)
    finally:
        client.close()
    if args.json:
        print(json.dumps(tests, indent=2))
        return 0
    if not tests:
        print("No saved tests found.")
        return 0
    _print_tests_table(tests)
    return 0


def run_tests_get(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        test = client.get_demo_test(args.test_id)
    finally:
        client.close()
    if args.json:
        print(json.dumps(test, indent=2))
    else:
        print(f"Test ID: {test.get('id', args.test_id)}")
        print(f"Name: {test.get('name', '-')}")
        print(f"Repository: {test.get('repo_full_name') or '-'}")
        print(f"CI Enabled: {_bool_label(bool(test.get('ci_enabled')))}")
        print(f"Start URL: {test.get('start_url') or '-'}")
        print(f"Prompt: {test.get('prompt') or '-'}")
        print()
        _print_test_config_summary(test.get("test_config_json") or {})
    return 0


def run_tests_create(args: argparse.Namespace) -> int:
    payload: dict[str, Any] = {"name": args.name}
    for attr, key in (
        ("description", "description"),
        ("run_id", "run_id"),
        ("prompt", "prompt"),
        ("url", "start_url"),
        ("repo", "repo_full_name"),
    ):
        value = getattr(args, attr, None)
        if value:
            payload[key] = value
    if getattr(args, "ci", False):
        payload["ci_enabled"] = True
    if getattr(args, "tag", None):
        payload["tags"] = args.tag
    if getattr(args, "test_config", None):
        config = _normalized_test_config(_extract_test_config(_read_json_file(args.test_config)))
        _assert_valid_test_config(config)
        payload["test_config"] = config
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        test = client.create_demo_test(payload)
    finally:
        client.close()
    if args.json:
        print(json.dumps(test, indent=2))
    else:
        print("Saved test created.")
        print(f"Test ID: {test.get('id')}")
        print(f"Name: {test.get('name')}")
    return 0


def run_tests_import(args: argparse.Namespace) -> int:
    payload = _test_payload_from_file(args.file)
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        test = client.create_demo_test(payload)
    finally:
        client.close()
    if args.json:
        print(json.dumps(test, indent=2))
    else:
        print("Saved test imported.")
        print(f"Test ID: {test.get('id')}")
        print(f"Name: {test.get('name')}")
    return 0


def run_tests_export(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        test = client.get_demo_test(args.test_id)
    finally:
        client.close()
    _write_json_output(test, args.output)
    return 0


def run_tests_edit(args: argparse.Namespace) -> int:
    editor = os.environ.get("EDITOR")
    if not editor:
        raise CliError("Set $EDITOR to use `arga test-runner tests edit`.")
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        test = client.get_demo_test(args.test_id)
        editable = {
            "name": test.get("name"),
            "description": test.get("description"),
            "prompt": test.get("prompt"),
            "start_url": test.get("start_url"),
            "repo_full_name": test.get("repo_full_name"),
            "ci_enabled": test.get("ci_enabled"),
            "tags": test.get("tags") or [],
            "test_config": test.get("test_config_json") or {},
        }
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False, encoding="utf-8") as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(json.dumps(editable, indent=2, sort_keys=True) + "\n")
        try:
            subprocess.run([editor, str(tmp_path)], check=True)
            payload = _test_payload_from_file(str(tmp_path))
        finally:
            tmp_path.unlink(missing_ok=True)
        updated = client.update_demo_test(args.test_id, payload)
    finally:
        client.close()
    if args.json:
        print(json.dumps(updated, indent=2))
    else:
        print("Saved test updated.")
        print(f"Test ID: {updated.get('id')}")
        print(f"Name: {updated.get('name')}")
    return 0


def run_tests_delete(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        result = client.delete_demo_test(args.test_id)
    finally:
        client.close()
    if args.json:
        print(json.dumps(result))
    else:
        print(f"Deleted saved test {args.test_id}.")
    return 0


def run_tests_run(args: argparse.Namespace) -> int:
    twins_arg = _split_csv(args.twins)
    start_url = args.url
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        ttl_minutes = _resolve_ttl(client, args.ttl)
        if twins_arg:
            from arga_cli.wizard.provision import provision_twins

            status = provision_twins(client, twins_arg, ttl_minutes=ttl_minutes or 30)
            _print_twin_env_vars(status)
            if not start_url:
                print("Deploy your app with the environment variables above.")
                print("Press Ctrl+C to cancel.\n")
                try:
                    start_url = input("Enter your staging URL: ").strip()
                except KeyboardInterrupt:
                    print("\nCancelled.")
                    return 1
                if not start_url:
                    raise CliError("A URL is required to start the saved test run.")
                print()
            else:
                print("Deploy your app with the environment variables above, then press Enter to start the saved test.")
                print("Press Ctrl+C to cancel.\n")
                try:
                    input()
                except KeyboardInterrupt:
                    print("\nCancelled.")
                    return 1
        run = client.run_demo_test(
            args.test_id,
            start_url=start_url,
            prompt=args.prompt,
            twins=twins_arg,
            ttl_minutes=ttl_minutes,
            session_id=args.session_id,
        )
    finally:
        client.close()
    if args.json:
        print(json.dumps(run, indent=2))
    else:
        print("Saved test run started.")
        print(f"Run ID: {run.get('id') or run.get('run_id') or '-'}")
        print(f"Status: {run.get('status', '-')}")
        print(f"Start URL: {run.get('start_url') or start_url or '-'}")
    return 0


def run_tests_config_validate(args: argparse.Namespace) -> int:
    config = _normalized_test_config(_extract_test_config(_read_json_file(args.file)))
    errors = _validate_test_config(config)
    if args.json:
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
        return 0 if not errors else 1
    if errors:
        print("Invalid TestConfig:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("TestConfig is valid.")
    return 0


def run_tests_config_summarize(args: argparse.Namespace) -> int:
    config = _normalized_test_config(_extract_test_config(_read_json_file(args.file)))
    _assert_valid_test_config(config)
    if args.json:
        print(json.dumps(config, indent=2))
    else:
        _print_test_config_summary(config)
    return 0


def run_tests_config_normalize(args: argparse.Namespace) -> int:
    config = _normalized_test_config(_extract_test_config(_read_json_file(args.file)))
    _assert_valid_test_config(config)
    _write_json_output(config, args.output)
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
        description=(
            f"Wrap `git {command}` with optional Arga-specific behavior. "
            f"All unrecognized flags are forwarded to `git {command}`."
        ),
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
        "  --ttl MINUTES        Session TTL in minutes (paid/team: 1-480, default 60; free: fixed 10)\n"
        "  --no-shape-detect    Disable heuristic detection of API keys by value pattern\n"
        "  -h, --help           Show this help"
    )


def _build_wizard_init_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arga wizard", allow_abbrev=False)
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    parser.add_argument("--ttl", type=int, default=None, help="Session TTL in minutes (paid/team: 1-480, default 60)")
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
        ttl_minutes=args.ttl,
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
    # Public `pub-` hosts are drop-in callable without the proxy token; only
    # decorate private hosts so the printed URL accurately reflects what
    # the user needs to use.
    is_public = bool(status.get("is_public"))
    proxy_token = status.get("proxy_token")
    for name, info in status.get("twins", {}).items():
        label = TWIN_CATALOG.get(name, {}).get("label", name).ljust(16)
        base_url = info.get("base_url", "")
        url = base_url if is_public else with_proxy_token(base_url, proxy_token)
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

    try:
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
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    raise CliError(f"Unknown wizard subcommand: {command}")


def _add_url_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    parser.add_argument(
        "--url", default=None, help="Deployed application URL (prompted after twin provisioning when --twins is used)"
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Natural language instructions for the agent (optional when --scenario or --test-config is provided)",
    )
    parser.add_argument("--scenario", default=None, help="Scenario ID to seed twins from")
    parser.add_argument("--scenario-id", dest="scenario", help=argparse.SUPPRESS)
    parser.add_argument("--test-config", default=None, help="Path to a TestConfig JSON file")
    parser.add_argument("--twins", default=None, help="Comma-separated twins to provision before the run")
    parser.add_argument("--runner-mode", default=None, help="Manual runner mode override")
    parser.add_argument("--repo", default=None, help="Repository in owner/repo format")
    parser.add_argument("--branch", default=None, help="Branch associated with this URL run")
    parser.add_argument("--pr-url", default=None, help="Pull request URL associated with this URL run")
    parser.add_argument("--email", help="Optional login email")
    parser.add_argument("--password", help="Optional login password")
    parser.add_argument("--ttl", type=int, default=None, help="Run duration in minutes")
    parser.add_argument("--json", action="store_true", default=False, help="Output result as JSON")


def _add_scenario_parsers(subparsers: argparse._SubParsersAction, *, deprecated_alias: bool = False) -> None:
    scenarios_list_parser = subparsers.add_parser("list", help="List your scenarios")
    scenarios_list_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    scenarios_list_parser.add_argument("--include-presets", action="store_true", default=False)
    scenarios_list_parser.add_argument("--twin", default=None, help="Filter by twin")
    scenarios_list_parser.add_argument("--tag", default=None, help="Filter by tag")
    scenarios_list_parser.add_argument("--json", action="store_true", default=False, help="Output as JSON")
    scenarios_list_parser.set_defaults(func=run_scenarios_list, deprecated_alias=deprecated_alias)

    scenarios_get_parser = subparsers.add_parser("get", help="Get a scenario as JSON")
    scenarios_get_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    scenarios_get_parser.add_argument("scenario_id", help="Scenario ID")
    scenarios_get_parser.set_defaults(func=run_scenarios_get)

    scenarios_create_parser = subparsers.add_parser("create", help="Create a scenario from a prompt")
    scenarios_create_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    scenarios_create_parser.add_argument("--name", required=True, help="Scenario name")
    scenarios_create_parser.add_argument("--prompt", required=True, help="Natural-language twin state")
    scenarios_create_parser.add_argument("--description", default=None, help="Optional description")
    scenarios_create_parser.add_argument("--twin", action="append", default=None, help="Restrict to a twin (repeatable)")
    scenarios_create_parser.add_argument("--tag", action="append", default=None, help="Tag the scenario (repeatable)")
    scenarios_create_parser.add_argument("--json", action="store_true", default=False, help="Output as JSON")
    scenarios_create_parser.set_defaults(func=run_scenarios_create, deprecated_alias=deprecated_alias)

    scenarios_import_parser = subparsers.add_parser("import", help="Import a scenario JSON file")
    scenarios_import_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    scenarios_import_parser.add_argument("--file", required=True, help="Scenario JSON file")
    scenarios_import_parser.add_argument("--json", action="store_true", default=False, help="Output as JSON")
    scenarios_import_parser.set_defaults(func=run_scenarios_import)

    scenarios_export_parser = subparsers.add_parser("export", help="Export a scenario JSON file")
    scenarios_export_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    scenarios_export_parser.add_argument("scenario_id", help="Scenario ID")
    scenarios_export_parser.add_argument("--output", "-o", default=None, help="Output file; defaults to stdout")
    scenarios_export_parser.set_defaults(func=run_scenarios_export)

    scenarios_update_parser = subparsers.add_parser("update", help="Update a scenario from JSON")
    scenarios_update_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    scenarios_update_parser.add_argument("scenario_id", help="Scenario ID")
    scenarios_update_parser.add_argument("--file", required=True, help="Scenario JSON file")
    scenarios_update_parser.add_argument("--json", action="store_true", default=False, help="Output as JSON")
    scenarios_update_parser.set_defaults(func=run_scenarios_update)

    scenarios_delete_parser = subparsers.add_parser("delete", help="Delete a scenario")
    scenarios_delete_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    scenarios_delete_parser.add_argument("scenario_id", help="Scenario ID to delete")
    scenarios_delete_parser.add_argument("--json", action="store_true", default=False, help="Output as JSON")
    scenarios_delete_parser.set_defaults(func=run_scenarios_delete, deprecated_alias=deprecated_alias)


def _add_saved_test_parsers(subparsers: argparse._SubParsersAction) -> None:
    list_parser = subparsers.add_parser("list", help="List saved tests")
    list_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    list_parser.add_argument("--repo", default=None, help="Filter by repository")
    list_parser.add_argument("--json", action="store_true", default=False)
    list_parser.set_defaults(func=run_tests_list)

    get_parser = subparsers.add_parser("get", help="Get a saved test")
    get_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    get_parser.add_argument("test_id", help="Saved test ID")
    get_parser.add_argument("--json", action="store_true", default=False)
    get_parser.set_defaults(func=run_tests_get)

    create_parser = subparsers.add_parser("create", help="Create a saved test")
    create_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    create_parser.add_argument("--name", required=True, help="Saved test name")
    create_parser.add_argument("--description", default=None)
    create_parser.add_argument("--run-id", default=None, help="Source demo runner run ID")
    create_parser.add_argument("--test-config", default=None, help="TestConfig JSON file")
    create_parser.add_argument("--prompt", default=None)
    create_parser.add_argument("--url", default=None, help="Start URL")
    create_parser.add_argument("--repo", default=None, help="Repository in owner/repo format")
    create_parser.add_argument("--ci", action="store_true", default=False, help="Enable for CI checks")
    create_parser.add_argument("--tag", action="append", default=None)
    create_parser.add_argument("--json", action="store_true", default=False)
    create_parser.set_defaults(func=run_tests_create)

    import_parser = subparsers.add_parser("import", help="Import a saved test JSON file")
    import_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    import_parser.add_argument("--file", required=True)
    import_parser.add_argument("--json", action="store_true", default=False)
    import_parser.set_defaults(func=run_tests_import)

    export_parser = subparsers.add_parser("export", help="Export a saved test JSON file")
    export_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    export_parser.add_argument("test_id")
    export_parser.add_argument("--output", "-o", default=None)
    export_parser.set_defaults(func=run_tests_export)

    edit_parser = subparsers.add_parser("edit", help="Edit a saved test in $EDITOR")
    edit_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    edit_parser.add_argument("test_id")
    edit_parser.add_argument("--json", action="store_true", default=False)
    edit_parser.set_defaults(func=run_tests_edit)

    delete_parser = subparsers.add_parser("delete", help="Delete a saved test")
    delete_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    delete_parser.add_argument("test_id")
    delete_parser.add_argument("--json", action="store_true", default=False)
    delete_parser.set_defaults(func=run_tests_delete)

    run_parser = subparsers.add_parser("run", help="Run a saved test")
    run_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    run_parser.add_argument("test_id")
    run_parser.add_argument("--url", default=None, help="Override start URL")
    run_parser.add_argument("--prompt", default=None, help="Override prompt")
    run_parser.add_argument("--twins", default=None, help="Comma-separated twins")
    run_parser.add_argument("--ttl", type=int, default=None)
    run_parser.add_argument("--session-id", default=None)
    run_parser.add_argument("--json", action="store_true", default=False)
    run_parser.set_defaults(func=run_tests_run)

    config_parser = subparsers.add_parser("config", help="Validate and summarize TestConfig files")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    validate_parser = config_subparsers.add_parser("validate", help="Validate a TestConfig JSON file")
    validate_parser.add_argument("--file", required=True)
    validate_parser.add_argument("--json", action="store_true", default=False)
    validate_parser.set_defaults(func=run_tests_config_validate)
    summarize_parser = config_subparsers.add_parser("summarize", help="Summarize a TestConfig JSON file")
    summarize_parser.add_argument("--file", required=True)
    summarize_parser.add_argument("--json", action="store_true", default=False)
    summarize_parser.set_defaults(func=run_tests_config_summarize)
    normalize_parser = config_subparsers.add_parser("normalize", help="Normalize a TestConfig JSON file")
    normalize_parser.add_argument("--file", required=True)
    normalize_parser.add_argument("--output", "-o", default=None)
    normalize_parser.set_defaults(func=run_tests_config_normalize)


def _add_demo_run_parsers(subparsers: argparse._SubParsersAction, *, deprecated_alias: bool = False) -> None:
    url_parser = subparsers.add_parser("url", help="Run a browser validation against a deployed URL")
    _add_url_run_arguments(url_parser)
    url_parser.set_defaults(func=run_test_url, deprecated_alias=deprecated_alias)

    list_parser = subparsers.add_parser("list", help="List recent test runner runs")
    list_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    list_parser.add_argument("--json", action="store_true", default=False)
    list_parser.set_defaults(func=run_demo_runs_list, deprecated_alias=deprecated_alias)

    get_parser = subparsers.add_parser("get", help="Get a test runner run")
    get_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    get_parser.add_argument("run_id")
    get_parser.add_argument("--json", action="store_true", default=False)
    get_parser.set_defaults(func=run_demo_runs_get)

    logs_parser = subparsers.add_parser("logs", help="Show test runner events")
    logs_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    logs_parser.add_argument("run_id")
    logs_parser.add_argument("--json", action="store_true", default=False)
    logs_parser.set_defaults(func=run_demo_runs_logs)

    rerun_parser = subparsers.add_parser("rerun", help="Rerun a test runner run")
    rerun_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    rerun_parser.add_argument("run_id")
    rerun_parser.add_argument("--prompt", default=None)
    rerun_parser.add_argument("--url", default=None)
    rerun_parser.add_argument("--json", action="store_true", default=False)
    rerun_parser.set_defaults(func=run_demo_runs_rerun)

    message_parser = subparsers.add_parser("message", help="Send a message to a live test runner run")
    message_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    message_parser.add_argument("run_id")
    message_parser.add_argument("message")
    message_parser.add_argument("--json", action="store_true", default=False)
    message_parser.set_defaults(func=run_demo_runs_message)


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

    previews_parser = subparsers.add_parser("previews", help="Manage preview environments")
    previews_subparsers = previews_parser.add_subparsers(dest="previews_command", required=True)

    sandboxes_parser = previews_subparsers.add_parser("sandboxes", help="Run sandbox preview environments")
    sandboxes_subparsers = sandboxes_parser.add_subparsers(dest="sandboxes_command", required=True)
    sandbox_run_parser = sandboxes_subparsers.add_parser("run", help="Run a sandbox preview for a branch or PR")
    sandbox_run_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    sandbox_run_parser.add_argument("--repo", required=True, help="Repository in owner/repo format")
    sandbox_run_parser.add_argument("--branch", required=True, help="Branch to deploy into the sandbox")
    sandbox_run_parser.add_argument("--pr-url", default=None, help="Pull request URL when this sandbox is PR-backed")
    sandbox_run_parser.add_argument("--frontend-url", default=None, help="Frontend URL to validate after deploy")
    sandbox_run_parser.add_argument("--context-notes", default=None, help="Additional sandbox instructions")
    sandbox_run_parser.add_argument("--scenario-prompt", default=None, help="Scenario seed prompt for twins")
    sandbox_run_parser.add_argument("--scenario-id", default=None, help="Saved scenario ID to seed twins")
    sandbox_run_parser.add_argument("--twins", default=None, help="Comma-separated twins to include")
    sandbox_run_parser.add_argument("--session-id", default=None, help="Reuse an existing validation session")
    sandbox_run_parser.add_argument("--json", action="store_true", default=False, help="Output result as JSON")
    sandbox_run_parser.set_defaults(func=run_previews_sandbox_run)

    pr_checks_parser = previews_subparsers.add_parser("pr-checks", help="Run and configure PR checks")
    pr_checks_subparsers = pr_checks_parser.add_subparsers(dest="pr_checks_command", required=True)
    pr_checks_run_parser = pr_checks_subparsers.add_parser("run", help="Run a PR check")
    pr_checks_run_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    pr_checks_run_parser.add_argument("--repo", required=True, help="Repository in owner/repo format")
    pr_checks_run_parser.add_argument("--pr-url", default=None, help="Pull request URL")
    pr_checks_run_parser.add_argument("--pr", type=int, default=None, help="Pull request number")
    pr_checks_run_parser.add_argument("--branch", default=None, help="Branch to validate")
    pr_checks_run_parser.add_argument("--frontend-url", default=None, help="Frontend URL to validate")
    pr_checks_run_parser.add_argument("--context-notes", default=None, help="Additional instructions")
    pr_checks_run_parser.add_argument("--scenario-prompt", default=None, help="Scenario seed prompt for twins")
    pr_checks_run_parser.add_argument("--scenario-id", default=None, help="Saved scenario ID to seed twins")
    pr_checks_run_parser.add_argument("--twins", default=None, help="Comma-separated twins to include")
    pr_checks_run_parser.add_argument("--session-id", default=None, help="Reuse an existing validation session")
    pr_checks_run_parser.add_argument("--run-type", default="pr_run", choices=("pr_run", "agent_run"))
    pr_checks_run_parser.add_argument("--json", action="store_true", default=False, help="Output result as JSON")
    pr_checks_run_parser.set_defaults(func=run_validate_pr)
    pr_checks_install_parser = pr_checks_subparsers.add_parser("install", help="Install automatic PR checks")
    pr_checks_install_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    pr_checks_install_parser.add_argument("repo", help="Repository in owner/repo format")
    pr_checks_install_parser.set_defaults(func=run_validate_install)
    pr_checks_config_parser = pr_checks_subparsers.add_parser("config", help="Show PR check config")
    pr_checks_config_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    pr_checks_config_parser.add_argument("repo", help="Repository in owner/repo format")
    pr_checks_config_parser.set_defaults(func=run_validate_config)
    pr_checks_config_set_parser = pr_checks_subparsers.add_parser("config-set", help="Save PR check config")
    pr_checks_config_set_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    pr_checks_config_set_parser.add_argument("repo", help="Repository in owner/repo format")
    pr_checks_config_set_parser.add_argument("--trigger", choices=("pr", "branch"), help="Validation trigger mode")
    pr_checks_config_set_parser.add_argument("--branch", help="Branch to monitor when using branch trigger mode")
    pr_checks_config_set_parser.add_argument("--comments", choices=("on", "off"), help="Whether PR comments are enabled")
    pr_checks_config_set_parser.set_defaults(func=run_validate_config_set)

    twins_parser = previews_subparsers.add_parser("twins", help="Provision twins")
    twins_subparsers = twins_parser.add_subparsers(dest="twins_command", required=True)
    twins_provision_parser = twins_subparsers.add_parser("provision", help="Provision one or more twins")
    twins_provision_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    twins_provision_parser.add_argument("--twins", required=True, help="Comma-separated twins, e.g. jira,slack")
    twins_provision_parser.add_argument("--ttl", type=int, default=None, help="TTL in minutes")
    twins_provision_parser.add_argument("--scenario-prompt", default=None, help="Scenario prompt to seed twins")
    twins_provision_parser.add_argument("--wait", action="store_true", default=False, help="Wait until twins are ready")
    twins_provision_parser.add_argument("--timeout", type=int, default=300, help="Wait timeout in seconds")
    twins_provision_parser.add_argument("--json", action="store_true", default=False, help="Output result as JSON")
    twins_provision_parser.set_defaults(func=run_twins_provision)
    twins_status_parser = twins_subparsers.add_parser("status", help="Show twin provisioning status")
    twins_status_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    twins_status_parser.add_argument("run_id", help="Twin provisioning run ID")
    twins_status_parser.add_argument("--json", action="store_true", default=False, help="Output result as JSON")
    twins_status_parser.set_defaults(func=run_twins_status)

    test_runner_parser = subparsers.add_parser("test-runner", help="Manage scenarios, saved tests, and test runs")
    test_runner_subparsers = test_runner_parser.add_subparsers(dest="test_runner_command", required=True)

    scenarios_parser = test_runner_subparsers.add_parser("scenarios", help="Manage twin seed scenarios")
    scenarios_subparsers = scenarios_parser.add_subparsers(dest="scenarios_command", required=True)
    _add_scenario_parsers(scenarios_subparsers)

    tests_parser = test_runner_subparsers.add_parser("tests", help="Manage saved browser tests")
    tests_subparsers = tests_parser.add_subparsers(dest="tests_command", required=True)
    _add_saved_test_parsers(tests_subparsers)

    demo_runs_parser = test_runner_subparsers.add_parser("runs", help="Run and inspect live browser tests")
    demo_runs_subparsers = demo_runs_parser.add_subparsers(dest="demo_runs_command", required=True)
    _add_demo_run_parsers(demo_runs_subparsers)

    test_parser = subparsers.add_parser("test", help="Deprecated alias for test-runner runs")
    test_subparsers = test_parser.add_subparsers(dest="test_command", required=True)
    test_url_parser = test_subparsers.add_parser("url", help="Deprecated alias for test-runner runs url")
    _add_url_run_arguments(test_url_parser)
    test_url_parser.set_defaults(func=run_test_url, deprecated_alias=True)

    scenarios_alias_parser = subparsers.add_parser("scenarios", help="Deprecated alias for test-runner scenarios")
    scenarios_alias_subparsers = scenarios_alias_parser.add_subparsers(dest="scenarios_command", required=True)
    _add_scenario_parsers(scenarios_alias_subparsers, deprecated_alias=True)

    validate_parser = subparsers.add_parser("validate", help="Deprecated alias for previews pr-checks")
    validate_subparsers = validate_parser.add_subparsers(dest="validate_command", required=True)
    validate_pr_parser = validate_subparsers.add_parser("pr", help="Deprecated alias for previews pr-checks run")
    validate_pr_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    validate_pr_parser.add_argument("--repo", required=True, help="Repository in owner/repo format")
    validate_pr_parser.add_argument("--pr", required=True, type=int, help="Pull request number")
    validate_pr_parser.add_argument("--context-notes", default=None, help="Additional instructions or context")
    validate_pr_parser.add_argument("--json", action="store_true", default=False, help="Output result as JSON")
    validate_pr_parser.set_defaults(func=run_validate_pr, deprecated_alias=True)

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

    subparsers.add_parser("wizard", help="Twins quickstart wizard (run `arga wizard --help` for subcommands)")

    subparsers.add_parser("commit", help="Wrap git commit and optionally mark it to skip Arga validation")
    subparsers.add_parser("push", help="Wrap git push and verify skip state when requested")
    return parser


def main() -> None:
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "commit":
            exit_code = run_commit_cli(sys.argv[2:])
        elif len(sys.argv) > 1 and sys.argv[1] == "push":
            exit_code = run_push_cli(sys.argv[2:])
        elif len(sys.argv) > 1 and sys.argv[1] == "validate":
            exit_code = run_validate_cli(sys.argv[2:])
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
    _check_for_update()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
