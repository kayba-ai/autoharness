from __future__ import annotations

import json
from pathlib import Path

import yaml

from autoharness.cli import main


def test_guide_writes_project_config_and_benchmark_template(
    tmp_path: Path, capsys
) -> None:
    target_root = tmp_path / "sample_repo"
    (target_root / "src").mkdir(parents=True)
    (target_root / "tests").mkdir()

    config_path = tmp_path / "autoharness.yaml"
    benchmarks_dir = tmp_path / "benchmarks"
    summary_path = tmp_path / "autoharness.project.md"

    assert (
        main(
            [
                "guide",
                "--target-root",
                str(target_root),
                "--output-config",
                str(config_path),
                "--benchmark-config-dir",
                str(benchmarks_dir),
                "--summary-path",
                str(summary_path),
            ]
        )
        == 0
    )

    config_payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    benchmark_payload = yaml.safe_load(
        (benchmarks_dir / "screening.yaml").read_text(encoding="utf-8")
    )
    summary_text = summary_path.read_text(encoding="utf-8")

    assert config_payload["format_version"] == "autoharness.project.v1"
    assert config_payload["workspace"]["id"] == "sample_repo"
    assert config_payload["autonomy"]["editable_surfaces"] == ["src"]
    assert config_payload["benchmark"]["adapter"] == "generic_command"
    assert config_payload["generator"]["id"] == "openai_responses"
    assert config_payload["campaign"]["generator"] == "openai_responses"
    assert config_payload["target_root"] == "sample_repo"
    assert benchmark_payload["command"] == ["pytest", "-q"]
    assert benchmark_payload["benchmark_name"] == "sample_repo-screening"
    assert "Autoharness Project Summary" in summary_text
    assert "Detected a Python test layout." in capsys.readouterr().out


def test_project_config_defaults_cover_common_path_commands(
    tmp_path: Path, capsys
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    target_root = project_root / "target"
    target_root.mkdir()
    benchmark_dir = project_root / "benchmarks"
    benchmark_dir.mkdir()
    benchmark_config_path = benchmark_dir / "screening.yaml"
    benchmark_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "project-screening",
                "workdir": str(project_root),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    project_config_path = project_root / "autoharness.yaml"
    project_config_path.write_text(
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
                "campaign": {
                    "stage": "screening",
                    "max_iterations": 1,
                },
                "autonomy": {
                    "mode": "bounded",
                    "settings_path": ".autoharness/settings.yaml",
                    "editable_surfaces": [],
                    "protected_surfaces": [],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = project_root / "candidate.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "candidate.txt",
                        "content": "candidate\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "--project-config",
                str(project_config_path),
                "run-benchmark",
                "--output",
                str(project_root / "benchmark_result.json"),
            ]
        )
        == 0
    )
    capsys.readouterr()
    benchmark_payload = json.loads(
        (project_root / "benchmark_result.json").read_text(encoding="utf-8")
    )
    assert benchmark_payload["benchmark_name"] == "project-screening"
    assert (project_root / ".autoharness" / "settings.yaml").exists()
    assert (
        project_root
        / ".autoharness"
        / "workspaces"
        / "demo"
        / "workspace.json"
    ).exists()

    capsys.readouterr()
    assert (
        main(
            [
                "--project-config",
                str(project_config_path),
                "optimize",
                "--edit-plan",
                str(edit_plan_path),
                "--max-proposals",
                "1",
                "--json",
            ]
        )
        == 0
    )
    campaign_payload = json.loads(capsys.readouterr().out)
    assert campaign_payload["campaign"]["workspace_id"] == "demo"
    assert campaign_payload["campaign"]["target_root"] == str(target_root.resolve())

    capsys.readouterr()
    assert (
        main(
            [
                "--project-config",
                str(project_config_path),
                "report",
                "--json",
            ]
        )
        == 0
    )
    report_payload = json.loads(capsys.readouterr().out)
    assert report_payload["workspace_id"] == "demo"


def test_guide_writes_assistant_brief_when_requested(
    tmp_path: Path, capsys
) -> None:
    target_root = tmp_path / "sample_repo"
    (target_root / "src").mkdir(parents=True)
    (target_root / "tests").mkdir()

    config_path = tmp_path / "autoharness.yaml"
    benchmarks_dir = tmp_path / "benchmarks"
    summary_path = tmp_path / "autoharness.project.md"

    assert (
        main(
            [
                "guide",
                "--target-root",
                str(target_root),
                "--assistant",
                "codex",
                "--output-config",
                str(config_path),
                "--benchmark-config-dir",
                str(benchmarks_dir),
                "--summary-path",
                str(summary_path),
            ]
        )
        == 0
    )

    brief_path = tmp_path / "autoharness.codex.md"
    brief_text = brief_path.read_text(encoding="utf-8")
    config_payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert "Autoharness Assistant Brief" in brief_text
    assert "Codex" in brief_text
    assert "docs/ONBOARDING.md" in brief_text
    assert "autoharness optimize" in brief_text
    assert config_payload["generator"]["id"] == "codex_cli"
    assert config_payload["generator"]["options"] == {"sandbox": "read-only"}
    assert config_payload["campaign"]["generator"] == "codex_cli"
    assert f"Wrote assistant brief: {brief_path}" in capsys.readouterr().out
