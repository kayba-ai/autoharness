from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

from autoharness.cli import main


def _write_project_config(
    project_root: Path,
    *,
    generator_id: str,
    generator_options: dict[str, object] | None = None,
) -> Path:
    config_path = project_root / "autoharness.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "format_version": "autoharness.project.v1",
                "target_root": "target",
                "workspace": {
                    "id": "demo",
                    "root": ".autoharness/workspaces",
                    "track_id": "main",
                    "objective": "Improve harness benchmark performance without regressions",
                    "benchmark": "project-screening",
                    "domain": "general",
                },
                "benchmark": {
                    "adapter": "generic_command",
                    "config": "benchmarks/screening.yaml",
                    "stage": "screening",
                },
                "generator": {
                    "id": generator_id,
                    "intervention_class": "source",
                    "options": generator_options or {},
                },
                "campaign": {
                    "stage": "screening",
                    "generator": generator_id,
                    "intervention_classes": ["source"],
                    "max_iterations": 1,
                },
                "autonomy": {
                    "mode": "bounded",
                    "settings_path": ".autoharness/settings.yaml",
                    "editable_surfaces": ["src"],
                    "protected_surfaces": [],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config_path


def test_doctor_reports_ready_for_config_first_project(tmp_path: Path, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "target" / "src").mkdir(parents=True)
    benchmark_dir = project_root / "benchmarks"
    benchmark_dir.mkdir()
    (benchmark_dir / "screening.yaml").write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "project-screening",
                "workdir": str(project_root),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    project_config_path = _write_project_config(
        project_root,
        generator_id="failure_summary",
    )

    current_dir = Path.cwd()
    try:
        os.chdir(project_root)
        capsys.readouterr()
        assert main(["doctor", "--repeat", "2", "--json"]) == 0
    finally:
        os.chdir(current_dir)

    rendered = json.loads(capsys.readouterr().out)
    assert rendered["format_version"] == "autoharness.doctor.v1"
    assert rendered["status"] == "ready"
    assert rendered["project"]["project_config_path"] == str(project_config_path.resolve())
    assert rendered["generator"]["generator_id"] == "failure_summary"
    assert rendered["benchmark_validation"]["valid"] is True
    assert rendered["benchmark_probe"]["validation_summary"]["run_count"] == 2


def test_doctor_blocks_placeholder_benchmark_and_missing_openai_auth(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOHARNESS_OPENAI_API_KEY", raising=False)

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "target" / "src").mkdir(parents=True)
    benchmark_dir = project_root / "benchmarks"
    benchmark_dir.mkdir()
    (benchmark_dir / "screening.yaml").write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "project-screening",
                "workdir": str(project_root),
                "command": [
                    sys.executable,
                    "-c",
                    "print('replace with your benchmark command')",
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    _write_project_config(
        project_root,
        generator_id="openai_responses",
        generator_options={"proposal_scope": "balanced"},
    )

    current_dir = Path.cwd()
    try:
        os.chdir(project_root)
        capsys.readouterr()
        assert main(["doctor", "--skip-benchmark-runs", "--json"]) == 1
    finally:
        os.chdir(current_dir)

    rendered = json.loads(capsys.readouterr().out)
    assert rendered["status"] == "blocked"
    check_ids = {entry["check_id"] for entry in rendered["findings"]}
    assert "generator.openai_auth_missing" in check_ids
    assert "benchmark.placeholder_command" in check_ids
