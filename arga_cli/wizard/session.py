"""Load and save .arga-session.json files."""

from __future__ import annotations

import json
from pathlib import Path

from arga_cli.wizard.constants import SESSION_FILE


def load_session(cwd: str) -> dict:
    """Load session state from the current directory."""
    session_path = Path(cwd) / SESSION_FILE
    if not session_path.exists():
        raise FileNotFoundError("No active session. Run `arga wizard` first.")
    return json.loads(session_path.read_text())


def save_session(cwd: str, session: dict) -> None:
    """Save session state to the current directory."""
    session_path = Path(cwd) / SESSION_FILE
    session_path.write_text(json.dumps(session, indent=2) + "\n")


def delete_session(cwd: str) -> None:
    """Remove the session file."""
    session_path = Path(cwd) / SESSION_FILE
    session_path.unlink(missing_ok=True)
