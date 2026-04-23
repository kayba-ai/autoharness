"""HAL harness adapter."""

from __future__ import annotations

from typing import Any

from .base import (
    AdapterStagingSignal,
    AdapterStagingProfile,
    BenchmarkInvocation,
    CommandAdapterBase,
    TaskIdentityProfile,
    _extract_numeric_metrics_from_payload,
    _extract_task_results_from_payload,
    _load_json_artifact_from_config,
    _resolve_artifact_path,
    mapping_has_pathlike_hints,
    normalize_mapping,
    normalize_workdir,
    rewrite_pathlike_mapping,
)


class HALAdapter(CommandAdapterBase):
    """Build and execute ``hal-eval`` commands."""

    adapter_id = "hal"
    required_config_fields = (
        "benchmark",
        "agent_dir",
        "agent_function",
        "agent_name",
    )
    config_constraints = (
        "Path-like values inside `agent_args`, `benchmark_args`, and `inspect_args` are staging-aware.",
    )
    native_metrics_artifact_fields = (
        "summary_json_path",
        "result_json_path",
        "results_json_path",
        "artifact_json_path",
    )
    native_task_results_artifact_fields = (
        "result_json_path",
        "results_json_path",
        "summary_json_path",
        "artifact_json_path",
    )

    def default_task_identity_profile(self) -> TaskIdentityProfile | None:
        return TaskIdentityProfile(
            match_key_field="task_id",
            tier_field="tier",
            default_weight=1.0,
        )

    def starter_preset_configs(self) -> dict[str, dict[str, Any]]:
        base = {
            "benchmark": "taubench_airline",
            "agent_dir": "agents/demo",
            "agent_function": "agent.run",
            "agent_name": "Demo Agent",
        }
        return {
            "default": {
                **base,
                "benchmark_args": {"split": "test"},
            },
            "search": {
                **base,
                "benchmark_args": {"split": "test", "limit": 10},
            },
            "promotion": {
                **base,
                "benchmark_args": {"split": "test"},
                "docker": True,
            },
            "native-artifact": {
                **base,
                "summary_json_path": "artifacts/hal_summary.json",
                "result_json_path": "artifacts/hal_results.json",
            },
        }

    def staging_profile(self) -> AdapterStagingProfile:
        return AdapterStagingProfile(
            default_mode="off",
            default_workdir=True,
            target_path_fields=("workdir", "agent_dir"),
            relative_path_fields=("agent_dir",),
        )

    def validate_config(self, config: dict[str, Any]) -> None:
        for field_name in ("benchmark", "agent_dir", "agent_function", "agent_name"):
            value = config.get(field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"`{field_name}` is required for hal.")
        normalize_workdir(config.get("workdir"))
        normalize_mapping(config.get("env"), field_name="env")

    def suggest_staging(
        self,
        config: dict[str, Any],
        *,
        source_root,
    ) -> AdapterStagingSignal | None:
        for field_name in ("agent_args", "benchmark_args", "inspect_args"):
            value = config.get(field_name)
            if isinstance(value, dict) and mapping_has_pathlike_hints(
                value,
                source_root=source_root,
            ):
                return AdapterStagingSignal(
                    reason=(
                        "HAL nested config includes relative or target-root paths, "
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
        for field_name in ("agent_args", "benchmark_args", "inspect_args"):
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
        payload, parse_error = _load_json_artifact_from_config(
            config,
            result=result,
            field_names=(
                "summary_json_path",
                "result_json_path",
                "results_json_path",
                "artifact_json_path",
            ),
        )
        if parse_error is not None:
            return {}, parse_error
        if payload is None:
            return {}, None
        return _extract_numeric_metrics_from_payload(payload), None

    def default_task_results_from_result(
        self,
        config: dict[str, Any],
        *,
        result,
        task_identity_profile: TaskIdentityProfile | None,
    ) -> tuple[tuple[dict[str, Any], ...], str | None]:
        payload, parse_error = _load_json_artifact_from_config(
            config,
            result=result,
            field_names=(
                "result_json_path",
                "results_json_path",
                "summary_json_path",
                "artifact_json_path",
            ),
        )
        if parse_error is not None:
            return (), parse_error
        if payload is None:
            return (), None

        task_id_field = (
            task_identity_profile.match_key_field
            if task_identity_profile is not None
            else "task_id"
        )
        return _extract_task_results_from_payload(
            payload,
            task_id_field=task_id_field,
        )

    def parsed_artifact_sources(
        self,
        config: dict[str, Any],
        *,
        result,
    ) -> dict[str, Any]:
        sources = super().parsed_artifact_sources(config, result=result)
        summary_path = self._resolve_native_artifact_path(
            config,
            result=result,
            field_names=("summary_json_path", "result_json_path", "results_json_path", "artifact_json_path"),
        )
        result_path = self._resolve_native_artifact_path(
            config,
            result=result,
            field_names=("result_json_path", "results_json_path", "summary_json_path", "artifact_json_path"),
        )
        if summary_path is not None:
            sources["metrics"] = [summary_path]
        if result_path is not None:
            sources["task_results"] = [result_path]
        return sources

    def _resolve_native_artifact_path(
        self,
        config: dict[str, Any],
        *,
        result,
        field_names: tuple[str, ...],
    ) -> dict[str, str] | None:
        for field_name in field_names:
            raw_path = config.get(field_name)
            if not isinstance(raw_path, str) or not raw_path:
                continue
            return {
                "origin": field_name,
                "path": str(_resolve_artifact_path(raw_path, result=result)),
            }
        return None

    def build_invocation(self, config: dict[str, Any]) -> BenchmarkInvocation:
        self.validate_config(config)
        binary = str(config.get("binary") or "hal-eval")
        benchmark_name = str(config.get("benchmark_name") or f"hal:{config['benchmark']}")

        command: list[str] = [
            binary,
            "--benchmark",
            str(config["benchmark"]),
            "--agent_dir",
            str(config["agent_dir"]),
            "--agent_function",
            str(config["agent_function"]),
            "--agent_name",
            str(config["agent_name"]),
        ]

        scalar_args = {
            "--max_concurrent": config.get("max_concurrent"),
            "--conda_env_name": config.get("conda_env_name"),
            "--run_id": config.get("run_id"),
        }
        for flag, value in scalar_args.items():
            if value is None:
                continue
            command.extend([flag, str(value)])

        for prefix, key in (("-A", "agent_args"), ("-B", "benchmark_args"), ("-I", "inspect_args")):
            value = config.get(key)
            if value is None:
                continue
            if not isinstance(value, dict):
                raise ValueError(f"`{key}` must be a mapping when provided.")
            for arg_name, raw in value.items():
                if not isinstance(arg_name, str) or not arg_name:
                    raise ValueError(f"`{key}` keys must be non-empty strings.")
                command.extend([prefix, f"{arg_name}={raw}"])

        boolean_flags = {
            "--upload": config.get("upload"),
            "--vm": config.get("vm"),
            "--docker": config.get("docker"),
            "--continue_run": config.get("continue_run"),
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
