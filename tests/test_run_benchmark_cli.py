import json
import sys
from pathlib import Path

import yaml

from autoharness.cli import main


def test_run_benchmark_dry_run_renders_invocation(tmp_path: Path) -> None:
    config_path = tmp_path / "tau.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "domain": "airline",
                "agent": "llm",
                "agent_llm": "gpt-4.1-mini",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "invocation.json"

    exit_code = main(
        [
            "run-benchmark",
            "--adapter",
            "tau2_bench",
            "--config",
            str(config_path),
            "--dry-run",
            "--output",
            str(output_path),
        ]
    )
    assert exit_code == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["benchmark_name"] == "tau2:airline"
    assert payload["command"][:3] == ["tau2", "run", "--domain"]


def test_run_benchmark_uses_workspace_policy_preset_for_stage(tmp_path: Path) -> None:
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
            "promotion",
        ]
    )

    config_path = tmp_path / "hal_override.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "agent_dir": "agents/custom",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "hal_holdout.json"

    assert (
        main(
            [
                "run-benchmark",
                "--adapter",
                "hal",
                "--config",
                str(config_path),
                "--dry-run",
                "--stage",
                "holdout",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
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
    assert payload["stage_evaluation"]["benchmark_target"] == "tau-bench-airline"
    assert payload["stage_evaluation"]["benchmark_preset_target"] == "promotion"
    assert "--docker" in payload["command"]
    assert payload["command"][payload["command"].index("--agent_dir") + 1] == "agents/custom"


def test_run_benchmark_supports_inline_overrides_without_config_when_preset_pinned(
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
            "promotion",
        ]
    )

    output_path = tmp_path / "hal_inline.json"
    assert (
        main(
            [
                "run-benchmark",
                "--adapter",
                "hal",
                "--dry-run",
                "--stage",
                "holdout",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--set",
                "agent_dir=agents/inline",
                "--set",
                "agent_name=Inline Agent",
                "--set",
                "benchmark_args.limit=12",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["config_preset"] == "promotion"
    assert payload["command"][payload["command"].index("--agent_dir") + 1] == "agents/inline"
    assert payload["command"][payload["command"].index("--agent_name") + 1] == "Inline Agent"
    assert "-B" in payload["command"]
    limit_index = payload["command"].index("-B")
    assert "limit=12" in payload["command"][limit_index + 1 :]
    assert "--docker" in payload["command"]


def test_run_benchmark_executes_generic_command(tmp_path: Path) -> None:
    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "smoke",
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "result.json"

    exit_code = main(
        [
            "run-benchmark",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ]
    )
    assert exit_code == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["stdout"].strip() == "ok"


def test_run_benchmark_supports_builtin_preflight_checks(tmp_path: Path) -> None:
    workdir = tmp_path / "candidate"
    workdir.mkdir()
    (workdir / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    benchmark_counter = tmp_path / "benchmark_preflight_counter.txt"

    config_path = tmp_path / "generic_preflight.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "benchmark-preflight",
                "workdir": str(workdir),
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
    output_path = tmp_path / "preflight_result.json"

    exit_code = main(
        [
            "run-benchmark",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--preflight-check",
            "python_compile",
            "--output",
            str(output_path),
        ]
    )
    assert exit_code == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["success"] is False
    assert payload["preflight_failed"] is True
    assert payload["command"] == []
    assert payload["preflight_validation"]["all_passed"] is False
    assert payload["preflight_validation"]["command_count"] == 1
    assert "compileall" in payload["preflight_validation"]["commands"][0]["command"]
    assert not benchmark_counter.exists()


def test_run_benchmark_parses_metrics_from_json_stdout(tmp_path: Path) -> None:
    config_path = tmp_path / "generic_metrics.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "metrics-smoke",
                "command": [
                    sys.executable,
                    "-c",
                    "import json; print(json.dumps({'pass_rate': 0.75, 'score': 3}))",
                ],
                "metrics_parser": {
                    "format": "json_stdout",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "metrics_result.json"

    exit_code = main(
        [
            "run-benchmark",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ]
    )
    assert exit_code == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["metrics"] == {"pass_rate": 0.75, "score": 3}


def test_run_benchmark_records_parsed_artifact_sources_for_json_file_parser(
    tmp_path: Path,
) -> None:
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
    output_path = tmp_path / "metrics_file_result.json"

    exit_code = main(
        [
            "run-benchmark",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--repeat",
            "3",
            "--output",
            str(output_path),
        ]
    )
    assert exit_code == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["parsed_artifact_sources"] == {
        "metrics": [
            {
                "origin": "metrics_parser.path",
                "path": str((tmp_path / "metrics.json").resolve()),
                "validation_indices": [1, 2, 3],
            }
        ]
    }


def test_run_benchmark_parses_task_results_from_json_stdout(tmp_path: Path) -> None:
    config_path = tmp_path / "generic_tasks.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "task-smoke",
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        "print(json.dumps(["
                        "{'task_id': 'task-1', 'success': True, 'category': 'core'}, "
                        "{'task_id': 'task-2', 'success': False, 'category': 'edge'}"
                        "]))"
                    ),
                ],
                "task_results_parser": {
                    "format": "json_stdout",
                    "tier_field": "category",
                    "tier_weights": {"core": 4.0, "edge": 1.0},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "task_result.json"

    exit_code = main(
        [
            "run-benchmark",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ]
    )
    assert exit_code == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["task_results"] == [
        {"task_id": "task-1", "success": True, "category": "core", "score": 1.0},
        {"task_id": "task-2", "success": False, "category": "edge", "score": 0.0},
    ]
    assert payload["task_identity_profile"] == {
        "match_key_field": "task_id",
        "tier_field": "category",
        "weight_field": None,
        "tier_weights": {"core": 4.0, "edge": 1.0},
        "default_weight": 1.0,
    }
    assert payload["task_result_summary"]["task_mean_scores"] == {
        "task-1": 1.0,
        "task-2": 0.0,
    }


def test_run_benchmark_repeats_validation_runs_and_aggregates_metrics(
    tmp_path: Path,
) -> None:
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
    output_path = tmp_path / "repeat_result.json"

    exit_code = main(
        [
            "run-benchmark",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--repeat",
            "3",
            "--output",
            str(output_path),
        ]
    )
    assert exit_code == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["validation_run_count"] == 3
    assert len(payload["validation_runs"]) == 3
    assert payload["validation_summary"]["success_count"] == 3
    assert payload["validation_summary"]["success_rate"] == 1.0
    assert payload["validation_summary"]["success_rate_confidence_interval"]["lower"] > 0.5
    assert payload["metrics"] == {"pass_rate": 1.0, "score": 2.0}
    assert payload["validation_summary"]["metrics_confidence_intervals"]["pass_rate"] == {
        "lower": 1.0,
        "upper": 1.0,
        "confidence_level": 0.85,
        "count": 3,
    }


def test_run_benchmark_repeats_and_aggregates_task_results(tmp_path: Path) -> None:
    config_path = tmp_path / "generic_task_repeat.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "repeat-task-smoke",
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        "print(json.dumps(["
                        "{'task_id': 'task-1', 'score': 1.0}, "
                        "{'task_id': 'task-2', 'score': 0.0}"
                        "]))"
                    ),
                ],
                "task_results_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "repeat_task_result.json"

    exit_code = main(
        [
            "run-benchmark",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--repeat",
            "3",
            "--output",
            str(output_path),
        ]
    )
    assert exit_code == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["validation_summary"]["task_result_summary"]["task_mean_scores"] == {
        "task-1": 1.0,
        "task-2": 0.0,
    }
    assert payload["validation_summary"]["task_result_summary"]["task_observation_counts"] == {
        "task-1": 3,
        "task-2": 3,
    }


def test_run_benchmark_dry_run_repeats_seeded_invocations(tmp_path: Path) -> None:
    config_path = tmp_path / "tau_repeat.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "domain": "airline",
                "agent": "llm",
                "agent_llm": "gpt-4.1-mini",
                "seed": 7,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "tau_repeat_result.json"

    exit_code = main(
        [
            "run-benchmark",
            "--adapter",
            "tau2_bench",
            "--config",
            str(config_path),
            "--dry-run",
            "--repeat",
            "3",
            "--seed-field",
            "seed",
            "--output",
            str(output_path),
        ]
    )
    assert exit_code == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["validation_run_count"] == 3
    assert payload["validation_seeds"] == [7, 8, 9]
    commands = [run["command"] for run in payload["validation_runs"]]
    assert commands[0][-1] == "7"
    assert commands[1][-1] == "8"
    assert commands[2][-1] == "9"


def test_run_benchmark_stage_defaults_and_gate_failure(tmp_path: Path) -> None:
    config_path = tmp_path / "stage_validation.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "stage-validation",
                "command": [
                    sys.executable,
                    "-c",
                    "import json; print(json.dumps({'pass_rate': 0.5}))",
                ],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "stage_validation_result.json"

    exit_code = main(
        [
            "run-benchmark",
            "--adapter",
            "generic_command",
            "--config",
            str(config_path),
            "--stage",
            "validation",
            "--min-success-rate",
            "0.6",
            "--output",
            str(output_path),
        ]
    )
    assert exit_code == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["validation_run_count"] == 3
    assert payload["stage_evaluation"]["decision"] == "failed"
    assert payload["stage_evaluation"]["passed"] is False
    assert payload["stage_evaluation"]["decision_mode"] == "confidence_interval"
