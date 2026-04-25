"""CLI parser construction for the standalone autoharness scaffold."""

from __future__ import annotations

import argparse

from .cli_registration import register_command_parsers


class _TopLevelHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Preserve curated top-level help text for the common path."""


_TOP_LEVEL_DESCRIPTION = (
    "Optimize an existing harness repo by proposing changes, running evals, "
    "and keeping stable winners."
)

_TOP_LEVEL_EPILOG = """Common path:
  autoharness setup --autonomy bounded --editable-surface src --editable-surface prompts
  autoharness init --workspace-id demo --objective "Improve pass rate" --benchmark generic-smoke
  autoharness run-benchmark --adapter generic_command --config benchmark.yaml --stage screening
  autoharness generate-proposal --generator openai_responses --intervention-class source
  autoharness optimize --generator openai_responses --intervention-class source
  autoharness report

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
