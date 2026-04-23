"""CLI entrypoint for the standalone autoharness scaffold."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .cli_parser import build_parser
from .execution_handlers import (
    _load_iteration_plan,
    _planned_iteration_argv,
    _planned_iteration_cwd,
)
def _handle_run_planned_iteration(args: argparse.Namespace) -> int:
    plan = _load_iteration_plan(args.plan)
    planned_argv = _planned_iteration_argv(plan)
    planned_argv.extend(["--source-plan-path", str(args.plan.resolve())])
    planning_cwd = _planned_iteration_cwd(plan, plan_path=args.plan)
    if planning_cwd is None:
        return main(planned_argv)

    original_cwd = Path.cwd()
    try:
        os.chdir(planning_cwd)
        return main(planned_argv)
    finally:
        os.chdir(original_cwd)
def main(argv: list[str] | None = None) -> int:
    parser = build_parser(
        run_planned_iteration_handler=_handle_run_planned_iteration,
    )
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
