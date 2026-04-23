from pathlib import Path

import json

from autoharness import BenchmarkRunResult, get_adapter


def test_harbor_adapter_builds_expected_registered_dataset_command() -> None:
    adapter = get_adapter("harbor")
    invocation = adapter.build_invocation(
        {
            "dataset": "terminal-bench/terminal-bench-2",
            "model": "openai/gpt-4.1",
            "agent": "codex-cli",
            "num_trials": 8,
            "sandbox_env": "daytona",
        }
    )

    assert invocation.command[:4] == (
        "harbor",
        "run",
        "-d",
        "terminal-bench/terminal-bench-2",
    )
    assert "-m" in invocation.command
    assert "-a" in invocation.command
    assert "--env" in invocation.command
    assert invocation.benchmark_name == "harbor:terminal-bench/terminal-bench-2"


def test_harbor_adapter_builds_expected_local_dataset_command() -> None:
    adapter = get_adapter("harbor")
    invocation = adapter.build_invocation(
        {
            "dataset_path": "datasets/my-local-bench",
            "model": "openai/gpt-4.1",
            "agent_import_path": "my_agent.module:MyAgent",
        }
    )

    assert invocation.command[:4] == (
        "harbor",
        "run",
        "-p",
        "datasets/my-local-bench",
    )
    assert "--agent-import-path" in invocation.command
    assert invocation.benchmark_name == "harbor:datasets/my-local-bench"


def test_harbor_adapter_builds_expected_task_command() -> None:
    adapter = get_adapter("harbor")
    invocation = adapter.build_invocation(
        {
            "task": "terminal-bench/adaptive-rejection-sampler",
            "model": "openai/gpt-4.1",
            "agent": "codex-cli",
        }
    )

    assert invocation.command[:4] == (
        "harbor",
        "run",
        "-t",
        "terminal-bench/adaptive-rejection-sampler",
    )
    assert invocation.benchmark_name == "harbor:terminal-bench/adaptive-rejection-sampler"


def test_harbor_adapter_builds_expected_config_command() -> None:
    adapter = get_adapter("harbor")
    invocation = adapter.build_invocation(
        {
            "config_path": "configs/terminal.yaml",
            "model": "openai/gpt-4.1",
            "agent_import_path": "my_agent.module:MyAgent",
        }
    )

    assert invocation.command[:4] == (
        "harbor",
        "run",
        "-c",
        "configs/terminal.yaml",
    )
    assert invocation.benchmark_name == "harbor_config:configs/terminal.yaml"


def test_harbor_adapter_suggests_staging_for_local_config_path(tmp_path: Path) -> None:
    adapter = get_adapter("harbor")
    source_root = tmp_path / "target"
    source_root.mkdir()

    signal = adapter.suggest_staging(
        {
            "config_path": "configs/terminal.yaml",
            "model": "openai/gpt-4.1",
            "agent": "codex-cli",
        },
        source_root=source_root,
    )

    assert signal is not None
    assert "copy staging is viable" in signal.reason


def test_harbor_adapter_parses_native_artifact_paths(tmp_path: Path) -> None:
    adapter = get_adapter("harbor")
    summary_path = tmp_path / "harbor_summary.json"
    result_path = tmp_path / "harbor_results.json"
    summary_path.write_text(
        json.dumps(
            {
                "summary": {
                    "pass_rate": 0.5,
                    "score": 2.0,
                }
            }
        ),
        encoding="utf-8",
    )
    result_path.write_text(
        json.dumps(
            {
                "task_results": [
                    {"task_id": "task-a", "success": True, "category": "core"},
                    {"task_id": "task-b", "success": False, "category": "edge"},
                ]
            }
        ),
        encoding="utf-8",
    )
    config = {
        "task": "terminal-bench/adaptive-rejection-sampler",
        "model": "openai/gpt-4.1",
        "agent": "codex-cli",
        "summary_json_path": str(summary_path),
        "result_json_path": str(result_path),
    }
    run_result = BenchmarkRunResult(
        adapter_id="harbor",
        benchmark_name="harbor:terminal-bench/adaptive-rejection-sampler",
        command=("harbor", "run"),
        workdir=str(tmp_path),
        exit_code=0,
        success=True,
    )

    metrics, metrics_error = adapter.default_metrics_from_result(
        config,
        result=run_result,
    )
    task_results, task_results_error = adapter.default_task_results_from_result(
        config,
        result=run_result,
        task_identity_profile=adapter.task_identity_profile(config),
    )

    assert metrics_error is None
    assert task_results_error is None
    assert metrics == {"pass_rate": 0.5, "score": 2.0}
    assert task_results == (
        {"task_id": "task-a", "success": True, "category": "core", "score": 1.0},
        {"task_id": "task-b", "success": False, "category": "edge", "score": 0.0},
    )
    assert adapter.parsed_artifact_sources(
        config,
        result=run_result,
    ) == {
        "metrics": [
            {
                "origin": "summary_json_path",
                "path": str(summary_path.resolve()),
            }
        ],
        "task_results": [
            {
                "origin": "result_json_path",
                "path": str(result_path.resolve()),
            }
        ],
    }
