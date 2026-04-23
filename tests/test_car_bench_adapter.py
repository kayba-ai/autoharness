from autoharness import get_adapter


def test_car_bench_adapter_builds_expected_run_command() -> None:
    adapter = get_adapter("car_bench")
    invocation = adapter.build_invocation(
        {
            "model": "gpt-4.1-mini",
            "model_provider": "openai",
            "task_type": "base",
            "task_split": "test",
            "num_tasks": 3,
            "user_model": "gemini-2.5-flash",
            "user_model_provider": "gemini",
            "policy_evaluator_model": "gemini-2.5-flash",
            "policy_evaluator_model_provider": "gemini",
            "thinking": True,
            "user_thinking": True,
            "max_concurrency": 1,
        }
    )

    assert invocation.command[:2] == ("python", "run.py")
    assert "--model" in invocation.command
    assert "--task-type" in invocation.command
    assert "--thinking" in invocation.command
    assert invocation.benchmark_name == "car_bench:base:test"
