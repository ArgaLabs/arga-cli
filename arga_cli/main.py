from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import httpx

from arga_cli.mcp import install_mcp_configuration

DEFAULT_API_URL = os.environ.get("ARGA_API_URL", "https://api.argalabs.com")
CONFIG_PATH = Path.home() / ".config" / "arga" / "config.json"
POLL_INTERVAL_SECONDS = 2.0
POLL_TIMEOUT_SECONDS = 600.0


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
        response = self._client.post(
            f"{self._api_url}/validate/url",
            json=payload,
            headers=self._auth_headers(),
        )
        return self._parse_json(response, "Failed to start URL validation")

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
    return 0


def run_test_url(args: argparse.Namespace) -> int:
    if bool(args.email) != bool(args.password):
        raise CliError("Both --email and --password must be provided together.")

    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        payload = client.start_url_validation(
            url=args.url,
            prompt=args.prompt,
            email=args.email,
            password=args.password,
        )
    finally:
        client.close()

    print("Starting validation...\n")
    print(f"URL: {args.url}")
    print(f"Prompt: {args.prompt}\n")
    print(f"Run ID: {payload.get('run_id', 'unknown')}")
    print(f"Status: {payload.get('status', 'unknown')}")
    return 0


def run_validate_pr(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    client = ApiClient(args.api_url, api_key=api_key)
    try:
        payload = client.start_pr_validation(repo=args.repo, pr_number=args.pr)
    finally:
        client.close()

    print("Starting PR validation...\n")
    print(f"Repository: {args.repo}")
    print(f"PR: #{args.pr}\n")
    print("Validation run started.")
    print(f"Run ID: {payload.get('run_id', 'unknown')}")
    print(f"Status: {payload.get('status', 'unknown')}")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arga")
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

    test_parser = subparsers.add_parser("test", help="Start validation runs")
    test_subparsers = test_parser.add_subparsers(dest="test_command", required=True)

    test_url_parser = test_subparsers.add_parser("url", help="Run a browser validation against a deployed URL")
    test_url_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    test_url_parser.add_argument("--url", required=True, help="Deployed application URL")
    test_url_parser.add_argument("--prompt", required=True, help="Natural language instructions for the agent")
    test_url_parser.add_argument("--email", help="Optional login email")
    test_url_parser.add_argument("--password", help="Optional login password")
    test_url_parser.set_defaults(func=run_test_url)

    validate_parser = subparsers.add_parser("validate", help="Start PR or URL validation runs")
    validate_subparsers = validate_parser.add_subparsers(dest="validate_command", required=True)

    validate_pr_parser = validate_subparsers.add_parser("pr", help="Run PR validation")
    validate_pr_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    validate_pr_parser.add_argument("--repo", required=True, help="Repository in owner/repo format")
    validate_pr_parser.add_argument("--pr", required=True, type=int, help="Pull request number")
    validate_pr_parser.set_defaults(func=run_validate_pr)

    validate_url_parser = validate_subparsers.add_parser(
        "url",
        help="Run a browser validation against a deployed URL",
    )
    validate_url_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    validate_url_parser.add_argument("--url", required=True, help="Deployed application URL")
    validate_url_parser.add_argument("--prompt", required=True, help="Natural language instructions for the agent")
    validate_url_parser.add_argument("--email", help="Optional login email")
    validate_url_parser.add_argument("--password", help="Optional login password")
    validate_url_parser.set_defaults(func=run_test_url)

    mcp_parser = subparsers.add_parser("mcp", help="Manage MCP integrations")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command", required=True)

    mcp_install_parser = mcp_subparsers.add_parser(
        "install",
        help="Install Arga MCP config into supported IDE agents",
    )
    mcp_install_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Arga API base URL")
    mcp_install_parser.set_defaults(func=run_mcp_install)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
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
