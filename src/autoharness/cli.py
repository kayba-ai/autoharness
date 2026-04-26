"""CLI entrypoint for the standalone autoharness scaffold."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .cli_parser import build_parser
from .project_config import apply_project_defaults, maybe_bootstrap_project_state
from .execution_handlers import (
    _load_iteration_plan,
    _planned_iteration_argv,
    _planned_iteration_cwd,
)
def _handle_run_planned_iteration(args: argparse.Namespace) -> int:
    plan = _load_iteration_plan(args.plan)
    planned_argv = _planned_iteration_argv(plan)
    if getattr(args, "project_config", None) is not None:
        planned_argv = [
            "--project-config",
            str(Path(args.project_config)),
            *planned_argv,
        ]
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
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    parser = build_parser(
        run_planned_iteration_handler=_handle_run_planned_iteration,
    )
    args = parser.parse_args(raw_argv)
    args = apply_project_defaults(
        args=args,
        raw_argv=raw_argv,
        cwd=Path.cwd(),
    )
    args = maybe_bootstrap_project_state(args=args)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
