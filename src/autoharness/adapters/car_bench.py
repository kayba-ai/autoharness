"""CAR-bench adapter."""

from __future__ import annotations

from typing import Any

from .base import (
    AdapterStagingProfile,
    BenchmarkInvocation,
    CommandAdapterBase,
    normalize_mapping,
    normalize_workdir,
)


class CARBenchAdapter(CommandAdapterBase):
    """Build and execute ``python run.py`` commands for CAR-bench."""

    adapter_id = "car_bench"
    required_config_fields = ("model", "model_provider")
    config_constraints = (
        "`task_type` must be one of `base`, `hallucination`, or `disambiguation` when provided.",
        "`task_split` must be one of `train` or `test` when provided.",
    )

    def starter_preset_configs(self) -> dict[str, dict[str, Any]]:
        base = {
            "model": "gpt-4.1",
            "model_provider": "openai",
            "task_type": "base",
        }
        return {
            "default": {
                **base,
                "task_split": "train",
                "num_tasks": 10,
            },
            "search": {
                **base,
                "task_split": "train",
                "num_tasks": 10,
            },
            "promotion": {
                **base,
                "task_split": "test",
                "num_tasks": 50,
            },
        }

    def staging_profile(self) -> AdapterStagingProfile:
        return AdapterStagingProfile(
            default_mode="copy",
            default_workdir=True,
            target_path_fields=(
                "workdir",
                "script",
                "log_dir",
                "few_shot_displays_path",
            ),
            relative_path_fields=(
                "script",
                "log_dir",
                "few_shot_displays_path",
            ),
        )

    def validate_config(self, config: dict[str, Any]) -> None:
        for field_name in ("model", "model_provider"):
            value = config.get(field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"`{field_name}` is required for car_bench.")

        normalize_workdir(config.get("workdir"))
        normalize_mapping(config.get("env"), field_name="env")

        task_type = config.get("task_type")
        if task_type is not None and task_type not in (
            "base",
            "hallucination",
            "disambiguation",
        ):
            raise ValueError(
                "`task_type` must be one of base, hallucination, disambiguation."
            )

        task_split = config.get("task_split")
        if task_split is not None and task_split not in ("train", "test"):
            raise ValueError("`task_split` must be one of train or test.")

    def build_invocation(self, config: dict[str, Any]) -> BenchmarkInvocation:
        self.validate_config(config)
        binary = str(config.get("binary") or "python")
        script = str(config.get("script") or "run.py")
        task_type = str(config.get("task_type") or "base")
        task_split = str(config.get("task_split") or "train")
        benchmark_name = str(
            config.get("benchmark_name") or f"car_bench:{task_type}:{task_split}"
        )

        command: list[str] = [binary, script]
        scalar_args = {
            "--model": config.get("model"),
            "--model-provider": config.get("model_provider"),
            "--user-model": config.get("user_model"),
            "--user-model-provider": config.get("user_model_provider"),
            "--policy-evaluator-model": config.get("policy_evaluator_model"),
            "--policy-evaluator-model-provider": config.get(
                "policy_evaluator_model_provider"
            ),
            "--task-type": task_type,
            "--task-split": task_split,
            "--num-tasks": config.get("num_tasks"),
            "--log-dir": config.get("log_dir"),
            "--max-concurrency": config.get("max_concurrency"),
            "--seed": config.get("seed"),
            "--shuffle": config.get("shuffle"),
            "--user-strategy": config.get("user_strategy"),
            "--policy-evaluator-strategy": config.get("policy_evaluator_strategy"),
            "--few-shot-displays-path": config.get("few_shot_displays_path"),
            "--temperature": config.get("temperature"),
            "--reasoning-effort": config.get("reasoning_effort"),
            "--num-trials": config.get("num_trials"),
        }
        for flag, value in scalar_args.items():
            if value is None:
                continue
            command.extend([flag, str(value)])

        task_id_filter = config.get("task_id_filter")
        if task_id_filter is not None:
            if not isinstance(task_id_filter, list) or not all(
                isinstance(task_id, str) and task_id for task_id in task_id_filter
            ):
                raise ValueError("`task_id_filter` must be a list of non-empty strings.")
            command.append("--task-id-filter")
            command.extend(task_id_filter)

        # run.py mixes action flags and bool-typed options. For the bool options that
        # require explicit values, pass stringified booleans.
        bool_value_args = {
            "--evaluate-policy": config.get("evaluate_policy"),
            "--score-tool-execution-errors": config.get(
                "score_tool_execution_errors"
            ),
            "--score-policy-errors": config.get("score_policy_errors"),
            "--use-user-as-a-tool-tools": config.get("use_user_as_a_tool_tools"),
            "--user-thinking": config.get("user_thinking"),
            "--remove-non-standard-fields-from-tools": config.get(
                "remove_non_standard_fields_from_tools"
            ),
            "--planning-and-thinking-tool": config.get("planning_and_thinking_tool"),
        }
        for flag, value in bool_value_args.items():
            if value is None:
                continue
            if not isinstance(value, bool):
                raise ValueError(f"`{flag}` values must be booleans when provided.")
            command.extend([flag, "True" if value else "False"])

        for flag, key in (
            ("--thinking", "thinking"),
            ("--interleaved-thinking", "interleaved_thinking"),
        ):
            value = config.get(key)
            if value is None:
                continue
            if not isinstance(value, bool):
                raise ValueError(f"`{key}` must be a boolean when provided.")
            if value:
                command.append(flag)

        extra_args = config.get("extra_args")
        if extra_args is not None:
            if not isinstance(extra_args, list) or not all(
                isinstance(part, str) and part for part in extra_args
            ):
                raise ValueError("`extra_args` must be a list of non-empty strings.")
            command.extend(extra_args)

        timeout_seconds = config.get("timeout_seconds")
        if timeout_seconds is not None and not isinstance(timeout_seconds, (int, float)):
            raise ValueError("`timeout_seconds` must be numeric when provided.")

        return BenchmarkInvocation(
            benchmark_name=benchmark_name,
            command=tuple(command),
            workdir=normalize_workdir(config.get("workdir")),
            env_overrides=normalize_mapping(config.get("env"), field_name="env"),
            timeout_seconds=float(timeout_seconds) if timeout_seconds is not None else None,
        )
