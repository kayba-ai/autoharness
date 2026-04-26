"""Doctor command registration."""

from __future__ import annotations

from pathlib import Path

from .cli_arguments import (
    _add_config_composition_arguments,
    _add_json_output_arguments,
    _add_required_adapter_argument,
)
from .doctor_handlers import _handle_doctor


def register_doctor_parsers(subparsers) -> None:
    doctor = subparsers.add_parser(
        "doctor",
        help="Validate project config, generator readiness, and benchmark stability.",
    )
    doctor.add_argument(
        "--target-root",
        type=Path,
        default=None,
        help="Optional target repo root to validate. Defaults to `target_root` from autoharness.yaml.",
    )
    _add_required_adapter_argument(
        doctor,
        help_text="Optional implemented adapter id to validate.",
        required=False,
    )
    _add_config_composition_arguments(
        doctor,
        preset_help=(
            "Optional starter-config preset to compose before any config file or inline overrides."
        ),
    )
    doctor.add_argument(
        "--stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default="screening",
        help="Evaluation stage policy to validate. Default: screening.",
    )
    doctor.add_argument(
        "--generator",
        default=None,
        help="Optional proposal generator id to validate. Defaults to `generator.id` from autoharness.yaml.",
    )
    doctor.add_argument(
        "--generator-option",
        action="append",
        default=[],
        help="Repeatable generator option in key=value form.",
    )
    doctor.add_argument(
        "--repeat",
        type=int,
        default=3,
        help="How many times to run the benchmark probe. Default: 3.",
    )
    doctor.add_argument(
        "--skip-benchmark-runs",
        action="store_true",
        help="Validate config and generator readiness without executing the benchmark command.",
    )
    _add_json_output_arguments(
        doctor,
        json_help="Render the doctor report as JSON.",
        output_help="Optional path to write the doctor report JSON.",
    )
    doctor.set_defaults(handler=_handle_doctor)
