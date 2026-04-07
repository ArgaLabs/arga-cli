"""arga entry — Dockerfile injection for twin routing via MITM proxy."""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_ENTRY_SCRIPT_PATH = _ASSETS_DIR / "arga-entry"

_MISSING_SCRIPT_MSG = "arga-entry script not found. Reinstall arga-cli or check that arga_cli/assets/arga-entry exists."


def _load_entry_script() -> str:
    if _ENTRY_SCRIPT_PATH.exists():
        return _ENTRY_SCRIPT_PATH.read_text()
    raise RuntimeError(_MISSING_SCRIPT_MSG)


INJECT_MARKER = "# --- arga twin interception ---"

DOCKERFILE_SNIPPET = textwrap.dedent("""\
    # --- arga twin interception ---
    COPY arga-entry /arga/arga-entry
    RUN chmod +x /arga/arga-entry
    ENV NODE_OPTIONS="--use-openssl-ca"
    ENTRYPOINT ["/arga/arga-entry", "run", "--"]
""")

RUNTIME_INSTRUCTIONS = textwrap.dedent("""\
    Next steps:
      1. Build your image:    docker build -t myapp .
      2. Mount the CA cert and set routing at runtime:

         # With a twin provision:
         arga twins provision --twins slack,stripe
         arga twins status <provision-id>   # get gateway URL

         # Run with CA cert + proxy routing:
         docker run \\
           -v /path/to/ca.crt:/arga/ca.crt:ro \\
           -e HTTPS_PROXY=<gateway-url> \\
           -e REQUESTS_CA_BUNDLE=/arga/ca.crt \\
           myapp

         # Or with DNS-based routing (extra_hosts):
         docker run \\
           -v /path/to/ca.crt:/arga/ca.crt:ro \\
           --add-host api.slack.com:<gateway-ip> \\
           --add-host api.stripe.com:<gateway-ip> \\
           myapp
""")


def _find_last_from_line(lines: list[str]) -> int:
    """Find the line index of the last FROM instruction (to inject after multi-stage builds)."""
    last = -1
    for i, line in enumerate(lines):
        if re.match(r"^\s*FROM\s+", line, re.IGNORECASE):
            last = i
    return last


def inject_dockerfile(dockerfile_path: str, *, output_path: str | None = None) -> str:
    """Inject arga-entry into a Dockerfile and write the script next to it.

    Returns the path where the modified Dockerfile was written.
    """
    src = Path(dockerfile_path)
    if not src.exists():
        raise FileNotFoundError(f"Dockerfile not found: {dockerfile_path}")

    content = src.read_text()

    if INJECT_MARKER in content:
        raise ValueError(f"Dockerfile already contains arga-entry injection ({INJECT_MARKER})")

    # Write the arga-entry script next to the Dockerfile
    script_dest = src.parent / "arga-entry"
    script_content = _load_entry_script()
    script_dest.write_text(script_content)
    script_dest.chmod(0o755)

    # Append the injection snippet
    if not content.endswith("\n"):
        content += "\n"
    content += DOCKERFILE_SNIPPET

    dest = Path(output_path) if output_path else src
    dest.write_text(content)
    return str(dest)


def run_entry_inject(args: argparse.Namespace) -> int:
    try:
        dest = inject_dockerfile(
            args.dockerfile,
            output_path=getattr(args, "output", None),
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Injected arga-entry into {dest}")
    print(f"Wrote arga-entry script to {Path(args.dockerfile).parent / 'arga-entry'}")
    print()
    print(RUNTIME_INSTRUCTIONS)
    return 0


def run_entry_show(args: argparse.Namespace) -> int:
    del args
    try:
        script = _load_entry_script()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(script)
    return 0


def run_entry_eject(args: argparse.Namespace) -> int:
    src = Path(args.dockerfile)
    if not src.exists():
        print(f"Error: Dockerfile not found: {args.dockerfile}", file=sys.stderr)
        return 1

    content = src.read_text()
    if INJECT_MARKER not in content:
        print("No arga-entry injection found in Dockerfile.", file=sys.stderr)
        return 1

    # Remove everything from the marker to the end (or to the next non-arga section)
    lines = content.splitlines(keepends=True)
    output_lines: list[str] = []
    skip = False
    for line in lines:
        if INJECT_MARKER in line:
            skip = True
            continue
        if skip:
            # Skip lines that are part of the injection block
            stripped = line.strip()
            if stripped.startswith(
                (
                    "COPY arga-entry",
                    "RUN chmod +x /arga/arga-entry",
                    "ENV NODE_OPTIONS=",
                    'ENTRYPOINT ["/arga/arga-entry"',
                )
            ):
                continue
            skip = False
        if not skip:
            output_lines.append(line)

    # Remove trailing blank lines
    result = "".join(output_lines).rstrip("\n") + "\n"
    src.write_text(result)

    # Remove the arga-entry script if it exists next to the Dockerfile
    script_path = src.parent / "arga-entry"
    if script_path.exists():
        script_path.unlink()
        print(f"Removed {script_path}")

    print(f"Removed arga-entry injection from {args.dockerfile}")
    return 0


def build_entry_parser(subparsers: argparse._SubParsersAction) -> None:
    entry_parser = subparsers.add_parser("entry", help="Inject arga-entry into Dockerfiles for twin routing")
    entry_subparsers = entry_parser.add_subparsers(dest="entry_command", required=True)

    inject_parser = entry_subparsers.add_parser(
        "inject",
        help="Modify a Dockerfile to route traffic through twins",
    )
    inject_parser.add_argument("dockerfile", help="Path to Dockerfile")
    inject_parser.add_argument("--output", default=None, help="Write modified Dockerfile to a different path")
    inject_parser.set_defaults(func=run_entry_inject)

    eject_parser = entry_subparsers.add_parser(
        "eject",
        help="Remove arga-entry injection from a Dockerfile",
    )
    eject_parser.add_argument("dockerfile", help="Path to Dockerfile")
    eject_parser.set_defaults(func=run_entry_eject)

    show_parser = entry_subparsers.add_parser(
        "show",
        help="Print the arga-entry script to stdout",
    )
    show_parser.set_defaults(func=run_entry_show)
