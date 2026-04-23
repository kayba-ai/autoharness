import json
from pathlib import Path

import yaml

from autoharness.outputs import (
    _emit_listing_json_output,
    _emit_text_listing_output,
    _export_listing_payload,
)


def test_emit_listing_json_output_writes_file_and_prints_json(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "listing.json"
    rendered = {
        "workspace_id": "demo",
        "iterations": [{"iteration_id": "iter_0001"}],
    }

    handled = _emit_listing_json_output(
        rendered=rendered,
        output=output,
        as_json=True,
    )

    assert handled is True
    assert json.loads(output.read_text(encoding="utf-8")) == rendered
    assert json.loads(capsys.readouterr().out) == rendered


def test_emit_text_listing_output_prints_summary_and_filters(capsys) -> None:
    _emit_text_listing_output(
        workspace_id="demo",
        collection_label="Iterations",
        collection_count=2,
        summary_label="Saved-plan runs",
        summary_count=1,
        sort_by="created_at",
        descending=True,
        resolved_track_id="main",
        named_filters=[
            ("Stage filter", "holdout"),
            ("Notes filter", None),
        ],
        enabled_filters=[
            ("Filter: saved plan only", True),
            ("Filter: unused", False),
        ],
        extra_lines=["Extra: yes"],
        item_lines=["- iter_0002", "- iter_0001"],
        output=Path("listing.txt"),
    )

    assert capsys.readouterr().out.splitlines() == [
        "Workspace: demo",
        "Iterations: 2",
        "Saved-plan runs: 1",
        "Sort: created_at desc",
        "Track filter: main",
        "Stage filter: holdout",
        "Filter: saved plan only",
        "Extra: yes",
        "- iter_0002",
        "- iter_0001",
        "Wrote output to listing.txt",
    ]


def test_export_listing_payload_writes_yaml_manifest(tmp_path: Path) -> None:
    output = tmp_path / "iterations.yaml"

    output_format = _export_listing_payload(
        output=output,
        explicit_format=None,
        format_version="autoharness.iteration_export.v1",
        rendered={"workspace_id": "demo", "iterations": []},
        exported_at="2026-01-01T00:00:00Z",
    )

    payload = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert output_format == "yaml"
    assert payload == {
        "format_version": "autoharness.iteration_export.v1",
        "exported_at": "2026-01-01T00:00:00Z",
        "workspace_id": "demo",
        "iterations": [],
    }
