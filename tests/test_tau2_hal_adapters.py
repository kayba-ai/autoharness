from pathlib import Path

import json

from autoharness import BenchmarkRunResult, get_adapter


def test_tau2_adapter_builds_expected_run_command() -> None:
    adapter = get_adapter("tau2_bench")
    invocation = adapter.build_invocation(
        {
            "domain": "airline",
            "agent": "llm",
            "agent_llm": "gpt-4.1-mini",
            "task_split_name": "test",
            "task_ids": ["1", "2"],
            "num_trials": 2,
            "seed": 7,
        }
    )

    assert invocation.command[:3] == ("tau2", "run", "--domain")
    assert "--agent" in invocation.command
    assert "--task-ids" in invocation.command
    assert invocation.benchmark_name == "tau2:airline"


def test_hal_adapter_builds_expected_eval_command() -> None:
    adapter = get_adapter("hal")
    invocation = adapter.build_invocation(
        {
            "benchmark": "taubench_airline",
            "agent_dir": "agents/demo",
            "agent_function": "agent.run",
            "agent_name": "Demo Agent",
            "agent_args": {"model": "openai/gpt-4.1"},
            "benchmark_args": {"split": "test"},
            "docker": True,
        }
    )

    assert invocation.command[:3] == ("hal-eval", "--benchmark", "taubench_airline")
    assert "-A" in invocation.command
    assert "-B" in invocation.command
    assert "--docker" in invocation.command
    assert invocation.benchmark_name == "hal:taubench_airline"


def test_hal_adapter_rewrites_nested_pathlike_args_for_stage(tmp_path: Path) -> None:
    adapter = get_adapter("hal")
    source_root = tmp_path / "source"
    staged_root = tmp_path / "stage"
    source_root.mkdir()
    staged_root.mkdir()

    rewritten = adapter.rewrite_config_for_stage(
        {
            "benchmark": "taubench_airline",
            "agent_dir": str(source_root / "agents/demo"),
            "agent_function": "agent.run",
            "agent_name": "Demo Agent",
            "agent_args": {
                "task_path": "data/tasks.jsonl",
                "model_name": "openai/gpt-4.1",
            },
            "benchmark_args": {
                "cache_path": str(source_root / "cache"),
            },
        },
        source_root=source_root,
        staged_root=staged_root,
    )

    assert rewritten["agent_args"]["task_path"] == str(
        (staged_root / "data/tasks.jsonl").resolve()
    )
    assert rewritten["agent_args"]["model_name"] == "openai/gpt-4.1"
    assert rewritten["benchmark_args"]["cache_path"] == str(
        (staged_root / "cache").resolve()
    )


def test_hal_adapter_suggests_staging_for_nested_pathlike_args(tmp_path: Path) -> None:
    adapter = get_adapter("hal")
    source_root = tmp_path / "source"
    source_root.mkdir()

    signal = adapter.suggest_staging(
        {
            "benchmark": "taubench_airline",
            "agent_dir": "/opt/agents/demo",
            "agent_function": "agent.run",
            "agent_name": "Demo Agent",
            "agent_args": {"task_path": "data/tasks.jsonl"},
        },
        source_root=source_root,
    )

    assert signal is not None
    assert "copy staging is viable" in signal.reason


def test_tau2_adapter_rewrites_nested_pathlike_args_for_stage(tmp_path: Path) -> None:
    adapter = get_adapter("tau2_bench")
    source_root = tmp_path / "source"
    staged_root = tmp_path / "stage"
    source_root.mkdir()
    staged_root.mkdir()

    rewritten = adapter.rewrite_config_for_stage(
        {
            "domain": "airline",
            "retrieval_config_kwargs": {
                "cache_dir": "artifacts/cache",
                "model_name": "openai/gpt-4.1",
            },
            "agent_llm_args": {
                "output_path": str(source_root / "runs" / "agent.json"),
            },
        },
        source_root=source_root,
        staged_root=staged_root,
    )

    assert rewritten["retrieval_config_kwargs"]["cache_dir"] == str(
        (staged_root / "artifacts/cache").resolve()
    )
    assert rewritten["retrieval_config_kwargs"]["model_name"] == "openai/gpt-4.1"
    assert rewritten["agent_llm_args"]["output_path"] == str(
        (staged_root / "runs" / "agent.json").resolve()
    )


def test_tau2_adapter_suggests_staging_for_nested_pathlike_args(tmp_path: Path) -> None:
    adapter = get_adapter("tau2_bench")
    source_root = tmp_path / "source"
    source_root.mkdir()

    signal = adapter.suggest_staging(
        {
            "domain": "airline",
            "retrieval_config_kwargs": {"cache_dir": "artifacts/cache"},
        },
        source_root=source_root,
    )

    assert signal is not None
    assert "copy staging is viable" in signal.reason


def test_tau2_adapter_parses_native_results_artifact(tmp_path: Path) -> None:
    adapter = get_adapter("tau2_bench")
    results_path = tmp_path / "data" / "simulations" / "demo-run" / "results.json"
    results_path.parent.mkdir(parents=True)
    results_path.write_text(
        json.dumps(
            {
                "tasks_evaluated": 2,
                "k": 4,
                "metrics": {
                    "pass_1": 0.5,
                    "pass_2": 1.0,
                },
                "results": [
                    {
                        "task_id": "task-1",
                        "domain": "airline",
                        "passed_all": True,
                        "pass_k_values": {"1": 1.0, "2": 1.0, "3": 1.0, "4": 1.0},
                        "trials": [
                            {
                                "task_id": "task-1",
                                "reward": 1.0,
                                "success": True,
                                "steps": 8,
                                "cost": 0.4,
                                "error": None,
                            }
                        ],
                    },
                    {
                        "task_id": "task-2",
                        "domain": "airline",
                        "passed_all": False,
                        "pass_k_values": {"1": 0.0, "2": 1.0, "3": 1.0, "4": 1.0},
                        "trials": [
                            {
                                "task_id": "task-2",
                                "reward": 0.0,
                                "success": False,
                                "steps": 3,
                                "cost": 0.2,
                                "error": "rate limit",
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    run_result = BenchmarkRunResult(
        adapter_id="tau2_bench",
        benchmark_name="tau2:airline",
        command=("tau2", "run"),
        workdir=str(tmp_path),
        exit_code=0,
        success=True,
    )

    metrics, metrics_error = adapter.default_metrics_from_result(
        {"domain": "airline", "save_to": "demo-run"},
        result=run_result,
    )
    task_results, task_results_error = adapter.default_task_results_from_result(
        {"domain": "airline", "save_to": "demo-run"},
        result=run_result,
        task_identity_profile=adapter.task_identity_profile({"domain": "airline"}),
    )

    assert metrics_error is None
    assert task_results_error is None
    assert metrics["pass_1"] == 0.5
    assert metrics["pass_rate"] == 0.5
    assert task_results[0]["score"] == 1.0
    assert task_results[1]["score"] == 0.0
    assert task_results[1]["pass_2"] == 1.0
    assert task_results[1]["error_count"] == 1
    assert adapter.parsed_artifact_sources(
        {"domain": "airline", "save_to": "demo-run"},
        result=run_result,
    ) == {
        "metrics": [
            {
                "origin": "save_to",
                "path": str(results_path.resolve()),
            }
        ],
        "task_results": [
            {
                "origin": "save_to",
                "path": str(results_path.resolve()),
            }
        ],
    }


def test_hal_adapter_parses_native_artifacts_with_task_identity_override(
    tmp_path: Path,
) -> None:
    adapter = get_adapter("hal")
    summary_path = tmp_path / "hal_summary.json"
    result_path = tmp_path / "hal_results.json"
    summary_path.write_text(
        json.dumps(
            {
                "metrics": {"success_rate": 0.75, "score": 3.0},
            }
        ),
        encoding="utf-8",
    )
    result_path.write_text(
        json.dumps(
            {
                "cases": [
                    {"case_id": "case-a", "passed": True, "tier": "critical"},
                    {"case_id": "case-b", "passed": False, "tier": "edge"},
                ]
            }
        ),
        encoding="utf-8",
    )
    config = {
        "benchmark": "taubench_airline",
        "agent_dir": "agents/demo",
        "agent_function": "agent.run",
        "agent_name": "Demo Agent",
        "summary_json_path": str(summary_path),
        "result_json_path": str(result_path),
        "task_identity_profile": {
            "match_key_field": "case_id",
            "tier_field": "tier",
            "tier_weights": {"critical": 5.0, "edge": 1.0},
        },
    }
    run_result = BenchmarkRunResult(
        adapter_id="hal",
        benchmark_name="hal:taubench_airline",
        command=("hal-eval",),
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
    assert metrics["success_rate"] == 0.75
    assert metrics["pass_rate"] == 0.75
    assert task_results == (
        {"case_id": "case-a", "passed": True, "tier": "critical", "task_id": "case-a", "score": 1.0},
        {"case_id": "case-b", "passed": False, "tier": "edge", "task_id": "case-b", "score": 0.0},
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
