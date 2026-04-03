"""Detect, parse, and rewrite .env files for twin configuration."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import questionary

from arga_cli.wizard.constants import (
    ENV_BACKUP_SUFFIX,
    ENV_FILE_NAMES,
    TOKEN_SHAPES,
    TWIN_ENV_MAPPINGS,
)
from arga_cli.wizard.output import console, dim, green, header

# ---------------------------------------------------------------------------
# .env detection
# ---------------------------------------------------------------------------


@dataclass
class DetectedEnvFile:
    path: str
    name: str


def detect_env_files(cwd: str) -> list[DetectedEnvFile]:
    """Scan a directory for common .env files."""
    found = []
    for name in ENV_FILE_NAMES:
        full_path = str(Path(cwd) / name)
        if Path(full_path).exists():
            found.append(DetectedEnvFile(path=full_path, name=name))
    return found


# ---------------------------------------------------------------------------
# .env parsing
# ---------------------------------------------------------------------------


@dataclass
class EnvEntry:
    raw: str
    key: str | None = None
    value: str | None = None


@dataclass
class EnvChange:
    key: str
    old_value: str
    new_value: str
    twin: str


def parse_env_file(file_path: str) -> list[EnvEntry]:
    """Parse a .env file into structured entries, preserving comments and blanks."""
    content = Path(file_path).read_text()
    entries = []
    for line in content.split("\n"):
        trimmed = line.strip()
        if trimmed == "" or trimmed.startswith("#"):
            entries.append(EnvEntry(raw=line))
            continue
        eq_idx = trimmed.find("=")
        if eq_idx == -1:
            entries.append(EnvEntry(raw=line))
            continue
        key = trimmed[:eq_idx].strip()
        value = trimmed[eq_idx + 1 :].strip()
        # Strip surrounding quotes
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        entries.append(EnvEntry(raw=line, key=key, value=value))
    return entries


def count_vars(entries: list[EnvEntry]) -> int:
    return sum(1 for e in entries if e.key is not None)


def apply_env_changes(file_path: str, entries: list[EnvEntry], changes: list[EnvChange]) -> None:
    """Write changes back to an env file. Creates a backup first."""
    shutil.copy2(file_path, file_path + ENV_BACKUP_SUFFIX)
    change_map = {c.key: c for c in changes}
    output_lines = []
    for entry in entries:
        if entry.key and entry.key in change_map:
            change = change_map[entry.key]
            output_lines.append(f"{entry.key}={change.new_value} # [arga-twin: {change.twin}]")
        else:
            output_lines.append(entry.raw)
    Path(file_path).write_text("\n".join(output_lines))


# ---------------------------------------------------------------------------
# Name-based env var resolution
# ---------------------------------------------------------------------------


def resolve_env_var(key: str, selected_twins: list[str]) -> dict | None:
    """For a given env var key, find which twin it belongs to and what the default is."""
    for twin_name in selected_twins:
        mapping = TWIN_ENV_MAPPINGS.get(twin_name)
        if not mapping:
            continue
        all_vars = mapping["token_vars"] + mapping["url_vars"] + mapping.get("secret_vars", [])
        if key in all_vars:
            default_value = mapping["defaults"].get(key, "")
            return {"twin": twin_name, "default_value": default_value}
    return None


# ---------------------------------------------------------------------------
# Shape-based detection
# ---------------------------------------------------------------------------


@dataclass
class ShapeMatch:
    key: str
    value: str
    shape: dict = field(default_factory=dict)


def match_value_shape(value: str, selected_twins: list[str]) -> dict | None:
    """Check whether a value matches any known token shape for the selected twins."""
    if not value or len(value) < 4:
        return None
    selected_set = set(selected_twins)
    for shape in TOKEN_SHAPES:
        if shape["twin"] not in selected_set:
            continue
        if re.search(shape["pattern"], value):
            return shape
    return None


def detect_shape_matches(
    entries: list[EnvEntry],
    selected_twins: list[str],
    already_matched_keys: set[str],
) -> list[ShapeMatch]:
    """Scan env entries not matched by name and check for token shape matches."""
    matches = []
    for entry in entries:
        if not entry.key or entry.value is None:
            continue
        if entry.key in already_matched_keys:
            continue
        shape = match_value_shape(entry.value, selected_twins)
        if shape:
            matches.append(ShapeMatch(key=entry.key, value=entry.value, shape=shape))
    return matches


# ---------------------------------------------------------------------------
# Main rewrite flow
# ---------------------------------------------------------------------------


def rewrite_env_files(
    cwd: str,
    selected_twins: list[str],
    *,
    shape_detect: bool = True,
) -> list[EnvChange]:
    """Detect env files, preview changes, and apply if confirmed."""
    env_files = detect_env_files(cwd)

    if not env_files:
        console.print("\n[yellow]  No .env files found in current directory.[/yellow]")
        dim("  You can configure environment variables manually using the twin URLs above.\n")
        return []

    header("Scanning for environment files...")
    for f in env_files:
        entries = parse_env_file(f.path)
        console.print(f"  Found: [cyan]{f.name}[/cyan] ({count_vars(entries)} variables)")

    # Let user pick which file(s) to update
    choices = [questionary.Choice(title=f.name, value=f.path) for f in env_files]
    if len(env_files) > 1:
        choices.append(questionary.Choice(title="All files", value="__all__"))
    choices.append(questionary.Choice(title="Skip (configure manually)", value="__skip__"))

    selected = questionary.select("Which file should I update?", choices=choices).ask()

    if not selected or selected == "__skip__":
        return []

    files_to_update = [f.path for f in env_files] if selected == "__all__" else [selected]

    all_changes: list[EnvChange] = []

    for file_path in files_to_update:
        entries = parse_env_file(file_path)

        # Name-based matching
        name_changes: list[EnvChange] = []
        for entry in entries:
            if not entry.key or entry.value is None:
                continue
            resolved = resolve_env_var(entry.key, selected_twins)
            if resolved and resolved["default_value"] and entry.value != resolved["default_value"]:
                name_changes.append(
                    EnvChange(
                        key=entry.key,
                        old_value=entry.value,
                        new_value=resolved["default_value"],
                        twin=resolved["twin"],
                    )
                )

        # Shape-based fallback detection
        name_matched_keys = {c.key for c in name_changes}
        shape_matches: list[ShapeMatch] = []
        shape_changes: list[EnvChange] = []
        shape_warnings: list[ShapeMatch] = []

        if shape_detect:
            shape_matches = detect_shape_matches(entries, selected_twins, name_matched_keys)
            for m in shape_matches:
                if m.shape.get("default_value") and m.value != m.shape["default_value"]:
                    shape_changes.append(
                        EnvChange(
                            key=m.key,
                            old_value=m.value,
                            new_value=m.shape["default_value"],
                            twin=m.shape["twin"],
                        )
                    )
                elif not m.shape.get("default_value"):
                    shape_warnings.append(m)

        if not name_changes and not shape_changes and not shape_warnings:
            dim(f"\n  No matching env vars found in {file_path}")
            continue

        console.print(f"\n[bold]Detected changes for {file_path}:[/bold]")

        if name_changes:
            dim("  Matched by variable name:")
            for c in name_changes:
                old_display = c.old_value[:27] + "..." if len(c.old_value) > 30 else c.old_value
                console.print(
                    f"  [cyan]{c.key}[/cyan]=[red]{old_display}[/red] [dim]\u2192[/dim] [green]{c.new_value}[/green]"
                )

        if shape_changes:
            if name_changes:
                console.print()
            console.print("[yellow]  Detected by value pattern (heuristic):[/yellow]")
            for sc in shape_changes:
                match = next((m for m in shape_matches if m.key == sc.key), None)
                old_display = sc.old_value[:27] + "..." if len(sc.old_value) > 30 else sc.old_value
                console.print(
                    f"  [cyan]{sc.key}[/cyan]=[red]{old_display}[/red] [dim]\u2192[/dim] [green]{sc.new_value}[/green]"
                )
                if match:
                    dim(f"    Reason: {match.shape['label']}")

        if shape_warnings:
            console.print()
            console.print("[yellow]  Detected but no twin default available (configure manually):[/yellow]")
            for w in shape_warnings:
                old_display = w.value[:27] + "..." if len(w.value) > 30 else w.value
                console.print(f"  [cyan]{w.key}[/cyan]=[red]{old_display}[/red]  [dim]{w.shape['label']}[/dim]")

        combined_changes = name_changes + shape_changes
        if not combined_changes:
            continue

        message = (
            f"Apply these changes? ({len(name_changes)} by name, {len(shape_changes)} by value pattern)"
            if shape_changes
            else "Apply these changes?"
        )
        ok = questionary.confirm(message, default=True).ask()

        if ok:
            apply_env_changes(file_path, entries, combined_changes)
            green(f"  Updated {file_path}")
            dim(f"  Backup saved: {file_path}{ENV_BACKUP_SUFFIX}")
            all_changes.extend(combined_changes)

    return all_changes
