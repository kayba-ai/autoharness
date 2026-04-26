"""Interactive prompt helpers for `autoharness guide`."""

from __future__ import annotations

import shlex
import sys


def stdio_supports_interaction() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def prompt_text(
    *,
    label: str,
    default: str,
) -> str:
    response = input(f"{label} [{default}]: ").strip()
    return response or default


def prompt_choice(
    *,
    label: str,
    default: str,
    choices: tuple[str, ...],
) -> str:
    choice_text = "/".join(choices)
    while True:
        response = input(f"{label} ({choice_text}) [{default}]: ").strip()
        selected = response or default
        if selected in choices:
            return selected
        print(f"Choose one of: {', '.join(choices)}")


def prompt_shell_command(
    *,
    label: str,
    default: list[str],
) -> list[str]:
    default_text = shlex.join(default)
    while True:
        response = input(f"{label} [{default_text}]: ").strip()
        rendered = response or default_text
        try:
            parsed = shlex.split(rendered)
        except ValueError as exc:
            print(f"Invalid shell command: {exc}")
            continue
        if parsed:
            return parsed
        print("Enter at least one command token.")


def prompt_csv_list(
    *,
    label: str,
    default: list[str],
) -> list[str]:
    default_text = ", ".join(default) if default else "(none)"
    response = input(f"{label} [{default_text}]: ").strip()
    if not response:
        return list(default)
    if response.lower() in {"none", "(none)"}:
        return []
    return [item.strip() for item in response.split(",") if item.strip()]


def prompt_yes_no(
    *,
    label: str,
    default: bool = False,
) -> bool:
    default_text = "Y/n" if default else "y/N"
    response = input(f"{label} [{default_text}]: ").strip().lower()
    if not response:
        return default
    return response in {"y", "yes"}
