"""Guide command registration."""

from __future__ import annotations

from pathlib import Path

from .guide_handlers import _handle_guide


def register_guide_parsers(subparsers) -> None:
    guide = subparsers.add_parser(
        "guide",
        help="Inspect a repo and write starter autoharness project and benchmark config files.",
    )
    guide.add_argument(
        "--target-root",
        type=Path,
        default=Path("."),
        help="Repo root to inspect. Default: current directory.",
    )
    guide.add_argument(
        "--workspace-id",
        default=None,
        help="Optional workspace id override for the generated config.",
    )
    guide.add_argument(
        "--objective",
        default=None,
        help="Optional objective override for the generated config.",
    )
    guide.add_argument(
        "--benchmark-name",
        default=None,
        help="Optional benchmark name override for the generated benchmark config.",
    )
    guide.add_argument(
        "--assistant",
        choices=("generic", "codex", "claude"),
        default=None,
        help="Optional assistant-specific onboarding brief to generate.",
    )
    guide.add_argument(
        "--assistant-brief-path",
        type=Path,
        default=None,
        help="Optional path for the generated assistant onboarding brief.",
    )
    guide.add_argument(
        "--output-config",
        type=Path,
        default=Path("autoharness.yaml"),
        help="Where to write the autoharness project config. Default: autoharness.yaml.",
    )
    guide.add_argument(
        "--benchmark-config-dir",
        type=Path,
        default=Path("benchmarks"),
        help="Directory for generated benchmark config files. Default: benchmarks.",
    )
    guide.add_argument(
        "--summary-path",
        type=Path,
        default=Path("autoharness.project.md"),
        help="Where to write the generated project summary. Default: autoharness.project.md.",
    )
    guide.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the generated config without writing files.",
    )
    guide.add_argument(
        "--force",
        action="store_true",
        help="Overwrite generated files if they already exist.",
    )
    guide.add_argument(
        "--json",
        action="store_true",
        help="Print the generated guide payload as JSON.",
    )
    guide.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the guide payload JSON.",
    )
    guide.set_defaults(handler=_handle_guide)
