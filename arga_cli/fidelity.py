"""Markdown fidelity reports and deployment-aware, machine-readable polling."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import uuid
from pathlib import Path

import httpx

MAX_REPORT_BYTES = 256 * 1024
STAGES = (
    "submitted",
    "fixing",
    "verifying",
    "ci_review",
    "awaiting_review",
    "merged",
    "deploying",
    "deployed",
    "customer_verified",
)
STOPPED = {"needs_information", "not_reproduced", "needs_human", "failed", "cancelled", "closed", "customer_rejected"}


def _positive(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Must be a positive finite number")
    return number


def add_parser(subparsers, default_api_url: str) -> None:
    group = subparsers.add_parser(
        "fidelity-gaps", help="Submit connector fidelity reports and track fixes through deployment"
    )
    commands = group.add_subparsers(dest="fidelity_command", required=True)
    submit = commands.add_parser("submit", help="Upload one connector's UTF-8 Markdown report")
    submit.add_argument("file", type=Path)
    submit.add_argument("--connector", required=True)
    submit.add_argument(
        "--parent", type=uuid.UUID, default=None, help="Previous report ID for another verification round"
    )
    submit.add_argument("--idempotency-key", default=None, help="Retry key; defaults to a hash of report and context")
    get = commands.add_parser("get", aliases=["status"], help="Read report progress and deployed revision")
    get.add_argument("id", type=uuid.UUID)
    listing = commands.add_parser("list", help="List this account's reports")
    listing.add_argument("--limit", type=int, choices=range(1, 101), default=20, metavar="1-100")
    wait = commands.add_parser("wait", help="Wait for a stage; timeout never cancels the repair")
    wait.add_argument("id", type=uuid.UUID)
    wait.add_argument("--until", choices=STAGES, default="deployed")
    wait.add_argument("--timeout", type=_positive, default=3600)
    wait.add_argument("--poll-interval", type=_positive, default=15)
    verify = commands.add_parser("verify", help="Record customer eval results for the deployed revision")
    verify.add_argument("id", type=uuid.UUID)
    verify.add_argument("--revision", required=True)
    verify.add_argument("--outcome", choices=("passed", "failed"), required=True)
    verify.add_argument("--followup", type=uuid.UUID, default=None)
    for parser in (submit, get, listing, wait, verify):
        parser.add_argument("--api-url", default=default_api_url)
        parser.add_argument("--json", action="store_true")
        parser.set_defaults(func=run)


def run(args) -> int:
    # Import lazily to preserve the CLI's existing API/auth/error conventions.
    from arga_cli.main import ApiClient, CliError, RetryableApiError, load_api_key

    client = ApiClient(args.api_url, api_key=load_api_key())
    try:
        command = args.fidelity_command
        if command == "submit":
            try:
                if args.file.suffix.lower() != ".md" or args.file.stat().st_size > MAX_REPORT_BYTES:
                    raise CliError("Provide a Markdown (.md) report of at most 256 KiB")
                markdown = args.file.read_bytes().decode("utf-8")
            except (OSError, UnicodeError) as exc:
                raise CliError("Cannot read report as UTF-8 Markdown") from exc
            if not markdown.strip() or "\x00" in markdown:
                raise CliError("Report must contain Markdown without NUL characters")
            payload = {
                "connector": args.connector,
                "filename": args.file.stem + ".md",
                "markdown": markdown,
                "parent_id": str(args.parent) if args.parent else None,
            }
            payload["idempotency_key"] = (
                args.idempotency_key or hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            )
            result = client.fidelity_request("POST", "", payload)
        elif command == "list":
            result = client.fidelity_request("GET", f"?limit={args.limit}")
        elif command == "verify":
            result = client.fidelity_request(
                "POST",
                f"/{args.id}/verification",
                {
                    "deployed_revision": args.revision,
                    "outcome": args.outcome,
                    "followup_id": str(args.followup) if args.followup else None,
                },
            )
        elif command == "wait":
            deadline = time.monotonic() + args.timeout
            result = {
                "id": str(args.id),
                "status": "unknown",
                "next_action": "Status unavailable; retry polling with this report ID.",
            }
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _print({**result, "poll_status": "timed_out"}, args.json)
                    return 2
                retry_after = 0
                try:
                    result = client.fidelity_request("GET", f"/{args.id}", timeout=min(remaining, 60))
                except (RetryableApiError, httpx.TransportError) as exc:
                    retry_after = getattr(exc, "retry_after", 0)
                else:
                    # Milestones survive terminal states and follow-up rounds.
                    if args.until in result.get("milestones", {}) or result["status"] == args.until:
                        break
                    if result["status"] in STOPPED:
                        _print(result, args.json)
                        return 1
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    hint = result.get("poll_after_seconds", args.poll_interval)
                    time.sleep(min(max(args.poll_interval, hint, retry_after), remaining))
        else:
            result = client.fidelity_request("GET", f"/{args.id}")
        _print(result, args.json)
        return 0
    finally:
        client.close()


def _print(result: dict, as_json: bool) -> None:
    if as_json or "items" in result:
        print(json.dumps(result, indent=2))
        return
    print(f"Fidelity report: {result['id']}")
    if result.get("connector"):
        print(f"Connector: {result['connector']}")
    print(f"Status: {result['status']}")
    if result.get("poll_status") == "timed_out":
        print("Polling timed out. Use this report ID to check again.")
    for field in ("next_action", "deployed_revision", "requires_new_twin_run"):
        if result.get(field) is not None:
            print(f"{field.replace('_', ' ').capitalize()}: {result[field]}")
    if result.get("information_needed"):
        print("Information needed: " + ", ".join(value.replace("_", " ") for value in result["information_needed"]))
