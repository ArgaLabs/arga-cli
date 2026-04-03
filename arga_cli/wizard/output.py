"""Rich console helpers for wizard output."""

from __future__ import annotations

import re

from rich.console import Console

console = Console()


def header(text: str) -> None:
    console.print(f"\n[bold]{text}[/bold]\n")


def green(text: str) -> None:
    console.print(f"[green]{text}[/green]")


def yellow(text: str) -> None:
    console.print(f"[yellow]{text}[/yellow]")


def dim(text: str) -> None:
    console.print(f"[dim]{text}[/dim]")


def error(text: str) -> None:
    console.print(f"[red]{text}[/red]")


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def print_summary_box(lines: list[str]) -> None:
    """Print a bordered summary box."""
    max_len = max((_strip_ansi(line).__len__() for line in lines), default=40)
    width = max(max_len + 4, 44)
    top = "\u250c" + "\u2500" * width + "\u2510"
    bottom = "\u2514" + "\u2500" * width + "\u2518"

    console.print(f"\n[bold]{top}[/bold]")
    for line in lines:
        visible = len(_strip_ansi(line))
        padding = width - visible - 2
        console.print(f"[bold]\u2502[/bold]  {line}{' ' * max(padding, 0)}[bold]\u2502[/bold]")
    console.print(f"[bold]{bottom}[/bold]\n")
