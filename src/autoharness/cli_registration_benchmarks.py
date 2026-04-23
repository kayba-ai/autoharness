"""Benchmark command registration."""

from __future__ import annotations

from .benchmark_handlers import (
    _handle_init_benchmark_config,
    _handle_list_benchmarks,
    _handle_show_benchmark_config,
    _handle_show_benchmark,
    _handle_validate_benchmark_config,
)
from .cli_arguments import (
    _add_benchmark_preset_argument,
    _add_config_composition_arguments,
    _add_force_argument,
    _add_json_output_arguments,
    _add_optional_format_argument,
    _add_optional_output_argument,
    _add_required_adapter_argument,
)


def register_benchmark_parsers(subparsers) -> None:
    list_benchmarks = subparsers.add_parser(
        "list-benchmarks",
        help="Show the built-in benchmark adapter catalog.",
    )
    list_benchmarks.add_argument(
        "--implemented-only",
        action="store_true",
        help="Only include adapters that have concrete implementations.",
    )
    _add_json_output_arguments(
        list_benchmarks,
        json_help="Render the catalog as JSON.",
        output_help="Optional path to write the rendered catalog JSON.",
    )
    list_benchmarks.set_defaults(handler=_handle_list_benchmarks)

    show_benchmark = subparsers.add_parser(
        "show-benchmark",
        help="Show one benchmark adapter spec plus implemented capabilities.",
    )
    _add_required_adapter_argument(
        show_benchmark,
        help_text="Benchmark adapter id from the built-in catalog.",
    )
    _add_benchmark_preset_argument(
        show_benchmark,
        help_text="Starter-config preset to render. Default: default.",
    )
    _add_json_output_arguments(
        show_benchmark,
        json_help="Render the benchmark entry as JSON.",
        output_help="Optional path to write the rendered benchmark JSON.",
    )
    show_benchmark.set_defaults(handler=_handle_show_benchmark)

    show_benchmark_config = subparsers.add_parser(
        "show-benchmark-config",
        help="Compose and inspect one benchmark adapter config without running it.",
    )
    _add_required_adapter_argument(
        show_benchmark_config,
        help_text="Implemented adapter id to inspect.",
    )
    _add_config_composition_arguments(
        show_benchmark_config,
        preset_help="Optional starter-config preset to compose before any config file or inline overrides.",
    )
    show_benchmark_config.add_argument(
        "--stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default=None,
        help="Optional stage override to apply before building the invocation.",
    )
    _add_json_output_arguments(
        show_benchmark_config,
        json_help="Render the composed config preview as JSON.",
        output_help="Optional path to write the composed config preview JSON.",
    )
    show_benchmark_config.set_defaults(handler=_handle_show_benchmark_config)

    validate_benchmark_config = subparsers.add_parser(
        "validate-benchmark-config",
        help="Compose and validate one benchmark adapter config without running it.",
    )
    _add_required_adapter_argument(
        validate_benchmark_config,
        help_text="Implemented adapter id to validate.",
    )
    _add_config_composition_arguments(
        validate_benchmark_config,
        preset_help="Optional starter-config preset to compose before any config file or inline overrides.",
    )
    validate_benchmark_config.add_argument(
        "--stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default=None,
        help="Optional stage override to apply before building the invocation.",
    )
    _add_json_output_arguments(
        validate_benchmark_config,
        json_help="Render the benchmark-config validation result as JSON.",
        output_help="Optional path to write the benchmark-config validation JSON.",
    )
    validate_benchmark_config.set_defaults(handler=_handle_validate_benchmark_config)

    init_benchmark_config = subparsers.add_parser(
        "init-benchmark-config",
        help="Write a starter config scaffold for one implemented benchmark adapter.",
    )
    _add_required_adapter_argument(
        init_benchmark_config,
        help_text="Implemented adapter id to scaffold.",
    )
    _add_benchmark_preset_argument(
        init_benchmark_config,
        help_text="Starter-config preset to write. Default: default.",
    )
    _add_optional_output_argument(
        init_benchmark_config,
        output_help=(
            "Where to write the scaffold. Defaults to <adapter>.yaml for the default "
            "preset, or <adapter>.<preset>.yaml for named presets."
        ),
    )
    _add_optional_format_argument(
        init_benchmark_config,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    _add_force_argument(
        init_benchmark_config,
        help_text="Overwrite an existing scaffold file.",
    )
    init_benchmark_config.set_defaults(handler=_handle_init_benchmark_config)
