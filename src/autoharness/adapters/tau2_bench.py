"""Tau2 / Tau-Bench adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import (
    AdapterStagingSignal,
    AdapterStagingProfile,
    BenchmarkInvocation,
    CommandAdapterBase,
    TaskIdentityProfile,
    _extract_numeric_metrics_from_payload,
    _load_json_artifact,
    _resolve_artifact_path,
    mapping_has_pathlike_hints,
    normalize_mapping,
    normalize_workdir,
    rewrite_pathlike_mapping,
)


class Tau2BenchAdapter(CommandAdapterBase):
    """Build and execute ``tau2 run`` commands."""

    adapter_id = "tau2_bench"
    required_config_fields = ("domain",)
    config_constraints = (
        "Nested mappings in `agent_llm_args`, `user_llm_args`, "
        "`retrieval_config_kwargs`, and `user_persona` are staging-aware.",
        "`save_to` can be used as a native results locator as well as a staged target path.",
    )
    native_metrics_artifact_fields = (
        "results_json_path",
        "result_json_path",
        "save_to",
    )
    native_task_results_artifact_fields = (
        "results_json_path",
        "result_json_path",
        "save_to",
    )

    def default_task_identity_profile(self) -> TaskIdentityProfile | None:
        return TaskIdentityProfile(
            match_key_field="task_id",
            tier_field="tier",
            tier_weights={
                "critical": 5.0,
                "high": 3.0,
                "medium": 1.0,
                "low": 0.5,
                "edge": 0.25,
            },
            default_weight=1.0,
        )

    def starter_preset_configs(self) -> dict[str, dict[str, Any]]:
        base = {
            "domain": "airline",
            "agent": "llm",
            "agent_llm": "gpt-4.1-mini",
            "task_split_name": "test",
        }
        return {
            "default": {
                **base,
                "num_trials": 1,
                "save_to": "demo-run",
            },
            "search": {
                **base,
                "num_trials": 1,
                "num_tasks": 10,
                "max_concurrency": 4,
                "save_to": "search-run",
            },
            "promotion": {
                **base,
                "num_trials": 3,
                "save_to": "promotion-run",
            },
            "native-artifact": {
                **base,
                "results_json_path": "data/simulations/demo-run/results.json",
            },
        }

    def staging_profile(self) -> AdapterStagingProfile:
        return AdapterStagingProfile(
            default_mode="off",
            default_workdir=False,
            target_path_fields=("workdir", "save_to"),
            relative_path_fields=("save_to",),
        )

    def validate_config(self, config: dict[str, Any]) -> None:
        domain = config.get("domain")
        if not isinstance(domain, str) or not domain:
            raise ValueError("`domain` is required for tau2_bench.")
        workdir = config.get("workdir")
        normalize_workdir(workdir)
        normalize_mapping(config.get("env"), field_name="env")

    def suggest_staging(
        self,
        config: dict[str, Any],
        *,
        source_root,
    ) -> AdapterStagingSignal | None:
        for field_name in (
            "agent_llm_args",
            "user_llm_args",
            "retrieval_config_kwargs",
            "user_persona",
        ):
            value = config.get(field_name)
            if isinstance(value, dict) and mapping_has_pathlike_hints(
                value,
                source_root=source_root,
            ):
                return AdapterStagingSignal(
                    reason=(
                        "Tau2 nested config includes relative or target-root paths, "
                        "so copy staging is viable."
                    )
                )
        return None

    def rewrite_config_for_stage(
        self,
        config: dict[str, Any],
        *,
        source_root,
        staged_root,
    ) -> dict[str, Any]:
        rewritten = dict(config)
        for field_name in (
            "agent_llm_args",
            "user_llm_args",
            "retrieval_config_kwargs",
            "user_persona",
        ):
            value = rewritten.get(field_name)
            if isinstance(value, dict):
                rewritten[field_name] = rewrite_pathlike_mapping(
                    value,
                    source_root=source_root,
                    staged_root=staged_root,
                )
        return rewritten

    def default_metrics_from_result(
        self,
        config: dict[str, Any],
        *,
        result,
    ) -> tuple[dict[str, Any], str | None]:
        payload, parse_error = self._load_results_payload(config, result=result)
        if parse_error is not None:
            return {}, parse_error
        if not isinstance(payload, dict):
            return {}, None

        metrics = _extract_numeric_metrics_from_payload(payload)
        if "pass_rate" not in metrics:
            raw_metrics = payload.get("metrics")
            if isinstance(raw_metrics, dict):
                pass_1 = raw_metrics.get("pass_1")
                if isinstance(pass_1, (int, float)) and not isinstance(pass_1, bool):
                    metrics["pass_rate"] = float(pass_1)

        if "pass_rate" not in metrics:
            results = payload.get("results")
            if isinstance(results, list):
                pass_1_values: list[float] = []
                for entry in results:
                    if not isinstance(entry, dict):
                        continue
                    pass_k_values = entry.get("pass_k_values")
                    if not isinstance(pass_k_values, dict):
                        continue
                    raw_pass_1 = pass_k_values.get("1")
                    if isinstance(raw_pass_1, (int, float)) and not isinstance(
                        raw_pass_1,
                        bool,
                    ):
                        pass_1_values.append(float(raw_pass_1))
                if pass_1_values:
                    metrics["pass_rate"] = sum(pass_1_values) / len(pass_1_values)

        return metrics, None

    def default_task_results_from_result(
        self,
        config: dict[str, Any],
        *,
        result,
        task_identity_profile: TaskIdentityProfile | None,
    ) -> tuple[tuple[dict[str, Any], ...], str | None]:
        payload, parse_error = self._load_results_payload(config, result=result)
        if parse_error is not None:
            return (), parse_error
        if not isinstance(payload, dict):
            return (), None

        raw_results = payload.get("results")
        if raw_results is None:
            return (), None
        if not isinstance(raw_results, list):
            return (), "Tau2 results payload did not contain a `results` list."

        task_results: list[dict[str, Any]] = []
        for entry in raw_results:
            if not isinstance(entry, dict):
                continue
            raw_task_id = entry.get("task_id")
            if raw_task_id is None:
                continue
            task_result: dict[str, Any] = {
                "task_id": str(raw_task_id),
            }
            if task_identity_profile is not None:
                match_key_field = task_identity_profile.match_key_field
                if match_key_field != "task_id":
                    task_result[match_key_field] = str(raw_task_id)
            raw_domain = entry.get("domain")
            if isinstance(raw_domain, str) and raw_domain:
                task_result["domain"] = raw_domain
            raw_passed_all = entry.get("passed_all")
            if isinstance(raw_passed_all, bool):
                task_result["passed_all"] = raw_passed_all

            pass_k_values = entry.get("pass_k_values")
            score: float | None = None
            if isinstance(pass_k_values, dict):
                for pass_k, value in pass_k_values.items():
                    if (
                        not isinstance(pass_k, str)
                        or not isinstance(value, (int, float))
                        or isinstance(value, bool)
                    ):
                        continue
                    task_result[f"pass_{pass_k}"] = float(value)
                raw_pass_1 = pass_k_values.get("1")
                if isinstance(raw_pass_1, (int, float)) and not isinstance(
                    raw_pass_1,
                    bool,
                ):
                    score = float(raw_pass_1)

            trials = entry.get("trials")
            if isinstance(trials, list):
                successful_trials = 0
                rewards: list[float] = []
                costs: list[float] = []
                error_count = 0
                for trial in trials:
                    if not isinstance(trial, dict):
                        continue
                    if trial.get("success") is True:
                        successful_trials += 1
                    reward = trial.get("reward")
                    if isinstance(reward, (int, float)) and not isinstance(reward, bool):
                        rewards.append(float(reward))
                    cost = trial.get("cost")
                    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                        costs.append(float(cost))
                    if isinstance(trial.get("error"), str) and trial["error"]:
                        error_count += 1
                task_result["trial_count"] = len(trials)
                task_result["successful_trials"] = successful_trials
                task_result["error_count"] = error_count
                if rewards:
                    task_result["mean_reward"] = sum(rewards) / len(rewards)
                if costs:
                    task_result["mean_cost"] = sum(costs) / len(costs)
                if score is None and trials:
                    score = successful_trials / len(trials)

            if score is None and isinstance(raw_passed_all, bool):
                score = 1.0 if raw_passed_all else 0.0
            if score is None:
                continue
            task_result["score"] = score
            task_results.append(task_result)

        return tuple(task_results), None

    def parsed_artifact_sources(
        self,
        config: dict[str, Any],
        *,
        result,
    ) -> dict[str, Any]:
        sources = super().parsed_artifact_sources(config, result=result)
        results_path, results_origin = self._resolve_results_path(config, result=result)
        if results_path is None:
            return sources
        descriptor = {
            "origin": results_origin,
            "path": str(results_path),
        }
        sources["metrics"] = [descriptor]
        sources["task_results"] = [descriptor]
        return sources

    def _load_results_payload(
        self,
        config: dict[str, Any],
        *,
        result,
    ) -> tuple[Any | None, str | None]:
        results_path, results_origin = self._resolve_results_path(config, result=result)
        del results_origin
        if results_path is None:
            return None, None
        return _load_json_artifact(
            str(results_path),
            result=result,
            field_name="tau2 results",
        )

    def _resolve_results_path(
        self,
        config: dict[str, Any],
        *,
        result,
    ) -> tuple[Path | None, str | None]:
        explicit_results_path = config.get("results_json_path") or config.get(
            "result_json_path"
        )
        if isinstance(explicit_results_path, str) and explicit_results_path:
            return (
                _resolve_artifact_path(explicit_results_path, result=result),
                "results_json_path",
            )

        raw_save_to = config.get("save_to")
        if not isinstance(raw_save_to, str) or not raw_save_to:
            return None, None

        save_path = Path(raw_save_to)
        if not save_path.is_absolute():
            base_dir = Path(result.workdir) if result.workdir is not None else Path.cwd()
            if save_path.suffix == ".json":
                save_path = base_dir / save_path
            else:
                save_path = base_dir / "data" / "simulations" / save_path / "results.json"
        return save_path.resolve(), "save_to"

    def build_invocation(self, config: dict[str, Any]) -> BenchmarkInvocation:
        self.validate_config(config)
        binary = str(config.get("binary") or "tau2")
        benchmark_name = str(config.get("benchmark_name") or f"tau2:{config['domain']}")

        command: list[str] = [binary, "run", "--domain", str(config["domain"])]
        scalar_args = {
            "--agent": config.get("agent"),
            "--agent-llm": config.get("agent_llm"),
            "--user": config.get("user"),
            "--user-llm": config.get("user_llm"),
            "--task-set-name": config.get("task_set_name"),
            "--task-split-name": config.get("task_split_name"),
            "--num-trials": config.get("num_trials"),
            "--num-tasks": config.get("num_tasks"),
            "--max-steps": config.get("max_steps"),
            "--max-errors": config.get("max_errors"),
            "--timeout": config.get("timeout_seconds"),
            "--save-to": config.get("save_to"),
            "--max-concurrency": config.get("max_concurrency"),
            "--seed": config.get("seed"),
            "--log-level": config.get("log_level"),
        }
        for flag, value in scalar_args.items():
            if value is None:
                continue
            command.extend([flag, str(value)])

        for flag, key in (
            ("--agent-llm-args", "agent_llm_args"),
            ("--user-llm-args", "user_llm_args"),
            ("--retrieval-config-kwargs", "retrieval_config_kwargs"),
            ("--user-persona", "user_persona"),
        ):
            value = config.get(key)
            if value is None:
                continue
            if not isinstance(value, dict):
                raise ValueError(f"`{key}` must be a mapping when provided.")
            command.extend([flag, json.dumps(value)])

        task_ids = config.get("task_ids")
        if task_ids is not None:
            if not isinstance(task_ids, list) or not all(
                isinstance(task_id, str) for task_id in task_ids
            ):
                raise ValueError("`task_ids` must be a list of strings.")
            command.append("--task-ids")
            command.extend(task_ids)

        boolean_flags = {
            "--verbose-logs": config.get("verbose_logs"),
            "--audio-native": config.get("audio_native"),
            "--auto-resume": config.get("auto_resume"),
            "--auto-review": config.get("auto_review"),
            "--enforce-communication-protocol": config.get(
                "enforce_communication_protocol"
            ),
        }
        for flag, enabled in boolean_flags.items():
            if enabled:
                command.append(flag)

        extra_args = config.get("extra_args")
        if extra_args is not None:
            if not isinstance(extra_args, list) or not all(
                isinstance(part, str) and part for part in extra_args
            ):
                raise ValueError("`extra_args` must be a list of non-empty strings.")
            command.extend(extra_args)

        return BenchmarkInvocation(
            benchmark_name=benchmark_name,
            command=tuple(command),
            workdir=normalize_workdir(config.get("workdir")),
            env_overrides=normalize_mapping(config.get("env"), field_name="env"),
            timeout_seconds=(
                float(config["timeout_seconds"])
                if config.get("timeout_seconds") is not None
                else None
            ),
        )
