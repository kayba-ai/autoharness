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
        "--benchmark-command",
        default=None,
        help="Optional shell command override for the generated benchmark config.",
    )
    guide.add_argument(
        "--editable-surface",
        action="append",
        default=None,
        help="Repeatable editable surface override for the generated autonomy config.",
    )
    guide.add_argument(
        "--protected-surface",
        action="append",
        default=None,
        help="Repeatable protected surface override for the generated autonomy config.",
    )
    guide.add_argument(
        "--generator",
        default=None,
        help="Optional proposal generator id override for the generated project config.",
    )
    guide.add_argument(
        "--autonomy",
        choices=("proposal", "bounded", "full"),
        default=None,
        help="Optional autonomy mode override for the generated project config.",
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
        "--assistant-packet-path",
        type=Path,
        default=None,
        help="Optional path for the generated assistant onboarding packet JSON.",
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
        "--non-interactive",
        action="store_true",
        help="Skip TTY questions and use detected defaults plus explicit overrides.",
    )
    guide.add_argument(
        "--yes",
        action="store_true",
        help="Accept detected defaults without prompting.",
    )
    guide.add_argument(
        "--skip-doctor",
        action="store_true",
        help="Write the guide outputs without running the embedded doctor check.",
    )
    guide.add_argument(
        "--run-benchmark-probe",
        action="store_true",
        help="After writing files, run repeated benchmark probe checks instead of only structural validation.",
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
