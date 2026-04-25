import json
import sys
from pathlib import Path

import pytest
import yaml

from autoharness.cli import main


def test_run_iteration_records_one_hypothesis(tmp_path: Path) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; from pathlib import Path; "
                        "Path('metrics.json').write_text("
                        "json.dumps({'pass_rate': 1.0}), encoding='utf-8'"
                        "); print('ok')"
                    ),
                ],
                "metrics_parser": {
                    "format": "json_file",
                    "path": str(tmp_path / "metrics.json"),
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Check whether the smoke command runs cleanly",
            "--root",
            str(workspaces_root),
        ]
    )
    assert exit_code == 0

    state = json.loads(
        (workspaces_root / "demo" / "state.json").read_text(encoding="utf-8")
    )
    assert state["next_iteration_index"] == 2
    assert state["last_iteration_id"] == "iter_0001"

    registry_dir = workspaces_root / "demo" / "tracks" / "main" / "registry"
    records = sorted(registry_dir.glob("*.json"))
    assert len(records) == 1

    iteration_summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert iteration_summary["adapter_id"] == "generic_command"
    assert iteration_summary["status"] == "success"


def test_run_iteration_persists_preflight_failure_without_running_benchmark(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    benchmark_counter = tmp_path / "benchmark_counter.txt"
    preflight_counter = tmp_path / "preflight_counter.txt"
    preflight_script = tmp_path / "preflight_fail.py"
    preflight_script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                f"Path({preflight_counter.as_posix()!r}).write_text('1', encoding='utf-8')",
                "raise SystemExit(1)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "preflight-smoke",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"Path({str(benchmark_counter)!r}).write_text('1', encoding='utf-8')"
                    ),
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Fail preflight before benchmark execution",
            "--preflight-command",
            f"{sys.executable} {preflight_script}",
            "--root",
            str(workspaces_root),
        ]
    )
    assert exit_code == 0

    registry_records = sorted(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )
    assert len(registry_records) == 1
    record = json.loads(registry_records[0].read_text(encoding="utf-8"))
    payload = record["payload"]

    assert record["status"] == "failed"
    assert payload["preflight_failed"] is True
    assert payload["command"] == []
    assert payload["preflight_validation"]["all_passed"] is False
    assert payload["preflight_validation"]["command_count"] == 1
    assert not benchmark_counter.exists()
    assert preflight_counter.read_text(encoding="utf-8") == "1"


def test_run_iteration_supports_builtin_preflight_checks(tmp_path: Path) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()
    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    (target_root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    benchmark_counter = tmp_path / "benchmark_counter_builtin.txt"

    config_path = tmp_path / "generic_builtin_check.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "preflight-builtin-check",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"Path({str(benchmark_counter)!r}).write_text('1', encoding='utf-8')"
                    ),
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Fail builtin python compile preflight",
            "--target-root",
            str(target_root),
            "--preflight-check",
            "python_compile",
            "--root",
            str(workspaces_root),
        ]
    )
    assert exit_code == 0

    registry_records = sorted(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )
    assert len(registry_records) == 1
    record = json.loads(registry_records[0].read_text(encoding="utf-8"))
    payload = record["payload"]

    assert record["status"] == "failed"
    assert payload["preflight_failed"] is True
    assert payload["preflight_validation"]["all_passed"] is False
    assert payload["preflight_validation"]["command_count"] == 1
    assert "compileall" in payload["preflight_validation"]["commands"][0]["command"]
    assert not benchmark_counter.exists()


def test_run_iteration_reuses_preflight_cache_for_same_candidate(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()
    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    counter_path = tmp_path / "preflight_counter_cache.txt"
    preflight_script = tmp_path / "preflight_count.py"
    preflight_script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                f"path = Path({str(counter_path)!r})",
                "current = int(path.read_text(encoding='utf-8')) if path.exists() else 0",
                "path.write_text(str(current + 1), encoding='utf-8')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "generic_preflight_cache.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "preflight-cache",
                "workdir": str(target_root),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "cached_candidate.txt",
                        "content": "candidate\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Populate preflight cache",
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--preflight-command",
                f"{sys.executable} {preflight_script}",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Reuse preflight cache",
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--preflight-command",
                f"{sys.executable} {preflight_script}",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    registry_records = sorted(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )
    assert len(registry_records) == 2
    records_by_hypothesis = {
        record["hypothesis"]: record["payload"]
        for record in (
            json.loads(path.read_text(encoding="utf-8")) for path in registry_records
        )
    }
    first_payload = records_by_hypothesis["Populate preflight cache"]
    second_payload = records_by_hypothesis["Reuse preflight cache"]

    assert first_payload["preflight_validation"]["cache_hit"] is False
    assert second_payload["preflight_validation"]["cache_hit"] is True
    assert counter_path.read_text(encoding="utf-8") == "1"


def test_run_iteration_reports_cleanup_drift_and_environment_capture(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()
    (target_root / "baseline.txt").write_text("baseline\n", encoding="utf-8")
    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic_cleanup.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "cleanup-drift",
                "workdir": str(target_root),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        "Path('stray.txt').write_text('stray\\n', encoding='utf-8'); "
                        "raise SystemExit(1)"
                    ),
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "cleanup_edit_plan.yaml"
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

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Detect cleanup drift",
            "--target-root",
            str(target_root),
            "--edit-plan",
            str(edit_plan_path),
            "--root",
            str(workspaces_root),
        ]
    )
    assert exit_code == 0

    registry_records = sorted(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )
    record = json.loads(registry_records[0].read_text(encoding="utf-8"))
    payload = record["payload"]

    assert payload["cleanup_validation"]["passed"] is False
    assert payload["cleanup_validation"]["drift"]["added_paths"] == ["stray.txt"]
    assert payload["run_environment"]["python_executable"] == sys.executable
    assert payload["working_directory_manifest"]["execution_root"].endswith(
        "staging/target"
    )
    assert payload["staging"]["source_root"] == str(target_root.resolve())
    assert payload["execution_manifest"]["drift"]["added_paths"] == ["stray.txt"]
    assert not (target_root / "candidate.txt").exists()
    assert not (target_root / "stray.txt").exists()


def test_show_iteration_and_show_iterations_commands(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "First smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Second smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    show_iteration_output_path = tmp_path / "iteration.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-iteration",
                "--workspace-id",
                "demo",
                "--iteration-id",
                "iter_0001",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(show_iteration_output_path),
            ]
        )
        == 0
    )
    rendered_iteration = json.loads(capsys.readouterr().out)
    assert rendered_iteration["summary"]["iteration_id"] == "iter_0001"
    assert rendered_iteration["summary"]["record_id"].startswith("run_")
    assert rendered_iteration["linked_records"]["track_id"] == "main"
    assert rendered_iteration["artifacts"]["summary_path"].endswith("iter_0001/summary.json")
    assert rendered_iteration["artifacts"]["hypothesis_path"].endswith("iter_0001/hypothesis.md")
    assert json.loads(show_iteration_output_path.read_text(encoding="utf-8")) == rendered_iteration

    show_iterations_output_path = tmp_path / "iterations.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(show_iterations_output_path),
            ]
        )
        == 0
    )
    rendered_iterations = json.loads(capsys.readouterr().out)
    assert rendered_iterations["last_iteration_id"] == "iter_0002"
    assert [item["iteration_id"] for item in rendered_iterations["iterations"]] == [
        "iter_0001",
        "iter_0002",
    ]
    assert rendered_iterations["iterations"][0]["last_iteration"] is False
    assert rendered_iterations["iterations"][1]["last_iteration"] is True
    assert json.loads(show_iterations_output_path.read_text(encoding="utf-8")) == rendered_iterations


def test_show_iterations_marks_saved_plan_runs(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    plan_path = tmp_path / "planned_iteration.json"
    config_path = tmp_path / "generic.yaml"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Direct smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Planned smoke check",
                "--root",
                str(workspaces_root),
                "--output",
                str(plan_path),
            ]
        )
        == 0
    )
    assert main(["run-planned-iteration", "--plan", str(plan_path)]) == 0

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["saved_plan_only"] is False
    assert rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in rendered["iterations"]] == [
        "iter_0001",
        "iter_0002",
    ]
    assert rendered["iterations"][0]["saved_plan_run"] is False
    assert rendered["iterations"][0]["source_plan_path"] is None
    assert rendered["iterations"][0]["source_plan_artifact_path"] is None
    assert rendered["iterations"][1]["saved_plan_run"] is True
    assert rendered["iterations"][1]["source_plan_path"] == str(plan_path.resolve())
    assert rendered["iterations"][1]["source_plan_artifact_path"] == str(
        workspaces_root
        / "demo"
        / "iterations"
        / "iter_0002"
        / "source_plan.json"
    )

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert "Saved-plan runs: 1" in text_output
    assert "iter_0002: track=main, status=success, stage=screening" in text_output
    assert "saved_plan=yes" in text_output

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--saved-plan-only",
                "--json",
            ]
        )
        == 0
    )
    filtered_rendered = json.loads(capsys.readouterr().out)
    assert filtered_rendered["saved_plan_only"] is True
    assert filtered_rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in filtered_rendered["iterations"]] == [
        "iter_0002",
    ]
    assert filtered_rendered["iterations"][0]["saved_plan_run"] is True

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--saved-plan-only",
            ]
        )
        == 0
    )
    filtered_text_output = capsys.readouterr().out
    assert "Iterations: 1" in filtered_text_output
    assert "Saved-plan runs: 1" in filtered_text_output
    assert "Filter: saved-plan only" in filtered_text_output
    assert "iter_0001" not in filtered_text_output
    assert "iter_0002" in filtered_text_output


def test_export_iterations_command_writes_filtered_yaml(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    plan_path = tmp_path / "planned_iteration.json"
    config_path = tmp_path / "generic.yaml"
    export_path = tmp_path / "iterations.report"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Direct smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Planned smoke check",
                "--root",
                str(workspaces_root),
                "--output",
                str(plan_path),
            ]
        )
        == 0
    )
    assert main(["run-planned-iteration", "--plan", str(plan_path)]) == 0

    capsys.readouterr()
    assert (
        main(
            [
                "export-iterations",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--saved-plan-only",
                "--format",
                "yaml",
                "--output",
                str(export_path),
            ]
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert "Workspace: demo" in text_output
    assert "Iterations exported: 1" in text_output
    assert "Saved-plan runs: 1" in text_output
    assert "Format: yaml" in text_output
    assert f"Export path: {export_path}" in text_output

    rendered = yaml.safe_load(export_path.read_text(encoding="utf-8"))
    assert rendered["format_version"] == "autoharness.iteration_export.v1"
    assert rendered["workspace_id"] == "demo"
    assert rendered["saved_plan_only"] is True
    assert rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in rendered["iterations"]] == ["iter_0002"]
    assert rendered["iterations"][0]["saved_plan_run"] is True
    assert rendered["iterations"][0]["source_plan_path"] == str(plan_path.resolve())

    capsys.readouterr()
    assert main(["show-listing-file", str(export_path), "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["listing_type"] == "iteration_export"
    assert shown["workspace_id"] == "demo"
    assert shown["item_total"] == 1
    assert shown["summary_total"] == 1

    capsys.readouterr()
    assert main(["show-artifact-file", str(export_path), "--json"]) == 0
    generic_shown = json.loads(capsys.readouterr().out)
    assert generic_shown["listing_type"] == "iteration_export"
    assert generic_shown["item_total"] == 1

    capsys.readouterr()
    assert main(["validate-listing-file", str(export_path), "--json"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["listing_type"] == "iteration_export"
    assert validated["valid"] is True

    invalid_export_path = tmp_path / "invalid_iterations.json"
    invalid_export_path.write_text(
        json.dumps(
            {
                "format_version": "autoharness.iteration_export.v1",
                "exported_at": "2026-04-22T00:00:00Z",
                "workspace_id": "demo",
                "iterations": [],
            }
        ),
        encoding="utf-8",
    )
    capsys.readouterr()
    assert main(["validate-listing-file", str(invalid_export_path), "--json"]) == 1
    invalid_rendered = json.loads(capsys.readouterr().out)
    assert invalid_rendered["listing_type"] == "iteration_export"
    assert invalid_rendered["valid"] is False
    assert "Missing or invalid `saved_plan_iterations_total`." in invalid_rendered[
        "validation_errors"
    ]
    assert "Missing or invalid `iterations_dir`." in invalid_rendered[
        "validation_errors"
    ]


def test_show_iterations_filters_by_track(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    plan_path = tmp_path / "planned_alt_iteration.json"
    config_path = tmp_path / "generic.yaml"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )
    assert (
        main(
            [
                "create-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Main smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Alt smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Planned alt smoke check",
                "--root",
                str(workspaces_root),
                "--output",
                str(plan_path),
            ]
        )
        == 0
    )
    assert main(["run-planned-iteration", "--plan", str(plan_path)]) == 0

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["track_id"] == "alt"
    assert rendered["saved_plan_only"] is False
    assert rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in rendered["iterations"]] == [
        "iter_0002",
        "iter_0003",
    ]
    assert {item["track_id"] for item in rendered["iterations"]} == {"alt"}
    assert rendered["iterations"][0]["saved_plan_run"] is False
    assert rendered["iterations"][1]["saved_plan_run"] is True
    assert rendered["iterations"][1]["source_plan_path"] == str(plan_path.resolve())

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert "Track filter: alt" in text_output
    assert "Saved-plan runs: 1" in text_output
    assert "iter_0001" not in text_output
    assert "iter_0002" in text_output
    assert "iter_0003" in text_output

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--saved-plan-only",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    filtered_rendered = json.loads(capsys.readouterr().out)
    assert filtered_rendered["track_id"] == "alt"
    assert filtered_rendered["saved_plan_only"] is True
    assert filtered_rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in filtered_rendered["iterations"]] == [
        "iter_0003",
    ]


def test_show_records_filters_by_track_and_saved_plan(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    plan_path = tmp_path / "planned_alt_record.json"
    output_path = tmp_path / "records.json"
    config_path = tmp_path / "generic.yaml"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )
    assert (
        main(
            [
                "create-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Main smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Alt smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Planned alt smoke check",
                "--root",
                str(workspaces_root),
                "--output",
                str(plan_path),
            ]
        )
        == 0
    )
    assert main(["run-planned-iteration", "--plan", str(plan_path)]) == 0

    capsys.readouterr()
    assert (
        main(
            [
                "show-records",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["track_id"] == "alt"
    assert rendered["saved_plan_only"] is False
    assert rendered["saved_plan_records_total"] == 1
    assert len(rendered["records"]) == 2
    assert {item["track_id"] for item in rendered["records"]} == {"alt"}
    assert sum(1 for item in rendered["records"] if item["saved_plan_run"]) == 1
    assert json.loads(output_path.read_text(encoding="utf-8")) == rendered

    capsys.readouterr()
    assert (
        main(
            [
                "show-records",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--saved-plan-only",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    filtered_rendered = json.loads(capsys.readouterr().out)
    assert filtered_rendered["track_id"] == "alt"
    assert filtered_rendered["saved_plan_only"] is True
    assert filtered_rendered["saved_plan_records_total"] == 1
    assert len(filtered_rendered["records"]) == 1
    assert filtered_rendered["records"][0]["saved_plan_run"] is True
    assert filtered_rendered["records"][0]["source_plan_path"] == str(plan_path.resolve())

    capsys.readouterr()
    assert (
        main(
            [
                "show-records",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--saved-plan-only",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert "Track filter: alt" in text_output
    assert "Saved-plan runs: 1" in text_output
    assert "Filter: saved-plan only" in text_output
    assert "track=main" not in text_output
    assert "track=alt" in text_output
    assert "saved_plan=yes" in text_output


def test_export_records_command_writes_filtered_yaml(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    plan_path = tmp_path / "planned_alt_record.json"
    export_path = tmp_path / "records.report"
    config_path = tmp_path / "generic.yaml"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )
    assert (
        main(
            [
                "create-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Main smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Alt smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Planned alt smoke check",
                "--root",
                str(workspaces_root),
                "--output",
                str(plan_path),
            ]
        )
        == 0
    )
    assert main(["run-planned-iteration", "--plan", str(plan_path)]) == 0

    capsys.readouterr()
    assert (
        main(
            [
                "export-records",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--saved-plan-only",
                "--root",
                str(workspaces_root),
                "--format",
                "yaml",
                "--output",
                str(export_path),
            ]
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert "Workspace: demo" in text_output
    assert "Records exported: 1" in text_output
    assert "Saved-plan runs: 1" in text_output
    assert "Format: yaml" in text_output
    assert f"Export path: {export_path}" in text_output

    rendered = yaml.safe_load(export_path.read_text(encoding="utf-8"))
    assert rendered["format_version"] == "autoharness.record_export.v1"
    assert rendered["workspace_id"] == "demo"
    assert rendered["track_id"] == "alt"
    assert rendered["saved_plan_only"] is True
    assert rendered["saved_plan_records_total"] == 1
    assert len(rendered["records"]) == 1
    assert rendered["records"][0]["saved_plan_run"] is True
    assert rendered["records"][0]["source_plan_path"] == str(plan_path.resolve())

    capsys.readouterr()
    assert main(["show-listing-file", str(export_path)]) == 0
    listing_text = capsys.readouterr().out
    assert "Listing type: record_export" in listing_text
    assert "Workspace: demo" in listing_text
    assert "saved_plan_records_total: 1" in listing_text

    capsys.readouterr()
    assert main(["validate-listing-file", str(export_path), "--json"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["listing_type"] == "record_export"
    assert validated["valid"] is True


def test_show_iterations_filters_by_stage(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    plan_path = tmp_path / "planned_holdout_iteration.json"
    config_path = tmp_path / "generic.yaml"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Screening smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Direct holdout smoke check",
                "--stage",
                "holdout",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Planned holdout smoke check",
                "--stage",
                "holdout",
                "--root",
                str(workspaces_root),
                "--output",
                str(plan_path),
            ]
        )
        == 0
    )
    assert main(["run-planned-iteration", "--plan", str(plan_path)]) == 0

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--stage",
                "holdout",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["track_id"] is None
    assert rendered["stage"] == "holdout"
    assert rendered["saved_plan_only"] is False
    assert rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in rendered["iterations"]] == [
        "iter_0002",
        "iter_0003",
    ]
    assert {item["stage"] for item in rendered["iterations"]} == {"holdout"}
    assert rendered["iterations"][0]["saved_plan_run"] is False
    assert rendered["iterations"][1]["saved_plan_run"] is True
    assert rendered["iterations"][1]["source_plan_path"] == str(plan_path.resolve())

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--stage",
                "holdout",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert "Stage filter: holdout" in text_output
    assert "Saved-plan runs: 1" in text_output
    assert "iter_0001" not in text_output
    assert "iter_0002" in text_output
    assert "iter_0003" in text_output

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--stage",
                "holdout",
                "--saved-plan-only",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    filtered_rendered = json.loads(capsys.readouterr().out)
    assert filtered_rendered["stage"] == "holdout"
    assert filtered_rendered["saved_plan_only"] is True
    assert filtered_rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in filtered_rendered["iterations"]] == [
        "iter_0003",
    ]


def test_show_iterations_filters_by_status(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    success_config_path = tmp_path / "generic_success.yaml"
    success_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "status-smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(success_config_path),
                "--hypothesis",
                "Successful status smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(success_config_path),
                "--hypothesis",
                "Dry-run status smoke check",
                "--dry-run",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    inconclusive_config_path = tmp_path / "generic_inconclusive.yaml"
    counter_path = tmp_path / "repeat_counter.txt"
    inconclusive_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "validation-smoke",
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        f"from pathlib import Path; path = Path({str(counter_path)!r}); "
                        "count = int(path.read_text(encoding='utf-8')) if path.exists() else 0; "
                        "path.write_text(str(count + 1), encoding='utf-8'); "
                        "print(json.dumps({'pass_rate': 1.0 if count < 2 else 0.0}))"
                    ),
                ],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(inconclusive_config_path),
                "--hypothesis",
                "Inconclusive status smoke check",
                "--root",
                str(workspaces_root),
                "--stage",
                "validation",
                "--repeat",
                "3",
            ]
        )
        == 0
    )

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--status",
                "dry_run",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    dry_run_rendered = json.loads(capsys.readouterr().out)
    assert dry_run_rendered["status"] == "dry_run"
    assert dry_run_rendered["saved_plan_only"] is False
    assert dry_run_rendered["saved_plan_iterations_total"] == 0
    assert [item["iteration_id"] for item in dry_run_rendered["iterations"]] == [
        "iter_0002",
    ]
    assert {item["status"] for item in dry_run_rendered["iterations"]} == {"dry_run"}

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--status",
                "dry_run",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    dry_run_text_output = capsys.readouterr().out
    assert "Status filter: dry_run" in dry_run_text_output
    assert "- iter_0001:" not in dry_run_text_output
    assert "- iter_0002:" in dry_run_text_output
    assert "- iter_0003:" not in dry_run_text_output

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--stage",
                "validation",
                "--status",
                "inconclusive",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    inconclusive_rendered = json.loads(capsys.readouterr().out)
    assert inconclusive_rendered["stage"] == "validation"
    assert inconclusive_rendered["status"] == "inconclusive"
    assert [item["iteration_id"] for item in inconclusive_rendered["iterations"]] == [
        "iter_0003",
    ]
    assert {item["status"] for item in inconclusive_rendered["iterations"]} == {
        "inconclusive"
    }


def test_show_iterations_filters_by_benchmark_name(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    plan_path = tmp_path / "planned_holdout_iteration.json"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    smoke_config_path = tmp_path / "generic_smoke.yaml"
    smoke_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "search-smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    holdout_config_path = tmp_path / "generic_holdout.yaml"
    holdout_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "holdout-smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(smoke_config_path),
                "--hypothesis",
                "Search smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(holdout_config_path),
                "--hypothesis",
                "Direct holdout smoke check",
                "--root",
                str(workspaces_root),
                "--stage",
                "holdout",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(holdout_config_path),
                "--hypothesis",
                "Planned holdout smoke check",
                "--stage",
                "holdout",
                "--root",
                str(workspaces_root),
                "--output",
                str(plan_path),
            ]
        )
        == 0
    )
    assert main(["run-planned-iteration", "--plan", str(plan_path)]) == 0

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--benchmark-name",
                "holdout-smoke",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["benchmark_name"] == "holdout-smoke"
    assert rendered["saved_plan_only"] is False
    assert rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in rendered["iterations"]] == [
        "iter_0002",
        "iter_0003",
    ]
    assert {item["benchmark_name"] for item in rendered["iterations"]} == {
        "holdout-smoke"
    }
    assert rendered["iterations"][1]["saved_plan_run"] is True

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--benchmark-name",
                "holdout-smoke",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert "Benchmark filter: holdout-smoke" in text_output
    assert "- iter_0001:" not in text_output
    assert "- iter_0002:" in text_output
    assert "* iter_0003:" in text_output

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--benchmark-name",
                "holdout-smoke",
                "--saved-plan-only",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    filtered_rendered = json.loads(capsys.readouterr().out)
    assert filtered_rendered["benchmark_name"] == "holdout-smoke"
    assert filtered_rendered["saved_plan_only"] is True
    assert filtered_rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in filtered_rendered["iterations"]] == [
        "iter_0003",
    ]


def test_show_iterations_filters_by_adapter_id(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    plan_path = tmp_path / "planned_pytest_iteration.json"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    generic_config_path = tmp_path / "generic_smoke.yaml"
    generic_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "generic-smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text(
        "def test_ok() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    pytest_config_path = tmp_path / "pytest_smoke.yaml"
    pytest_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "pytest-smoke",
                "workdir": str(tmp_path),
                "module_mode": True,
                "targets": ["tests/test_sample.py"],
                "extra_args": ["-q"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(generic_config_path),
                "--hypothesis",
                "Generic smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "pytest",
                "--config",
                str(pytest_config_path),
                "--hypothesis",
                "Direct pytest smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "pytest",
                "--config",
                str(pytest_config_path),
                "--hypothesis",
                "Planned pytest smoke check",
                "--root",
                str(workspaces_root),
                "--output",
                str(plan_path),
            ]
        )
        == 0
    )
    assert main(["run-planned-iteration", "--plan", str(plan_path)]) == 0

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--adapter-id",
                "pytest",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["adapter_id"] == "pytest"
    assert rendered["saved_plan_only"] is False
    assert rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in rendered["iterations"]] == [
        "iter_0002",
        "iter_0003",
    ]
    assert {item["adapter_id"] for item in rendered["iterations"]} == {"pytest"}
    assert rendered["iterations"][1]["saved_plan_run"] is True

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--adapter-id",
                "pytest",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert "Adapter filter: pytest" in text_output
    assert "- iter_0001:" not in text_output
    assert "- iter_0002:" in text_output
    assert "* iter_0003:" in text_output

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--adapter-id",
                "pytest",
                "--saved-plan-only",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    filtered_rendered = json.loads(capsys.readouterr().out)
    assert filtered_rendered["adapter_id"] == "pytest"
    assert filtered_rendered["saved_plan_only"] is True
    assert filtered_rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in filtered_rendered["iterations"]] == [
        "iter_0003",
    ]


def test_show_iterations_filters_by_created_at(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    plan_path = tmp_path / "planned_smoke_iteration.json"
    config_path = tmp_path / "generic_smoke.yaml"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "time-smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Early smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Middle smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Planned late smoke check",
                "--root",
                str(workspaces_root),
                "--output",
                str(plan_path),
            ]
        )
        == 0
    )
    assert main(["run-planned-iteration", "--plan", str(plan_path)]) == 0

    timestamp_map = {
        "iter_0001": "2026-01-10T08:00:00Z",
        "iter_0002": "2026-01-11T12:00:00Z",
        "iter_0003": "2026-01-12T18:30:00Z",
    }
    for iteration_id, created_at in timestamp_map.items():
        summary_path = (
            workspaces_root
            / "demo"
            / "iterations"
            / iteration_id
            / "summary.json"
        )
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["created_at"] = created_at
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--since",
                "2026-01-11",
                "--until",
                "2026-01-12",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["since"] == "2026-01-11"
    assert rendered["until"] == "2026-01-12"
    assert rendered["saved_plan_only"] is False
    assert rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in rendered["iterations"]] == [
        "iter_0002",
        "iter_0003",
    ]

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--since",
                "2026-01-11",
                "--until",
                "2026-01-12",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert "Since filter: 2026-01-11" in text_output
    assert "Until filter: 2026-01-12" in text_output
    assert "- iter_0001:" not in text_output
    assert "- iter_0002:" in text_output
    assert "* iter_0003:" in text_output

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--since",
                "2026-01-12T00:00:00Z",
                "--saved-plan-only",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    filtered_rendered = json.loads(capsys.readouterr().out)
    assert filtered_rendered["since"] == "2026-01-12T00:00:00Z"
    assert filtered_rendered["until"] is None
    assert filtered_rendered["saved_plan_only"] is True
    assert filtered_rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in filtered_rendered["iterations"]] == [
        "iter_0003",
    ]


def test_show_iterations_sorts_results(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    config_path = tmp_path / "generic_smoke.yaml"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "sort-smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    for hypothesis in (
        "First sort smoke check",
        "Second sort smoke check",
        "Third sort smoke check",
    ):
        assert (
            main(
                [
                    "run-iteration",
                    "--workspace-id",
                    "demo",
                    "--adapter",
                    "generic_command",
                    "--config",
                    str(config_path),
                    "--hypothesis",
                    hypothesis,
                    "--root",
                    str(workspaces_root),
                ]
            )
            == 0
        )

    timestamp_map = {
        "iter_0001": "2026-01-12T18:30:00Z",
        "iter_0002": "2026-01-10T08:00:00Z",
        "iter_0003": "2026-01-11T12:00:00Z",
    }
    for iteration_id, created_at in timestamp_map.items():
        summary_path = (
            workspaces_root
            / "demo"
            / "iterations"
            / iteration_id
            / "summary.json"
        )
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["created_at"] = created_at
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    default_rendered = json.loads(capsys.readouterr().out)
    assert default_rendered["sort_by"] == "iteration_id"
    assert default_rendered["descending"] is False
    assert [item["iteration_id"] for item in default_rendered["iterations"]] == [
        "iter_0001",
        "iter_0002",
        "iter_0003",
    ]

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--sort-by",
                "created_at",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    created_at_rendered = json.loads(capsys.readouterr().out)
    assert created_at_rendered["sort_by"] == "created_at"
    assert created_at_rendered["descending"] is False
    assert [item["iteration_id"] for item in created_at_rendered["iterations"]] == [
        "iter_0002",
        "iter_0003",
        "iter_0001",
    ]

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--sort-by",
                "created_at",
                "--descending",
                "--limit",
                "2",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    descending_rendered = json.loads(capsys.readouterr().out)
    assert descending_rendered["sort_by"] == "created_at"
    assert descending_rendered["descending"] is True
    assert [item["iteration_id"] for item in descending_rendered["iterations"]] == [
        "iter_0001",
        "iter_0003",
    ]

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--sort-by",
                "created_at",
                "--descending",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert "Sort: created_at desc" in text_output
    assert text_output.index("- iter_0001:") < text_output.index("* iter_0003:")
    assert text_output.index("* iter_0003:") < text_output.index("- iter_0002:")


def test_show_iterations_filters_by_hypothesis_substring(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    plan_path = tmp_path / "planned_hypothesis_iteration.json"
    config_path = tmp_path / "generic_smoke.yaml"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "hypothesis-smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Alpha smoke check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Beta HOLDOUT check",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "planned beta replay",
                "--root",
                str(workspaces_root),
                "--output",
                str(plan_path),
            ]
        )
        == 0
    )
    assert main(["run-planned-iteration", "--plan", str(plan_path)]) == 0

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--hypothesis-contains",
                "beta",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["hypothesis_contains"] == "beta"
    assert rendered["saved_plan_only"] is False
    assert rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in rendered["iterations"]] == [
        "iter_0002",
        "iter_0003",
    ]
    assert [item["hypothesis"] for item in rendered["iterations"]] == [
        "Beta HOLDOUT check",
        "planned beta replay",
    ]
    assert rendered["iterations"][1]["saved_plan_run"] is True

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--hypothesis-contains",
                "beta",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert "Hypothesis filter: beta" in text_output
    assert "- iter_0001:" not in text_output
    assert "- iter_0002:" in text_output
    assert "* iter_0003:" in text_output

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--hypothesis-contains",
                "beta",
                "--saved-plan-only",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    filtered_rendered = json.loads(capsys.readouterr().out)
    assert filtered_rendered["hypothesis_contains"] == "beta"
    assert filtered_rendered["saved_plan_only"] is True
    assert filtered_rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in filtered_rendered["iterations"]] == [
        "iter_0003",
    ]


def test_show_iterations_filters_by_notes_substring(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    plan_path = tmp_path / "planned_notes_iteration.json"
    config_path = tmp_path / "generic_smoke.yaml"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "notes-smoke",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Alpha notes check",
                "--notes",
                "keep this baseline stable",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Beta notes check",
                "--notes",
                "Needs HOLDOUT review",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "planned notes replay",
                "--root",
                str(workspaces_root),
                "--output",
                str(plan_path),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run-planned-iteration",
                "--plan",
                str(plan_path),
            ]
        )
        == 0
    )

    # Patch the replayed run notes so the filter covers a saved-plan iteration too.
    replay_summary_path = (
        workspaces_root
        / "demo"
        / "iterations"
        / "iter_0003"
        / "summary.json"
    )
    replay_summary = json.loads(replay_summary_path.read_text(encoding="utf-8"))
    replay_summary["notes"] = "planned holdout replay note"
    replay_summary_path.write_text(json.dumps(replay_summary, indent=2) + "\n", encoding="utf-8")

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--notes-contains",
                "holdout",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["notes_contains"] == "holdout"
    assert rendered["saved_plan_only"] is False
    assert rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in rendered["iterations"]] == [
        "iter_0002",
        "iter_0003",
    ]
    assert [item["notes"] for item in rendered["iterations"]] == [
        "Needs HOLDOUT review",
        "planned holdout replay note",
    ]
    assert rendered["iterations"][1]["saved_plan_run"] is True

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--notes-contains",
                "holdout",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert "Notes filter: holdout" in text_output
    assert "- iter_0001:" not in text_output
    assert "- iter_0002:" in text_output
    assert "* iter_0003:" in text_output

    capsys.readouterr()
    assert (
        main(
            [
                "show-iterations",
                "--workspace-id",
                "demo",
                "--notes-contains",
                "holdout",
                "--saved-plan-only",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    filtered_rendered = json.loads(capsys.readouterr().out)
    assert filtered_rendered["notes_contains"] == "holdout"
    assert filtered_rendered["saved_plan_only"] is True
    assert filtered_rendered["saved_plan_iterations_total"] == 1
    assert [item["iteration_id"] for item in filtered_rendered["iterations"]] == [
        "iter_0003",
    ]


def test_run_iteration_records_parsed_artifact_sources_in_summary(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic_metrics_file.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "metrics-file-smoke",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; from pathlib import Path; "
                        "Path('metrics.json').write_text("
                        "json.dumps({'pass_rate': 1.0}), encoding='utf-8'"
                        ")"
                    ),
                ],
                "metrics_parser": {
                    "format": "json_file",
                    "path": "metrics.json",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Keep parser provenance in the iteration summary",
            "--root",
            str(workspaces_root),
            "--repeat",
            "2",
        ]
    )
    assert exit_code == 0

    iteration_dir = workspaces_root / "demo" / "iterations" / "iter_0001"
    summary = json.loads((iteration_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["parsed_artifact_sources"] == {
        "metrics": [
            {
                "origin": "metrics_parser.path",
                "path": str((tmp_path / "metrics.json").resolve()),
                "validation_indices": [1, 2],
            }
        ]
    }
    assert json.loads(
        (iteration_dir / "parsed_artifact_sources.json").read_text(encoding="utf-8")
    ) == summary["parsed_artifact_sources"]


def test_run_iteration_applies_edit_plan_in_bounded_mode(tmp_path: Path) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "target"
    target_root.mkdir()
    target_file = target_root / "src" / "agent.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("STATE = 'old'\n", encoding="utf-8")

    main(
        [
            "setup",
            "--output",
            str(settings),
            "--autonomy",
            "bounded",
            "--editable-surface",
            "src",
        ]
    )
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; from pathlib import Path; "
                        "Path('metrics.json').write_text("
                        "json.dumps({'pass_rate': 1.0}), encoding='utf-8'"
                        "); print('ok')"
                    ),
                ],
                "metrics_parser": {
                    "format": "json_file",
                    "path": str(tmp_path / "metrics.json"),
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "format_version": "autoharness.edit_plan.v1",
                "summary": "Update agent state",
                "operations": [
                    {
                        "type": "search_replace",
                        "path": "src/agent.py",
                        "search": "old",
                        "replace": "new",
                        "expected_count": 1,
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Update agent state before running the smoke check",
            "--root",
            str(workspaces_root),
            "--edit-plan",
            str(edit_plan_path),
            "--target-root",
            str(target_root),
        ]
    )
    assert exit_code == 0

    assert target_file.read_text(encoding="utf-8") == "STATE = 'old'\n"
    iteration_summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert iteration_summary["status"] == "success"
    assert iteration_summary["edit_application"]["status"] == "applied"
    assert iteration_summary["edit_restore"]["status"] == "reverted"
    diff_path = (
        workspaces_root / "demo" / "iterations" / "iter_0001" / "candidate.patch"
    )
    assert diff_path.exists()
    diff_text = diff_path.read_text(encoding="utf-8")
    assert "--- a/src/agent.py" in diff_text
    assert "+STATE = 'new'" in diff_text


def test_run_iteration_can_keep_applied_edits_on_request(tmp_path: Path) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "target"
    target_root.mkdir()
    target_file = target_root / "src" / "agent.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("STATE = 'old'\n", encoding="utf-8")

    main(
        [
            "setup",
            "--output",
            str(settings),
            "--autonomy",
            "bounded",
            "--editable-surface",
            "src",
        ]
    )
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "search_replace",
                        "path": "src/agent.py",
                        "search": "old",
                        "replace": "new",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Keep the candidate edits in place",
            "--root",
            str(workspaces_root),
            "--edit-plan",
            str(edit_plan_path),
            "--target-root",
            str(target_root),
            "--keep-applied-edits",
        ]
    )
    assert exit_code == 0
    assert target_file.read_text(encoding="utf-8") == "STATE = 'new'\n"

    iteration_summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert iteration_summary["edit_restore"]["status"] == "kept"
    assert "staging" not in iteration_summary


def test_run_iteration_downgrades_protected_edit_to_proposal_only(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "target"
    target_root.mkdir()
    target_file = target_root / "src" / "agent.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("STATE = 'old'\n", encoding="utf-8")

    main(
        [
            "setup",
            "--output",
            str(settings),
            "--autonomy",
            "full",
            "--protected-surface",
            "src",
        ]
    )
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "search_replace",
                        "path": "src/agent.py",
                        "search": "old",
                        "replace": "new",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Attempt protected edit",
            "--root",
            str(workspaces_root),
            "--edit-plan",
            str(edit_plan_path),
            "--target-root",
            str(target_root),
        ]
    )
    assert exit_code == 0

    assert target_file.read_text(encoding="utf-8") == "STATE = 'old'\n"
    registry_dir = workspaces_root / "demo" / "tracks" / "main" / "registry"
    records = sorted(registry_dir.glob("*.json"))
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["status"] == "dry_run"
    assert record["payload"]["edit_application"]["status"] == "proposal_only"
    assert record["payload"]["edit_restore"]["status"] == "not_applied"


def test_run_iteration_copy_stage_preserves_source_tree_and_rewrites_workdir(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "target"
    target_root.mkdir()
    target_file = target_root / "src" / "agent.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("STATE = 'old'\n", encoding="utf-8")

    main(
        [
            "setup",
            "--output",
            str(settings),
            "--autonomy",
            "bounded",
            "--editable-surface",
            "src",
        ]
    )
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "workdir": str(target_root),
                "command": [
                    "python",
                    "-c",
                    (
                        "from pathlib import Path; import os; "
                        "Path('cwd.txt').write_text(os.getcwd(), encoding='utf-8'); "
                        "print('ok')"
                    ),
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "search_replace",
                        "path": "src/agent.py",
                        "search": "old",
                        "replace": "new",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Run the benchmark in a staged copy",
            "--root",
            str(workspaces_root),
            "--edit-plan",
            str(edit_plan_path),
            "--target-root",
            str(target_root),
            "--staging-mode",
            "copy",
        ]
    )
    assert exit_code == 0

    assert target_file.read_text(encoding="utf-8") == "STATE = 'old'\n"
    assert not (target_root / "cwd.txt").exists()

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["staging"]["mode"] == "copy"
    staged_root = Path(summary["staging"]["staged_root"])
    assert staged_root.exists()
    assert (staged_root / "cwd.txt").read_text(encoding="utf-8") == str(staged_root)
    assert (workspaces_root / "demo" / "iterations" / "iter_0001" / "staging.json").exists()
    assert summary["staging"]["decision"]["requested_mode"] == "copy"
    assert summary["staging"]["decision"]["resolved_mode"] == "copy"


def test_run_iteration_auto_stage_for_generic_command(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "target"
    target_root.mkdir()
    target_file = target_root / "src" / "agent.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("STATE = 'old'\n", encoding="utf-8")

    main(
        [
            "setup",
            "--output",
            str(settings),
            "--autonomy",
            "bounded",
            "--editable-surface",
            "src",
        ]
    )
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "command": [
                    "python",
                    "-c",
                    (
                        "from pathlib import Path; import os; "
                        "Path('cwd.txt').write_text(os.getcwd(), encoding='utf-8'); "
                        "print('ok')"
                    ),
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "search_replace",
                        "path": "src/agent.py",
                        "search": "old",
                        "replace": "new",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Auto stage the local generic command run",
            "--root",
            str(workspaces_root),
            "--edit-plan",
            str(edit_plan_path),
            "--target-root",
            str(target_root),
        ]
    )
    assert exit_code == 0

    assert target_file.read_text(encoding="utf-8") == "STATE = 'old'\n"
    assert not (target_root / "cwd.txt").exists()

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["staging"]["decision"]["requested_mode"] == "auto"
    assert summary["staging"]["decision"]["resolved_mode"] == "copy"
    staged_root = Path(summary["staging"]["staged_root"])
    assert (staged_root / "cwd.txt").read_text(encoding="utf-8") == str(staged_root)


def test_run_iteration_auto_stage_for_hal_nested_config(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "target"
    target_root.mkdir()
    target_file = target_root / "src" / "agent.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("STATE = 'old'\n", encoding="utf-8")

    main(
        [
            "setup",
            "--output",
            str(settings),
            "--autonomy",
            "bounded",
            "--editable-surface",
            "src",
        ]
    )
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "hal.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark": "taubench_airline",
                "agent_dir": "/opt/demo-agent",
                "agent_function": "agent.run",
                "agent_name": "Demo Agent",
                "agent_args": {"task_path": "data/tasks.jsonl"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "search_replace",
                        "path": "src/agent.py",
                        "search": "old",
                        "replace": "new",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "hal",
            "--config",
            str(config_path),
            "--hypothesis",
            "Auto stage HAL when nested args reference target-relative paths",
            "--root",
            str(workspaces_root),
            "--edit-plan",
            str(edit_plan_path),
            "--target-root",
            str(target_root),
            "--dry-run",
        ]
    )
    assert exit_code == 0

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["staging"]["decision"]["requested_mode"] == "auto"
    assert summary["staging"]["decision"]["resolved_mode"] == "copy"
    staged_root = Path(summary["staging"]["staged_root"])
    registry_dir = workspaces_root / "demo" / "tracks" / "main" / "registry"
    record = json.loads(
        sorted(registry_dir.glob("*.json"))[0].read_text(encoding="utf-8")
    )
    command = record["payload"]["command"]
    task_arg = command[command.index("-A") + 1]
    assert task_arg == f"task_path={str((staged_root / 'data/tasks.jsonl').resolve())}"


def test_run_iteration_auto_stage_for_tau2_nested_config(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "target"
    target_root.mkdir()
    target_file = target_root / "src" / "agent.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("STATE = 'old'\n", encoding="utf-8")

    main(
        [
            "setup",
            "--output",
            str(settings),
            "--autonomy",
            "bounded",
            "--editable-surface",
            "src",
        ]
    )
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "tau2.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "domain": "airline",
                "retrieval_config_kwargs": {"cache_dir": "artifacts/cache"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "search_replace",
                        "path": "src/agent.py",
                        "search": "old",
                        "replace": "new",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "tau2_bench",
            "--config",
            str(config_path),
            "--hypothesis",
            "Auto stage Tau2 when nested args reference target-relative paths",
            "--root",
            str(workspaces_root),
            "--edit-plan",
            str(edit_plan_path),
            "--target-root",
            str(target_root),
            "--dry-run",
        ]
    )
    assert exit_code == 0

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["staging"]["decision"]["requested_mode"] == "auto"
    assert summary["staging"]["decision"]["resolved_mode"] == "copy"
    staged_root = Path(summary["staging"]["staged_root"])
    registry_dir = workspaces_root / "demo" / "tracks" / "main" / "registry"
    record = json.loads(
        sorted(registry_dir.glob("*.json"))[0].read_text(encoding="utf-8")
    )
    command = record["payload"]["command"]
    encoded_args = command[command.index("--retrieval-config-kwargs") + 1]
    assert json.loads(encoded_args) == {
        "cache_dir": str((staged_root / "artifacts/cache").resolve())
    }


def test_run_iteration_records_validation_summary_and_metrics(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic_repeat.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "repeat-smoke",
                "command": [
                    sys.executable,
                    "-c",
                    "import json; print(json.dumps({'pass_rate': 1.0, 'score': 2}))",
                ],
                "metrics_parser": {
                    "format": "json_stdout",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Validate the candidate more than once",
            "--root",
            str(workspaces_root),
            "--repeat",
            "2",
        ]
    )
    assert exit_code == 0

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["metrics"] == {"pass_rate": 1.0, "score": 2.0}
    assert summary["validation_summary"]["run_count"] == 2
    assert summary["validation_summary"]["success_count"] == 2
    assert (
        summary["validation_summary"]["success_rate_confidence_interval"]["confidence_level"]
        == 0.85
    )

    state = json.loads(
        (workspaces_root / "demo" / "state.json").read_text(encoding="utf-8")
    )
    assert state["summary"]["validation_runs_total"] == 2


def test_run_iteration_applies_stage_override_and_records_stage_gate(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic_stage.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "search-smoke",
                "command": [
                    sys.executable,
                    "-c",
                    "import json; print(json.dumps({'pass_rate': 1.0}))",
                ],
                "metrics_parser": {"format": "json_stdout"},
                "stage_overrides": {
                    "holdout": {
                        "benchmark_name": "holdout-smoke",
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Run the holdout stage with stage-specific config",
            "--root",
            str(workspaces_root),
            "--stage",
            "holdout",
        ]
    )
    assert exit_code == 0

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["stage"] == "holdout"
    assert summary["benchmark_name"] == "holdout-smoke"
    assert summary["stage_evaluation"]["decision"] == "passed"
    assert summary["stage_evaluation"]["decision_mode"] == "confidence_interval"
    assert summary["stage_evaluation"]["benchmark_target"] == "tau-bench-airline"
    assert summary["stage_evaluation"]["applied_stage_override"] is True
    assert summary["validation_summary"]["run_count"] == 3

    state = json.loads(
        (workspaces_root / "demo" / "state.json").read_text(encoding="utf-8")
    )
    assert state["summary"]["holdout_iterations_total"] == 1
    assert state["summary"]["holdout_passes_total"] == 1


def test_run_iteration_uses_track_policy_benchmark_target(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )
    assert (
        main(
            [
                "set-track-policy",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--promotion-benchmark",
                "custom-holdout-benchmark",
            ]
        )
        == 0
    )

    config_path = tmp_path / "holdout_smoke.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "holdout-smoke",
                "command": [
                    sys.executable,
                    "-c",
                    "import json; print(json.dumps({'pass_rate': 1.0}))",
                ],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Use the track policy promotion benchmark target",
            "--root",
            str(workspaces_root),
            "--stage",
            "holdout",
        ]
    )
    assert exit_code == 0

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["stage_evaluation"]["benchmark_target"] == "custom-holdout-benchmark"


def test_run_iteration_uses_track_policy_preset_over_workspace_fallback(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )
    main(
        [
            "set-workspace",
            "--workspace-id",
            "demo",
            "--root",
            str(workspaces_root),
            "--promotion-preset",
            "search",
        ]
    )
    main(
        [
            "set-track-policy",
            "--workspace-id",
            "demo",
            "--root",
            str(workspaces_root),
            "--promotion-preset",
            "promotion",
        ]
    )

    config_path = tmp_path / "hal_override.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "agent_name": "Track Override Agent",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "iteration_payload.json"

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "hal",
                "--config",
                str(config_path),
                "--hypothesis",
                "Use the track policy promotion preset",
                "--root",
                str(workspaces_root),
                "--stage",
                "holdout",
                "--dry-run",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["config_preset"] == "promotion"
    assert payload["config_preset_source"] == "policy"
    assert payload["policy_preset"] == "promotion"
    assert payload["stage_evaluation"]["benchmark_preset_target"] == "promotion"
    assert "--docker" in payload["command"]
    assert payload["command"][payload["command"].index("--agent_name") + 1] == (
        "Track Override Agent"
    )

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["config_preset"] == "promotion"
    assert summary["config_preset_source"] == "policy"
    assert summary["policy_preset"] == "promotion"
    assert summary["stage_evaluation"]["benchmark_preset_target"] == "promotion"


def test_run_iteration_supports_inline_overrides_without_config_when_preset_pinned(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )
    main(
        [
            "set-track-policy",
            "--workspace-id",
            "demo",
            "--root",
            str(workspaces_root),
            "--promotion-preset",
            "promotion",
        ]
    )

    output_path = tmp_path / "inline_iteration_payload.json"
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "hal",
                "--hypothesis",
                "Use inline overrides with a policy preset",
                "--root",
                str(workspaces_root),
                "--stage",
                "holdout",
                "--dry-run",
                "--set",
                "agent_dir=agents/inline",
                "--set",
                "agent_name=Inline Iteration Agent",
                "--set",
                "benchmark_args.limit=8",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["config_preset"] == "promotion"
    assert payload["command"][payload["command"].index("--agent_dir") + 1] == "agents/inline"
    assert payload["command"][payload["command"].index("--agent_name") + 1] == (
        "Inline Iteration Agent"
    )
    assert "--docker" in payload["command"]

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["config_preset"] == "promotion"
    assert summary["stage_evaluation"]["benchmark_preset_target"] == "promotion"


def test_plan_iteration_renders_policy_aware_stage_command(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )
    main(
        [
            "set-track-policy",
            "--workspace-id",
            "demo",
            "--root",
            str(workspaces_root),
            "--promotion-benchmark",
            "custom-holdout-benchmark",
            "--promotion-preset",
            "promotion",
        ]
    )

    output_path = tmp_path / "plan_iteration.json"
    capsys.readouterr()
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "hal",
                "--root",
                str(workspaces_root),
                "--stage",
                "holdout",
                "--set",
                "agent_dir=agents/inline",
                "--set",
                "agent_name=Planned Agent",
                "--json",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    rendered = json.loads(capsys.readouterr().out)
    assert json.loads(output_path.read_text(encoding="utf-8")) == rendered
    assert rendered["format_version"] == "autoharness.iteration_plan.v1"
    assert rendered["workspace_id"] == "demo"
    assert rendered["track_id"] == "main"
    assert rendered["stage"] == "holdout"
    assert rendered["benchmark_target"] == "custom-holdout-benchmark"
    assert rendered["benchmark_preset_target"] == "promotion"
    assert rendered["selected_preset"] == "promotion"
    assert rendered["selected_preset_source"] == "policy"
    assert (
        rendered["suggested_hypothesis"]
        == "Run holdout iteration for custom-holdout-benchmark with hal using promotion preset"
    )
    assert rendered["suggested_command"][:5] == [
        "autoharness",
        "run-iteration",
        "--workspace-id",
        "demo",
        "--track-id",
    ]
    assert "--config" not in rendered["suggested_command"]
    assert "--set" in rendered["suggested_command"]
    assert rendered["effective_config"]["agent_dir"] == "agents/inline"
    assert rendered["effective_config"]["agent_name"] == "Planned Agent"
    assert rendered["effective_config"]["docker"] is True
    assert rendered["planned_invocation"]["command"][0] == "hal-eval"
    assert "--docker" in rendered["planned_invocation"]["command"]
    assert (
        rendered["effective_track_policy_sources"]["promotion_preset"]
        == "track_policy"
    )

    capsys.readouterr()
    assert main(["show-plan-file", str(output_path), "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["format_version"] == "autoharness.iteration_plan.v1"
    assert shown["workspace_id"] == "demo"
    assert shown["track_id"] == "main"
    assert shown["adapter_id"] == "hal"
    assert shown["stage"] == "holdout"
    assert shown["legacy_format"] is False

    capsys.readouterr()
    assert main(["show-artifact-file", str(output_path), "--json"]) == 0
    generic_shown = json.loads(capsys.readouterr().out)
    assert generic_shown["workspace_id"] == "demo"
    assert generic_shown["track_id"] == "main"
    assert generic_shown["adapter_id"] == "hal"

    capsys.readouterr()
    assert main(["validate-plan-file", str(output_path), "--json"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["valid"] is True
    assert validated["format_version"] == "autoharness.iteration_plan.v1"

    capsys.readouterr()
    assert main(["validate-artifact-file", str(output_path), "--json"]) == 0
    generic_validated = json.loads(capsys.readouterr().out)
    assert generic_validated["valid"] is True
    assert generic_validated["format_version"] == "autoharness.iteration_plan.v1"

    legacy_plan_path = tmp_path / "legacy_plan.json"
    legacy_rendered = dict(rendered)
    legacy_rendered.pop("format_version")
    legacy_rendered.pop("planned_at")
    legacy_plan_path.write_text(
        json.dumps(legacy_rendered) + "\n",
        encoding="utf-8",
    )
    capsys.readouterr()
    assert main(["validate-plan-file", str(legacy_plan_path), "--json"]) == 0
    legacy_validated = json.loads(capsys.readouterr().out)
    assert legacy_validated["valid"] is True
    assert legacy_validated["legacy_format"] is True
    assert legacy_validated["format_version"] is None

    invalid_plan_path = tmp_path / "invalid_plan.json"
    invalid_plan_path.write_text(
        json.dumps(
            {
                "format_version": "autoharness.iteration_plan.v1",
                "suggested_command": ["autoharness", "run-iteration"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    capsys.readouterr()
    assert main(["validate-plan-file", str(invalid_plan_path), "--json"]) == 1
    invalid_rendered = json.loads(capsys.readouterr().out)
    assert invalid_rendered["valid"] is False
    assert "Missing or invalid `workspace_id`." in invalid_rendered[
        "validation_errors"
    ]
    assert "Missing or invalid `planned_invocation`." in invalid_rendered[
        "validation_errors"
    ]


def test_plan_iteration_honors_cli_preset_and_config_path(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "hal_override.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "agent_dir": "agents/config",
                "agent_name": "Config Agent",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "plan_iteration_cli.json"
    capsys.readouterr()
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "hal",
                "--root",
                str(workspaces_root),
                "--stage",
                "holdout",
                "--config",
                str(config_path),
                "--preset",
                "promotion",
                "--hypothesis",
                "Manual plan hypothesis",
                "--dry-run",
                "--json",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    rendered = json.loads(capsys.readouterr().out)
    assert json.loads(output_path.read_text(encoding="utf-8")) == rendered
    assert rendered["selected_preset"] == "promotion"
    assert rendered["selected_preset_source"] == "cli"
    assert rendered["suggested_hypothesis"] == "Manual plan hypothesis"
    assert "--config" in rendered["suggested_command"]
    assert "--preset" in rendered["suggested_command"]
    assert "--dry-run" in rendered["suggested_command"]
    assert rendered["effective_config"]["agent_dir"] == "agents/config"
    assert rendered["effective_config"]["docker"] is True


def test_plan_iteration_can_materialize_config_and_hypothesis_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "hal_override.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "agent_dir": "agents/config",
                "agent_name": "Config Agent",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    written_config_path = tmp_path / "planned_config.json"
    written_hypothesis_path = tmp_path / "planned_hypothesis.txt"
    written_command_path = tmp_path / "planned_command.sh"

    capsys.readouterr()
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "hal",
                "--root",
                str(workspaces_root),
                "--stage",
                "holdout",
                "--config",
                str(config_path),
                "--preset",
                "promotion",
                "--set",
                "benchmark_args.limit=12",
                "--write-config",
                str(written_config_path),
                "--write-hypothesis",
                str(written_hypothesis_path),
                "--write-command",
                str(written_command_path),
                "--json",
            ]
        )
        == 0
    )

    rendered = json.loads(capsys.readouterr().out)
    assert rendered["selected_preset"] == "promotion"
    assert rendered["selected_preset_source"] == "cli"
    assert rendered["written_artifacts"] == {
        "config_path": str(written_config_path),
        "config_format": "json",
        "hypothesis_path": str(written_hypothesis_path),
        "command_path": str(written_command_path),
    }
    assert json.loads(written_config_path.read_text(encoding="utf-8")) == rendered["effective_config"]
    assert (
        written_hypothesis_path.read_text(encoding="utf-8")
        == rendered["suggested_hypothesis"] + "\n"
    )
    assert (
        written_command_path.read_text(encoding="utf-8")
        == "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"{rendered['suggested_shell_command']}\n"
    )
    assert written_command_path.stat().st_mode & 0o111
    assert rendered["effective_config"]["agent_dir"] == "agents/config"
    assert rendered["effective_config"]["benchmark_args"]["limit"] == 12
    assert rendered["suggested_command"].count("--config") == 1
    assert str(written_config_path) in rendered["suggested_command"]
    assert str(config_path) not in rendered["suggested_command"]
    assert "--preset" not in rendered["suggested_command"]
    assert "--set" not in rendered["suggested_command"]


def test_run_planned_iteration_replays_saved_plan_from_planning_cwd(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    plan_path = tmp_path / "planned_iteration.json"

    monkeypatch.chdir(tmp_path)
    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = Path("generic_relative.yaml")
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "planned-smoke",
                "command": [
                    sys.executable,
                    "-c",
                    "import json; print(json.dumps({'pass_rate': 1.0}))",
                ],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Planned relative execution",
                "--root",
                str(workspaces_root),
                "--stage",
                "holdout",
                "--output",
                str(plan_path),
            ]
        )
        == 0
    )

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["planning_cwd"] == str(tmp_path)
    assert plan["suggested_command"][:2] == ["autoharness", "run-iteration"]

    other_cwd = tmp_path / "other"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    assert main(["run-planned-iteration", "--plan", str(plan_path)]) == 0

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["hypothesis"] == "Planned relative execution"
    assert summary["status"] == "success"
    assert summary["source_plan_path"] == str(plan_path.resolve())
    iteration_source_plan_path = (
        workspaces_root
        / "demo"
        / "iterations"
        / "iter_0001"
        / "source_plan.json"
    )
    assert json.loads(iteration_source_plan_path.read_text(encoding="utf-8")) == plan

    record_path = next(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["config_path"] == "generic_relative.yaml"
    assert record["source_plan_path"] == str(plan_path.resolve())
    record_id = record["record_id"]

    capsys.readouterr()
    assert (
        main(
            [
                "show-iteration",
                "--workspace-id",
                "demo",
                "--iteration-id",
                "iter_0001",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered_iteration = json.loads(capsys.readouterr().out)
    assert (
        rendered_iteration["artifacts"]["source_plan_artifact_path"]
        == str(iteration_source_plan_path)
    )
    assert rendered_iteration["source_plan"] == plan

    show_record_output_path = tmp_path / "record_from_plan.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-record",
                "--workspace-id",
                "demo",
                "--record-id",
                record_id,
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(show_record_output_path),
            ]
        )
        == 0
    )
    rendered_record = json.loads(capsys.readouterr().out)
    assert json.loads(show_record_output_path.read_text(encoding="utf-8")) == rendered_record
    assert rendered_record["source_plan_artifact_path"] == str(iteration_source_plan_path)
    assert rendered_record["source_plan"] == plan

    capsys.readouterr()
    assert (
        main(
            [
                "show-record",
                "--workspace-id",
                "demo",
                "--record-id",
                record_id,
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert f"Source plan: {plan_path.resolve()}" in text_output
    assert f"Source plan artifact: {iteration_source_plan_path}" in text_output


def test_run_planned_iteration_rejects_non_run_iteration_plan(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "invalid_plan.json"
    plan_path.write_text(
        json.dumps({"suggested_command": ["autoharness", "plan-iteration"]}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="run-iteration"):
        main(["run-planned-iteration", "--plan", str(plan_path)])


def test_run_iteration_marks_inconclusive_stage_when_bounds_straddle_threshold(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic_inconclusive.yaml"
    counter_path = tmp_path / "repeat_counter.txt"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "validation-smoke",
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        f"from pathlib import Path; path = Path({str(counter_path)!r}); "
                        "count = int(path.read_text(encoding='utf-8')) if path.exists() else 0; "
                        "path.write_text(str(count + 1), encoding='utf-8'); "
                        "print(json.dumps({'pass_rate': 1.0 if count < 2 else 0.0}))"
                    ),
                ],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Stage gate should be inconclusive for mixed results",
            "--root",
            str(workspaces_root),
            "--stage",
            "validation",
            "--repeat",
            "3",
        ]
    )
    assert exit_code == 0

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["status"] == "inconclusive"
    assert summary["stage_evaluation"]["decision"] == "inconclusive"

    state = json.loads(
        (workspaces_root / "demo" / "state.json").read_text(encoding="utf-8")
    )
    assert state["summary"]["inconclusive_candidates"] == 1
    assert state["summary"]["validation_inconclusive_total"] == 1


def test_run_iteration_marks_repeated_metric_drift_as_flaky(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    counter_path = tmp_path / "repeat_counter.txt"
    config_path = tmp_path / "generic_flaky.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "validation-flaky",
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        f"from pathlib import Path; path = Path({str(counter_path)!r}); "
                        "count = int(path.read_text(encoding='utf-8')) if path.exists() else 0; "
                        "path.write_text(str(count + 1), encoding='utf-8'); "
                        "print(json.dumps({'pass_rate': 1.0, 'score': float(count)}))"
                    ),
                ],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Repeated validation should expose flaky metrics",
                "--root",
                str(workspaces_root),
                "--stage",
                "validation",
                "--repeat",
                "2",
            ]
        )
        == 0
    )

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    stability_summary = summary["validation_summary"]["stability_summary"]
    assert stability_summary["flaky"] is True
    assert stability_summary["varying_metric_keys"] == ["score"]
    assert stability_summary["varying_metric_count"] == 1
    assert summary["stage_evaluation"]["stability_summary"]["flaky"] is True


def test_run_iteration_can_compare_against_explicit_baseline_record(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    baseline_config_path = tmp_path / "baseline.yaml"
    baseline_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "baseline-smoke",
                "command": [
                    sys.executable,
                    "-c",
                    "import json; print(json.dumps({'pass_rate': 0.0}))",
                ],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(baseline_config_path),
            "--hypothesis",
            "Create a weak baseline",
            "--root",
            str(workspaces_root),
            "--stage",
            "holdout",
            "--repeat",
            "3",
        ]
    )
    assert exit_code == 0

    registry_dir = workspaces_root / "demo" / "tracks" / "main" / "registry"
    baseline_record_id = sorted(registry_dir.glob("*.json"))[0].stem

    candidate_config_path = tmp_path / "candidate.yaml"
    candidate_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "candidate-smoke",
                "command": [
                    sys.executable,
                    "-c",
                    "import json; print(json.dumps({'pass_rate': 1.0}))",
                ],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(candidate_config_path),
            "--hypothesis",
            "Beat the explicit baseline",
            "--root",
            str(workspaces_root),
            "--stage",
            "holdout",
            "--baseline-record-id",
            baseline_record_id,
            "--repeat",
            "3",
        ]
    )
    assert exit_code == 0

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0002"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["stage_evaluation"]["decision"] == "passed"
    assert summary["stage_evaluation"]["baseline_comparison"]["decision"] == "improved"
    assert (
        summary["stage_evaluation"]["baseline_comparison"]["comparison_mode"]
        == "paired_delta"
    )
    assert (
        summary["stage_evaluation"]["baseline_comparison"]["baseline_label"]
        == baseline_record_id
    )


def test_run_iteration_prefers_task_aware_baseline_comparison(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    baseline_config_path = tmp_path / "baseline_tasks.yaml"
    baseline_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "baseline-tasks",
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        "print(json.dumps({"
                        "'pass_rate': 0.0, "
                        "'tasks': ["
                        "{'task_id': 'task-1', 'score': 0.0}, "
                        "{'task_id': 'task-2', 'score': 0.0}"
                        "]"
                        "}))"
                    ),
                ],
                "metrics_parser": {"format": "json_stdout", "include": ["pass_rate"]},
                "task_results_parser": {
                    "format": "json_stdout",
                    "key_path": ["tasks"],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(baseline_config_path),
            "--hypothesis",
            "Record a weak task baseline",
            "--root",
            str(workspaces_root),
            "--stage",
            "screening",
        ]
    )
    assert exit_code == 0

    registry_dir = workspaces_root / "demo" / "tracks" / "main" / "registry"
    baseline_record_id = sorted(registry_dir.glob("*.json"))[0].stem

    candidate_config_path = tmp_path / "candidate_tasks.yaml"
    candidate_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "candidate-tasks",
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        "print(json.dumps({"
                        "'pass_rate': 1.0, "
                        "'tasks': ["
                        "{'task_id': 'task-1', 'score': 1.0}, "
                        "{'task_id': 'task-2', 'score': 1.0}"
                        "]"
                        "}))"
                    ),
                ],
                "metrics_parser": {"format": "json_stdout", "include": ["pass_rate"]},
                "task_results_parser": {
                    "format": "json_stdout",
                    "key_path": ["tasks"],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(candidate_config_path),
            "--hypothesis",
            "Beat the baseline on matched tasks",
            "--root",
            str(workspaces_root),
            "--stage",
            "screening",
            "--baseline-record-id",
            baseline_record_id,
        ]
    )
    assert exit_code == 0

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0002"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["stage_evaluation"]["decision"] == "passed"
    assert summary["stage_evaluation"]["baseline_comparison"]["decision"] == "improved"
    assert (
        summary["stage_evaluation"]["baseline_comparison"]["comparison_mode"]
        == "task_delta"
    )
    assert summary["stage_evaluation"]["baseline_comparison"]["matched_task_ids"] == [
        "task-1",
        "task-2",
    ]


def test_run_iteration_can_gate_on_task_regressions(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    baseline_config_path = tmp_path / "baseline_task_gate.yaml"
    baseline_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "baseline-task-gate",
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        "print(json.dumps({"
                        "'pass_rate': 1.0, "
                        "'tasks': ["
                        "{'task_id': 'task-1', 'score': 1.0, 'tier': 'critical'}, "
                        "{'task_id': 'task-2', 'score': 0.2, 'tier': 'critical'}, "
                        "{'task_id': 'task-3', 'score': 0.2, 'tier': 'edge'}"
                        "]"
                        "}))"
                    ),
                ],
                "metrics_parser": {"format": "json_stdout", "include": ["pass_rate"]},
                "task_results_parser": {
                    "format": "json_stdout",
                    "key_path": ["tasks"],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(baseline_config_path),
            "--hypothesis",
            "Create a baseline with strong coverage on task-1",
            "--root",
            str(workspaces_root),
            "--stage",
            "screening",
        ]
    )
    assert exit_code == 0

    registry_dir = workspaces_root / "demo" / "tracks" / "main" / "registry"
    baseline_record_id = sorted(registry_dir.glob("*.json"))[0].stem

    candidate_config_path = tmp_path / "candidate_task_gate.yaml"
    candidate_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "candidate-task-gate",
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        "print(json.dumps({"
                        "'pass_rate': 1.0, "
                        "'tasks': ["
                        "{'task_id': 'task-1', 'score': 0.9, 'tier': 'critical', 'owner': 'agent-a'}, "
                        "{'task_id': 'task-2', 'score': 1.0, 'tier': 'critical'}, "
                        "{'task_id': 'task-3', 'score': 1.0, 'tier': 'edge'}"
                        "]"
                        "}))"
                    ),
                ],
                "metrics_parser": {"format": "json_stdout", "include": ["pass_rate"]},
                "task_results_parser": {
                    "format": "json_stdout",
                    "key_path": ["tasks"],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(candidate_config_path),
            "--hypothesis",
            "Improve the mean while avoiding per-task regressions",
            "--root",
            str(workspaces_root),
            "--stage",
            "screening",
            "--baseline-record-id",
            baseline_record_id,
            "--max-regressed-tasks",
            "0",
        ]
    )
    assert exit_code == 0

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0002"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["stage_evaluation"]["decision"] == "failed"
    assert summary["stage_evaluation"]["baseline_comparison"]["decision"] == "regressed"
    assert summary["stage_evaluation"]["baseline_comparison"]["regressed_task_ids"] == [
        "task-1"
    ]
    assert (
        summary["stage_evaluation"]["baseline_comparison"]["regressed_tasks"][0][
            "candidate_task_result"
        ]["owner"]
        == "agent-a"
    )


def test_run_iteration_can_gate_on_weighted_case_regressions(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    baseline_config_path = tmp_path / "baseline_weighted_case_gate.yaml"
    baseline_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "baseline-weighted-case-gate",
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        "print(json.dumps({"
                        "'pass_rate': 1.0, "
                        "'tasks': ["
                        "{'task_id': 'task-1', 'case_id': 'case-a', 'score': 1.0, 'tier': 'critical'}, "
                        "{'task_id': 'task-2', 'case_id': 'case-b', 'score': 0.2, 'tier': 'edge'}, "
                        "{'task_id': 'task-3', 'case_id': 'case-c', 'score': 0.2, 'tier': 'edge'}"
                        "]"
                        "}))"
                    ),
                ],
                "metrics_parser": {"format": "json_stdout", "include": ["pass_rate"]},
                "task_results_parser": {
                    "format": "json_stdout",
                    "key_path": ["tasks"],
                    "match_key_field": "case_id",
                    "tier_field": "tier",
                    "tier_weights": {"critical": 5.0, "edge": 1.0},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(baseline_config_path),
            "--hypothesis",
            "Create a weighted-case baseline",
            "--root",
            str(workspaces_root),
            "--stage",
            "screening",
        ]
    )
    assert exit_code == 0

    registry_dir = workspaces_root / "demo" / "tracks" / "main" / "registry"
    baseline_record_id = sorted(registry_dir.glob("*.json"))[0].stem

    candidate_config_path = tmp_path / "candidate_weighted_case_gate.yaml"
    candidate_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "candidate-weighted-case-gate",
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        "print(json.dumps({"
                        "'pass_rate': 1.0, "
                        "'tasks': ["
                        "{'task_id': 'task-1', 'case_id': 'case-a', 'score': 0.9, 'tier': 'critical', 'owner': 'agent-a'}, "
                        "{'task_id': 'task-2', 'case_id': 'case-b', 'score': 1.0, 'tier': 'edge'}, "
                        "{'task_id': 'task-3', 'case_id': 'case-c', 'score': 1.0, 'tier': 'edge'}"
                        "]"
                        "}))"
                    ),
                ],
                "metrics_parser": {"format": "json_stdout", "include": ["pass_rate"]},
                "task_results_parser": {
                    "format": "json_stdout",
                    "key_path": ["tasks"],
                    "match_key_field": "case_id",
                    "tier_field": "tier",
                    "tier_weights": {"critical": 5.0, "edge": 1.0},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(candidate_config_path),
            "--hypothesis",
            "Improve the mean while protecting weighted critical cases",
            "--root",
            str(workspaces_root),
            "--stage",
            "screening",
            "--baseline-record-id",
            baseline_record_id,
            "--max-regressed-task-weight-fraction",
            "0.4",
        ]
    )
    assert exit_code == 0

    summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0002"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["stage_evaluation"]["decision"] == "failed"
    assert summary["stage_evaluation"]["baseline_comparison"]["decision"] == "regressed"
    assert (
        summary["stage_evaluation"]["baseline_comparison"]["task_alignment_key"]
        == "case_id"
    )
    assert summary["stage_evaluation"]["baseline_comparison"]["regressed_task_ids"] == [
        "case-a"
    ]
    assert (
        round(
            summary["stage_evaluation"]["baseline_comparison"][
                "regressed_task_weight_fraction"
            ],
            3,
        )
        == 0.714
    )


def test_promote_replays_recorded_candidate_and_marks_champion(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    candidate_root = tmp_path / "candidate-target"
    candidate_root.mkdir()
    candidate_file = candidate_root / "src" / "agent.py"
    candidate_file.parent.mkdir(parents=True)
    candidate_file.write_text("STATE = 'old'\n", encoding="utf-8")

    promoted_root = tmp_path / "promoted-target"
    promoted_root.mkdir()
    promoted_file = promoted_root / "src" / "agent.py"
    promoted_file.parent.mkdir(parents=True)
    promoted_file.write_text("STATE = 'old'\n", encoding="utf-8")

    main(
        [
            "setup",
            "--output",
            str(settings),
            "--autonomy",
            "bounded",
            "--editable-surface",
            "src",
        ]
    )
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; from pathlib import Path; "
                        "Path('metrics.json').write_text("
                        "json.dumps({'pass_rate': 1.0}), encoding='utf-8'"
                        "); print('ok')"
                    ),
                ],
                "metrics_parser": {
                    "format": "json_file",
                    "path": str(tmp_path / "metrics.json"),
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "search_replace",
                        "path": "src/agent.py",
                        "search": "old",
                        "replace": "new",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--hypothesis",
            "Generate a recorded candidate",
            "--root",
            str(workspaces_root),
            "--edit-plan",
            str(edit_plan_path),
            "--target-root",
            str(candidate_root),
        ]
    )
    assert exit_code == 0
    assert candidate_file.read_text(encoding="utf-8") == "STATE = 'old'\n"

    registry_dir = workspaces_root / "demo" / "tracks" / "main" / "registry"
    records = sorted(registry_dir.glob("*.json"))
    record_id = records[0].stem

    exit_code = main(
        [
            "promote",
            "--workspace-id",
            "demo",
            "--record-id",
            record_id,
            "--root",
            str(workspaces_root),
            "--target-root",
            str(promoted_root),
        ]
    )
    assert exit_code == 0
    assert promoted_file.read_text(encoding="utf-8") == "STATE = 'new'\n"

    state = json.loads(
        (workspaces_root / "demo" / "state.json").read_text(encoding="utf-8")
    )
    assert state["current_champion_experiment_id"] == record_id

    promotions_dir = workspaces_root / "demo" / "tracks" / "main" / "promotions"
    promotion_records = sorted(promotions_dir.glob("promote_*.json"))
    assert len(promotion_records) == 2
    promotion_json_paths = [
        path for path in promotion_records if not path.name.endswith(".parsed_artifact_sources.json")
    ]
    assert len(promotion_json_paths) == 1
    promotion_payload = json.loads(
        promotion_json_paths[0].read_text(encoding="utf-8")
    )
    assert promotion_payload["record_id"] == record_id
    assert promotion_payload["edit_restore"]["status"] == "kept"
    assert promotion_payload["parsed_artifact_sources"] == {
        "metrics": [
            {
                "origin": "metrics_parser.path",
                "path": str((tmp_path / "metrics.json").resolve()),
                "validation_indices": [1],
            }
        ]
    }

    parsed_artifact_sources_files = sorted(
        promotions_dir.glob("*.parsed_artifact_sources.json")
    )
    assert len(parsed_artifact_sources_files) == 1
    assert json.loads(
        parsed_artifact_sources_files[0].read_text(encoding="utf-8")
    ) == promotion_payload["parsed_artifact_sources"]

    patch_files = sorted(promotions_dir.glob("*.patch"))
    assert len(patch_files) == 1
    patch_text = patch_files[0].read_text(encoding="utf-8")
    assert "--- a/src/agent.py" in patch_text

    champion_manifest_path = (
        workspaces_root / "demo" / "tracks" / "main" / "champion.json"
    )
    champion_manifest = json.loads(champion_manifest_path.read_text(encoding="utf-8"))
    assert champion_manifest["record_id"] == record_id
    assert champion_manifest["promotion_id"] == promotion_payload["promotion_id"]
    assert champion_manifest["promotion_path"] == str(promotion_json_paths[0])
    assert champion_manifest["diff_path"] == str(patch_files[0])
    assert (
        champion_manifest["parsed_artifact_sources_path"]
        == str(parsed_artifact_sources_files[0])
    )
    assert champion_manifest["parsed_artifact_sources"] == promotion_payload[
        "parsed_artifact_sources"
    ]


def test_show_and_export_champion_follow_active_track_manifest(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    candidate_root = tmp_path / "candidate-target"
    candidate_root.mkdir()
    candidate_file = candidate_root / "src" / "agent.py"
    candidate_file.parent.mkdir(parents=True)
    candidate_file.write_text("STATE = 'old'\n", encoding="utf-8")

    promoted_root = tmp_path / "promoted-target"
    promoted_root.mkdir()
    promoted_file = promoted_root / "src" / "agent.py"
    promoted_file.parent.mkdir(parents=True)
    promoted_file.write_text("STATE = 'old'\n", encoding="utf-8")

    main(
        [
            "setup",
            "--output",
            str(settings),
            "--autonomy",
            "bounded",
            "--editable-surface",
            "src",
        ]
    )
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; from pathlib import Path; "
                        "Path('metrics.json').write_text("
                        "json.dumps({'pass_rate': 1.0}), encoding='utf-8'"
                        "); print('ok')"
                    ),
                ],
                "metrics_parser": {
                    "format": "json_file",
                    "path": str(tmp_path / "metrics.json"),
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "search_replace",
                        "path": "src/agent.py",
                        "search": "old",
                        "replace": "new",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    plan_path = tmp_path / "planned_champion_iteration.json"
    assert (
        main(
            [
                "plan-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Generate a promoted champion",
                "--root",
                str(workspaces_root),
                "--output",
                str(plan_path),
            ]
        )
        == 0
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--hypothesis",
                "Generate a promoted champion",
                "--root",
                str(workspaces_root),
                "--edit-plan",
                str(edit_plan_path),
                "--target-root",
                str(candidate_root),
                "--source-plan-path",
                str(plan_path),
            ]
        )
        == 0
    )
    registry_dir = workspaces_root / "demo" / "tracks" / "main" / "registry"
    record_id = sorted(registry_dir.glob("*.json"))[0].stem

    assert (
        main(
            [
                "promote",
                "--workspace-id",
                "demo",
                "--record-id",
                record_id,
                "--root",
                str(workspaces_root),
                "--target-root",
                str(promoted_root),
            ]
        )
        == 0
    )
    assert promoted_file.read_text(encoding="utf-8") == "STATE = 'new'\n"

    capsys.readouterr()

    show_output_path = tmp_path / "shown_champion.json"
    assert (
        main(
            [
                "show-champion",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(show_output_path),
            ]
        )
        == 0
    )
    show_stdout = capsys.readouterr().out
    shown_manifest = json.loads(show_stdout)
    assert shown_manifest["record_id"] == record_id
    assert shown_manifest["source_plan_artifact_path"] == str(
        workspaces_root / "demo" / "iterations" / "iter_0001" / "source_plan.json"
    )
    assert shown_manifest["source_plan"] == json.loads(plan_path.read_text(encoding="utf-8"))
    assert json.loads(show_output_path.read_text(encoding="utf-8")) == shown_manifest

    capsys.readouterr()
    assert (
        main(
            [
                "show-champion",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    champion_text_output = capsys.readouterr().out
    assert (
        "Source plan artifact: "
        f"{workspaces_root / 'demo' / 'iterations' / 'iter_0001' / 'source_plan.json'}"
        in champion_text_output
    )

    track_artifacts_output_path = tmp_path / "track_artifacts.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-track-artifacts",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(track_artifacts_output_path),
            ]
        )
        == 0
    )
    rendered_track_artifacts = json.loads(capsys.readouterr().out)
    assert json.loads(track_artifacts_output_path.read_text(encoding="utf-8")) == rendered_track_artifacts
    assert rendered_track_artifacts["source_plan_artifacts"] == [
        {
            "record_id": record_id,
            "iteration_id": "iter_0001",
            "path": str(workspaces_root / "demo" / "iterations" / "iter_0001" / "source_plan.json"),
            "current_champion": True,
        }
    ]
    assert rendered_track_artifacts["registry_records"] == [
        {
            "record_id": record_id,
            "path": str(workspaces_root / "demo" / "tracks" / "main" / "registry" / f"{record_id}.json"),
            "iteration_id": "iter_0001",
            "source_plan_artifact_path": str(
                workspaces_root / "demo" / "iterations" / "iter_0001" / "source_plan.json"
            ),
        }
    ]
    assert rendered_track_artifacts["champion_artifacts"]["source_plan_artifact_path"] == str(
        workspaces_root / "demo" / "iterations" / "iter_0001" / "source_plan.json"
    )

    capsys.readouterr()
    assert (
        main(
            [
                "show-track-artifacts",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    track_artifacts_text_output = capsys.readouterr().out
    assert "Planned run artifacts: 1" in track_artifacts_text_output
    assert (
        "Champion source plan: "
        f"{workspaces_root / 'demo' / 'iterations' / 'iter_0001' / 'source_plan.json'}"
        in track_artifacts_text_output
    )

    export_dir = tmp_path / "champion-export"
    assert (
        main(
            [
                "export-champion",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(export_dir),
            ]
        )
        == 0
    )

    export_manifest = json.loads((export_dir / "champion.json").read_text(encoding="utf-8"))
    assert export_manifest["record_id"] == record_id
    assert export_manifest["bundle_artifacts"] == {
        "source_champion_manifest_path": "source_champion.json",
        "benchmark_record_path": "benchmark_record.json",
        "promotion_path": "promotion.json",
        "diff_path": "candidate.patch",
        "parsed_artifact_sources_path": "parsed_artifact_sources.json",
        "source_plan_artifact_path": "source_plan.json",
    }
    assert (export_dir / "source_champion.json").exists()
    assert (export_dir / "benchmark_record.json").exists()
    assert (export_dir / "promotion.json").exists()
    assert (export_dir / "candidate.patch").exists()
    assert (export_dir / "parsed_artifact_sources.json").exists()
    assert (export_dir / "source_plan.json").exists()
    assert json.loads((export_dir / "source_plan.json").read_text(encoding="utf-8")) == json.loads(
        plan_path.read_text(encoding="utf-8")
    )
    assert export_manifest["source_artifacts"]["source_plan_artifact_path"] == str(
        workspaces_root / "demo" / "iterations" / "iter_0001" / "source_plan.json"
    )

    source_champion_manifest = json.loads(
        (export_dir / "source_champion.json").read_text(encoding="utf-8")
    )
    assert source_champion_manifest == {
        key: value for key, value in shown_manifest.items() if key in source_champion_manifest
    }


def test_compare_to_champion_recomputes_baseline_against_active_manifest(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    candidate_root = tmp_path / "candidate-target"
    candidate_root.mkdir()
    candidate_file = candidate_root / "src" / "agent.py"
    candidate_file.parent.mkdir(parents=True)
    candidate_file.write_text("STATE = 'old'\n", encoding="utf-8")

    promoted_root = tmp_path / "promoted-target"
    promoted_root.mkdir()
    promoted_file = promoted_root / "src" / "agent.py"
    promoted_file.parent.mkdir(parents=True)
    promoted_file.write_text("STATE = 'old'\n", encoding="utf-8")

    main(
        [
            "setup",
            "--output",
            str(settings),
            "--autonomy",
            "bounded",
            "--editable-surface",
            "src",
        ]
    )
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    champion_config_path = tmp_path / "champion.yaml"
    champion_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "command": [sys.executable, "-c", "import json; print(json.dumps({'pass_rate': 0.0}))"],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "search_replace",
                        "path": "src/agent.py",
                        "search": "old",
                        "replace": "new",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(champion_config_path),
                "--hypothesis",
                "Generate a weak champion candidate",
                "--root",
                str(workspaces_root),
                "--edit-plan",
                str(edit_plan_path),
                "--target-root",
                str(candidate_root),
            ]
        )
        == 0
    )
    champion_record_id = sorted(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )[0].stem
    assert (
        main(
            [
                "promote",
                "--workspace-id",
                "demo",
                "--record-id",
                champion_record_id,
                "--root",
                str(workspaces_root),
                "--target-root",
                str(promoted_root),
            ]
        )
        == 0
    )
    assert promoted_file.read_text(encoding="utf-8") == "STATE = 'new'\n"

    candidate_config_path = tmp_path / "candidate.yaml"
    candidate_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "command": [sys.executable, "-c", "import json; print(json.dumps({'pass_rate': 1.0}))"],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "run-benchmark",
                "--adapter",
                "generic_command",
                "--config",
                str(candidate_config_path),
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--hypothesis",
                "Stronger candidate than the champion",
            ]
        )
        == 0
    )
    registry_records = sorted(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )
    candidate_record_id = [path.stem for path in registry_records if path.stem != champion_record_id][0]

    capsys.readouterr()
    compare_output_path = tmp_path / "compare.json"
    assert (
        main(
            [
                "compare-to-champion",
                "--record-id",
                candidate_record_id,
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(compare_output_path),
            ]
        )
        == 0
    )
    compare_stdout = capsys.readouterr().out
    comparison = json.loads(compare_stdout)
    assert comparison["candidate"]["record_id"] == candidate_record_id
    assert comparison["champion"]["record_id"] == champion_record_id
    assert comparison["candidate_is_current_champion"] is False
    assert comparison["benchmark_match"] is True
    assert comparison["stage_match"] is True
    assert comparison["stage_evaluation"]["decision"] == "passed"
    assert comparison["stage_evaluation"]["baseline_comparison"]["decision"] == "improved"
    assert comparison["stage_evaluation"]["baseline_comparison"]["baseline_label"] == champion_record_id
    assert json.loads(compare_output_path.read_text(encoding="utf-8")) == comparison


def test_promote_from_compare_promotes_only_after_successful_comparison(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    candidate_root = tmp_path / "candidate-target"
    candidate_root.mkdir()
    candidate_file = candidate_root / "src" / "agent.py"
    candidate_file.parent.mkdir(parents=True)
    candidate_file.write_text("STATE = 'old'\n", encoding="utf-8")

    champion_target_root = tmp_path / "promoted-target"
    champion_target_root.mkdir()
    champion_target_file = champion_target_root / "src" / "agent.py"
    champion_target_file.parent.mkdir(parents=True)
    champion_target_file.write_text("STATE = 'old'\n", encoding="utf-8")

    next_target_root = tmp_path / "next-promoted-target"
    next_target_root.mkdir()
    next_target_file = next_target_root / "src" / "agent.py"
    next_target_file.parent.mkdir(parents=True)
    next_target_file.write_text("STATE = 'old'\n", encoding="utf-8")

    main(
        [
            "setup",
            "--output",
            str(settings),
            "--autonomy",
            "bounded",
            "--editable-surface",
            "src",
        ]
    )
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    weak_config_path = tmp_path / "weak.yaml"
    weak_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "command": [sys.executable, "-c", "import json; print(json.dumps({'pass_rate': 0.0}))"],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    strong_config_path = tmp_path / "strong.yaml"
    strong_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "command": [sys.executable, "-c", "import json; print(json.dumps({'pass_rate': 1.0}))"],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "search_replace",
                        "path": "src/agent.py",
                        "search": "old",
                        "replace": "new",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(weak_config_path),
                "--hypothesis",
                "Generate the initial weak champion",
                "--root",
                str(workspaces_root),
                "--edit-plan",
                str(edit_plan_path),
                "--target-root",
                str(candidate_root),
            ]
        )
        == 0
    )
    weak_record_id = sorted(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )[0].stem
    assert (
        main(
            [
                "promote",
                "--workspace-id",
                "demo",
                "--record-id",
                weak_record_id,
                "--root",
                str(workspaces_root),
                "--target-root",
                str(champion_target_root),
            ]
        )
        == 0
    )
    assert champion_target_file.read_text(encoding="utf-8") == "STATE = 'new'\n"

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(strong_config_path),
                "--hypothesis",
                "Generate a stronger candidate",
                "--root",
                str(workspaces_root),
                "--edit-plan",
                str(edit_plan_path),
                "--target-root",
                str(candidate_root),
            ]
        )
        == 0
    )
    registry_records = sorted(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )
    strong_record_id = [path.stem for path in registry_records if path.stem != weak_record_id][0]

    promote_output_path = tmp_path / "promote_from_compare.json"
    assert (
        main(
            [
                "promote-from-compare",
                "--record-id",
                strong_record_id,
                "--root",
                str(workspaces_root),
                "--target-root",
                str(next_target_root),
                "--output",
                str(promote_output_path),
            ]
        )
        == 0
    )
    assert next_target_file.read_text(encoding="utf-8") == "STATE = 'new'\n"

    promoted = json.loads(promote_output_path.read_text(encoding="utf-8"))
    assert promoted["comparison"]["candidate"]["record_id"] == strong_record_id
    assert promoted["comparison"]["champion"]["record_id"] == weak_record_id
    assert promoted["comparison"]["stage_evaluation"]["decision"] == "passed"
    assert (
        promoted["comparison"]["stage_evaluation"]["baseline_comparison"]["decision"]
        == "improved"
    )
    assert promoted["current_champion_experiment_id"] == strong_record_id

    state = json.loads((workspaces_root / "demo" / "state.json").read_text(encoding="utf-8"))
    assert state["current_champion_experiment_id"] == strong_record_id

    champion_manifest = json.loads(
        (
            workspaces_root / "demo" / "tracks" / "main" / "champion.json"
        ).read_text(encoding="utf-8")
    )
    assert champion_manifest["record_id"] == strong_record_id


def test_promote_from_compare_refuses_when_candidate_does_not_beat_champion(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    candidate_root = tmp_path / "candidate-target"
    candidate_root.mkdir()
    candidate_file = candidate_root / "src" / "agent.py"
    candidate_file.parent.mkdir(parents=True)
    candidate_file.write_text("STATE = 'old'\n", encoding="utf-8")

    champion_target_root = tmp_path / "promoted-target"
    champion_target_root.mkdir()
    champion_target_file = champion_target_root / "src" / "agent.py"
    champion_target_file.parent.mkdir(parents=True)
    champion_target_file.write_text("STATE = 'old'\n", encoding="utf-8")

    rejected_target_root = tmp_path / "rejected-target"
    rejected_target_root.mkdir()
    rejected_target_file = rejected_target_root / "src" / "agent.py"
    rejected_target_file.parent.mkdir(parents=True)
    rejected_target_file.write_text("STATE = 'old'\n", encoding="utf-8")

    main(
        [
            "setup",
            "--output",
            str(settings),
            "--autonomy",
            "bounded",
            "--editable-surface",
            "src",
        ]
    )
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    strong_config_path = tmp_path / "strong.yaml"
    strong_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "command": [sys.executable, "-c", "import json; print(json.dumps({'pass_rate': 1.0}))"],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    weak_config_path = tmp_path / "weak.yaml"
    weak_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "command": [sys.executable, "-c", "import json; print(json.dumps({'pass_rate': 0.0}))"],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "search_replace",
                        "path": "src/agent.py",
                        "search": "old",
                        "replace": "new",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(strong_config_path),
                "--hypothesis",
                "Generate the initial strong champion",
                "--root",
                str(workspaces_root),
                "--edit-plan",
                str(edit_plan_path),
                "--target-root",
                str(candidate_root),
            ]
        )
        == 0
    )
    strong_record_id = sorted(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )[0].stem
    assert (
        main(
            [
                "promote",
                "--workspace-id",
                "demo",
                "--record-id",
                strong_record_id,
                "--root",
                str(workspaces_root),
                "--target-root",
                str(champion_target_root),
            ]
        )
        == 0
    )
    assert champion_target_file.read_text(encoding="utf-8") == "STATE = 'new'\n"

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(weak_config_path),
                "--hypothesis",
                "Generate a weaker candidate",
                "--root",
                str(workspaces_root),
                "--edit-plan",
                str(edit_plan_path),
                "--target-root",
                str(candidate_root),
            ]
        )
        == 0
    )
    registry_records = sorted(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )
    weak_record_id = [path.stem for path in registry_records if path.stem != strong_record_id][0]

    with pytest.raises(SystemExit, match="did not pass the comparison stage gate"):
        main(
            [
                "promote-from-compare",
                "--workspace-id",
                "demo",
                "--record-id",
                weak_record_id,
                "--root",
                str(workspaces_root),
                "--target-root",
                str(rejected_target_root),
            ]
        )

    assert rejected_target_file.read_text(encoding="utf-8") == "STATE = 'old'\n"
    state = json.loads((workspaces_root / "demo" / "state.json").read_text(encoding="utf-8"))
    assert state["current_champion_experiment_id"] == strong_record_id


def test_promote_from_compare_uses_track_promotion_policy_defaults(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    candidate_root = tmp_path / "candidate-target"
    candidate_root.mkdir()
    candidate_file = candidate_root / "src" / "agent.py"
    candidate_file.parent.mkdir(parents=True)
    candidate_file.write_text("STATE = 'old'\n", encoding="utf-8")

    champion_target_root = tmp_path / "promoted-target"
    champion_target_root.mkdir()
    champion_target_file = champion_target_root / "src" / "agent.py"
    champion_target_file.parent.mkdir(parents=True)
    champion_target_file.write_text("STATE = 'old'\n", encoding="utf-8")

    next_target_root = tmp_path / "next-promoted-target"
    next_target_root.mkdir()
    next_target_file = next_target_root / "src" / "agent.py"
    next_target_file.parent.mkdir(parents=True)
    next_target_file.write_text("STATE = 'old'\n", encoding="utf-8")

    main(
        [
            "setup",
            "--output",
            str(settings),
            "--autonomy",
            "bounded",
            "--editable-surface",
            "src",
        ]
    )
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    weak_config_path = tmp_path / "weak.yaml"
    weak_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "command": [sys.executable, "-c", "import json; print(json.dumps({'pass_rate': 0.0}))"],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    strong_config_path = tmp_path / "strong.yaml"
    strong_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "command": [sys.executable, "-c", "import json; print(json.dumps({'pass_rate': 1.0}))"],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "search_replace",
                        "path": "src/agent.py",
                        "search": "old",
                        "replace": "new",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(weak_config_path),
                "--hypothesis",
                "Generate the initial weak champion",
                "--root",
                str(workspaces_root),
                "--edit-plan",
                str(edit_plan_path),
                "--target-root",
                str(candidate_root),
            ]
        )
        == 0
    )
    weak_record_id = sorted(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )[0].stem
    assert (
        main(
            [
                "promote",
                "--workspace-id",
                "demo",
                "--record-id",
                weak_record_id,
                "--root",
                str(workspaces_root),
                "--target-root",
                str(champion_target_root),
            ]
        )
        == 0
    )
    assert champion_target_file.read_text(encoding="utf-8") == "STATE = 'new'\n"

    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(strong_config_path),
                "--hypothesis",
                "Generate a stronger candidate",
                "--root",
                str(workspaces_root),
                "--edit-plan",
                str(edit_plan_path),
                "--target-root",
                str(candidate_root),
            ]
        )
        == 0
    )
    registry_records = sorted(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )
    strong_record_id = [path.stem for path in registry_records if path.stem != weak_record_id][0]

    assert (
        main(
            [
                "set-promotion-policy",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--min-improvement",
                "1.1",
            ]
        )
        == 0
    )

    with pytest.raises(SystemExit, match="did not pass the comparison stage gate"):
        main(
            [
                "promote-from-compare",
                "--workspace-id",
                "demo",
                "--record-id",
                strong_record_id,
                "--root",
                str(workspaces_root),
                "--target-root",
                str(next_target_root),
            ]
        )
    assert next_target_file.read_text(encoding="utf-8") == "STATE = 'old'\n"

    promote_output_path = tmp_path / "promote_from_policy_override.json"
    assert (
        main(
            [
                "promote-from-compare",
                "--workspace-id",
                "demo",
                "--record-id",
                strong_record_id,
                "--root",
                str(workspaces_root),
                "--target-root",
                str(next_target_root),
                "--min-improvement",
                "0.0",
                "--output",
                str(promote_output_path),
            ]
        )
        == 0
    )
    assert next_target_file.read_text(encoding="utf-8") == "STATE = 'new'\n"

    promoted = json.loads(promote_output_path.read_text(encoding="utf-8"))
    assert promoted["comparison"]["promotion_policy"]["min_improvement"] == 1.1
    assert promoted["comparison"]["stage_evaluation"]["baseline_comparison"]["decision"] == "improved"
    assert promoted["current_champion_experiment_id"] == strong_record_id
