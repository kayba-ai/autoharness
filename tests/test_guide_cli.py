from __future__ import annotations

import json
from pathlib import Path

import yaml
import builtins

from autoharness.cli import main


def test_guide_writes_project_config_and_benchmark_template(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOHARNESS_OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "autoharness.guide_discovery.shutil.which",
        lambda _command: None,
    )
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
    assert config_payload["generator"]["id"] == "failure_summary"
    assert config_payload["campaign"]["generator"] == "failure_summary"
    assert config_payload["target_root"] == "sample_repo"
    assert benchmark_payload["command"] == ["pytest", "-q"]
    assert benchmark_payload["benchmark_name"] == "sample_repo-screening"
    assert "Autoharness Project Summary" in summary_text
    rendered_output = capsys.readouterr().out
    assert "Detected a Python test layout." in rendered_output
    assert "Doctor status: ready" in rendered_output


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
    packet_path = tmp_path / "autoharness.onboarding.json"
    brief_text = brief_path.read_text(encoding="utf-8")
    packet_payload = json.loads(packet_path.read_text(encoding="utf-8"))
    config_payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert "Autoharness Assistant Brief" in brief_text
    assert "Codex" in brief_text
    assert "docs/ONBOARDING.md" in brief_text
    assert "autoharness.onboarding.json" in brief_text
    assert "autoharness optimize" in brief_text
    assert config_payload["generator"]["id"] == "codex_cli"
    assert config_payload["generator"]["options"] == {"sandbox": "read-only"}
    assert config_payload["campaign"]["generator"] == "codex_cli"
    assert packet_payload["format_version"] == "autoharness.onboarding_packet.v1"
    assert packet_payload["assistant"] == "codex"
    assert packet_payload["generated_files"]["assistant_brief"] == str(brief_path)
    assert isinstance(packet_payload["open_questions"], list)
    rendered_output = capsys.readouterr().out
    assert f"Wrote assistant brief: {brief_path}" in rendered_output
    assert f"Wrote onboarding packet: {packet_path}" in rendered_output


def test_guide_interactive_tty_refines_key_defaults(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOHARNESS_OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "autoharness.guide_discovery.shutil.which",
        lambda _command: None,
    )
    target_root = tmp_path / "sample_repo"
    (target_root / "src").mkdir(parents=True)
    (target_root / "tests").mkdir()
    config_path = tmp_path / "autoharness.yaml"
    benchmarks_dir = tmp_path / "benchmarks"
    summary_path = tmp_path / "autoharness.project.md"

    answers = iter(
        [
            "demo-guided",
            "Improve screening stability",
            "python -c \"print('ok')\"",
            "src, prompts",
            "proposal",
            "failure_summary",
            "n",
        ]
    )
    monkeypatch.setattr(
        "autoharness.guide_handlers.stdio_supports_interaction",
        lambda: True,
    )
    monkeypatch.setattr(
        builtins,
        "input",
        lambda _prompt="": next(answers),
    )

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
    rendered_output = capsys.readouterr().out

    assert config_payload["workspace"]["id"] == "demo-guided"
    assert config_payload["workspace"]["objective"] == "Improve screening stability"
    assert config_payload["autonomy"]["mode"] == "proposal"
    assert config_payload["autonomy"]["editable_surfaces"] == ["src", "prompts"]
    assert config_payload["generator"]["id"] == "failure_summary"
    assert benchmark_payload["command"] == ["python", "-c", "print('ok')"]
    assert "Guide detected a starter setup" in rendered_output
    assert "Doctor status: ready" in rendered_output


def test_guide_assistant_packet_surfaces_high_priority_open_questions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOHARNESS_OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "autoharness.guide_discovery.shutil.which",
        lambda _command: None,
    )
    target_root = tmp_path / "sample_repo"
    target_root.mkdir()
    config_path = tmp_path / "autoharness.yaml"
    benchmarks_dir = tmp_path / "benchmarks"
    summary_path = tmp_path / "autoharness.project.md"

    packet_path = tmp_path / "autoharness.onboarding.json"
    assert (
        main(
            [
                "guide",
                "--assistant",
                "claude",
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

    packet_payload = json.loads(packet_path.read_text(encoding="utf-8"))
    question_ids = {entry["id"] for entry in packet_payload["open_questions"]}
    assert "benchmark_command" in question_ids
    assert packet_payload["recommended_next_action"].startswith("Resolve the highest-priority open question")


def test_guide_prefers_local_codex_cli_when_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOHARNESS_OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "autoharness.guide_discovery.shutil.which",
        lambda command: "/usr/bin/codex" if command == "codex" else None,
    )
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
    assert config_payload["generator"]["id"] == "codex_cli"
    assert config_payload["generator"]["options"] == {"sandbox": "read-only"}


def test_guide_prefers_openai_when_no_local_assistant_is_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("AUTOHARNESS_OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "autoharness.guide_discovery.shutil.which",
        lambda _command: None,
    )
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
    assert config_payload["generator"]["id"] == "openai_responses"
    assert config_payload["generator"]["options"] == {"proposal_scope": "balanced"}
