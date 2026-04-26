"""CLI parser construction for the standalone autoharness scaffold."""

from __future__ import annotations

import argparse

from pathlib import Path

from .cli_registration import register_command_parsers


class _TopLevelHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Preserve curated top-level help text for the common path."""


_TOP_LEVEL_DESCRIPTION = (
    "Optimize an existing harness repo by proposing changes, running evals, "
    "and keeping stable winners."
)

_TOP_LEVEL_EPILOG = """Common path:
  autoharness guide
  autoharness doctor
  autoharness run-benchmark
  autoharness optimize
  autoharness report

If `autoharness.yaml` is present, autoharness can auto-bootstrap missing setup
and workspace state on the common path.

Power-user surfaces remain available for background workers, root coordination,
retention, bundles, and inspection commands.
"""


def build_parser(
    *,
    run_planned_iteration_handler,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoharness",
        description=_TOP_LEVEL_DESCRIPTION,
        epilog=_TOP_LEVEL_EPILOG,
        formatter_class=_TopLevelHelpFormatter,
    )
    parser.add_argument(
        "--project-config",
        type=Path,
        default=None,
        help=(
            "Optional autoharness project config path. If omitted, autoharness "
            "auto-discovers `autoharness.yaml` from the current directory upward."
        ),
    )
    subparsers = parser.add_subparsers(
        dest="command",
        metavar="<command>",
        required=True,
        title="commands",
    )
    register_command_parsers(
        subparsers,
        run_planned_iteration_handler=run_planned_iteration_handler,
    )
    return parser
