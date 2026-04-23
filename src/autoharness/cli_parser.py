"""CLI parser construction for the standalone autoharness scaffold."""

from __future__ import annotations

import argparse

from .cli_registration import register_command_parsers


def build_parser(
    *,
    run_planned_iteration_handler,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autoharness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_command_parsers(
        subparsers,
        run_planned_iteration_handler=run_planned_iteration_handler,
    )
    return parser
