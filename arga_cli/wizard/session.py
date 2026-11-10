"""Load and save .arga-session.json files."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from arga_cli.wizard.constants import SESSION_FILE


def load_session(cwd: str) -> dict:
    """Load metadata and resolve credentials in memory from normal CLI auth."""
    session_path = Path(cwd) / SESSION_FILE
    if not session_path.exists():
        raise FileNotFoundError("No active session. Run `arga wizard` first.")
    session = json.loads(session_path.read_text())
    if not isinstance(session, dict):
        raise ValueError("Invalid wizard session. Run `arga wizard` first.")
    if session.get("credential_source", "cli-config") != "cli-config":
        raise ValueError("Unsupported wizard credential reference. Run `arga login` first.")
    from arga_cli.main import NotAuthenticatedError, load_api_key

    try:
        api_key = load_api_key()
    except NotAuthenticatedError:
        # Legacy embedded credentials remain a fallback for existing sessions;
        # the normal auth store takes precedence to support credential rotation.
        if "credential_source" not in session and isinstance(session.get("api_key"), str) and session["api_key"]:
            return session
        raise
    return {**session, "api_key": api_key}


def save_session(cwd: str, session: dict) -> None:
    """Write credential references and metadata, never embedded credentials."""
    session_path = Path(cwd) / SESSION_FILE
    metadata = {
        key: session[key] for key in ("run_id", "created_at", "expires_at", "api_url", "scenario_id") if key in session
    }
    metadata["credential_source"] = "cli-config"
    twins = session.get("twins")
    metadata["twins"] = {
        name: {key: info[key] for key in ("base_url", "admin_url") if key in info}
        for name, info in (twins.items() if isinstance(twins, dict) else [])
        if isinstance(info, dict)
    }
    descriptor, temporary = tempfile.mkstemp(prefix=".arga-session-", dir=cwd)
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write(json.dumps(metadata, indent=2) + "\n")
        os.replace(temporary, session_path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def delete_session(cwd: str) -> None:
    """Remove the session file."""
    session_path = Path(cwd) / SESSION_FILE
    session_path.unlink(missing_ok=True)
