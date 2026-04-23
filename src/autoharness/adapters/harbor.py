"""Harbor adapter."""

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
    normalize_mapping,
    normalize_workdir,
)


class HarborAdapter(CommandAdapterBase):
    """Build and execute ``harbor run`` commands."""

    adapter_id = "harbor"
    required_config_fields = ("model",)
    config_constraints = (
        "Provide exactly one of `dataset`, `dataset_path`, `task`, or `config_path`.",
        "Provide exactly one of `agent` or `agent_import_path`.",
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

    def starter_preset_configs(self) -> dict[str, dict[str, Any]]:
        base = {
            "dataset": "terminal-bench/terminal-bench-2",
            "model": "openai/gpt-4.1",
            "agent": "codex-cli",
        }
        return {
            "default": {
                **base,
                "num_trials": 1,
            },
            "search": {
                **base,
                "num_trials": 1,
                "sandbox_env": "daytona",
            },
            "promotion": {
                **base,
                "num_trials": 5,
            },
            "native-artifact": {
                **base,
                "summary_json_path": "artifacts/harbor_summary.json",
                "result_json_path": "artifacts/harbor_results.json",
            },
        }

    def staging_profile(self) -> AdapterStagingProfile:
        return AdapterStagingProfile(
            default_mode="off",
            default_workdir=False,
            target_path_fields=("workdir", "dataset_path", "registry_path", "config_path"),
            relative_path_fields=("dataset_path", "registry_path", "config_path"),
        )

    def validate_config(self, config: dict[str, Any]) -> None:
        has_dataset = isinstance(config.get("dataset"), str) and bool(config.get("dataset"))
        has_path = isinstance(config.get("dataset_path"), str) and bool(config.get("dataset_path"))
        has_task = isinstance(config.get("task"), str) and bool(config.get("task"))
        has_config = isinstance(config.get("config_path"), str) and bool(config.get("config_path"))
        run_target_count = sum((has_dataset, has_path, has_task, has_config))
        if run_target_count != 1:
            raise ValueError(
                "Provide exactly one of `dataset`, `dataset_path`, `task`, or `config_path` for harbor."
            )

        model = config.get("model")
        if not isinstance(model, str) or not model:
            raise ValueError("`model` is required for harbor.")

        has_agent = isinstance(config.get("agent"), str) and bool(config.get("agent"))
        has_agent_import = isinstance(config.get("agent_import_path"), str) and bool(
            config.get("agent_import_path")
        )
        if has_agent == has_agent_import:
            raise ValueError(
                "Provide exactly one of `agent` or `agent_import_path` for harbor."
            )

        normalize_workdir(config.get("workdir"))
        normalize_mapping(config.get("env"), field_name="env")

    def suggest_staging(
        self,
        config: dict[str, Any],
        *,
        source_root,
    ) -> AdapterStagingSignal | None:
        config_path = config.get("config_path")
        if (
            isinstance(config_path, str)
            and config_path
            and (
                not config_path.startswith("/")
                or str(source_root.resolve()) in config_path
                or config_path in (
                    "{target_root}",
                    "$AUTOHARNESS_TARGET_ROOT",
                    "${AUTOHARNESS_TARGET_ROOT}",
                )
            )
        ):
            return AdapterStagingSignal(
                reason=(
                    "Harbor config_path points at a local benchmark config, so copy staging is viable."
                )
            )
        return None

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
        binary = str(config.get("binary") or "harbor")

        if config.get("dataset"):
            benchmark_name = str(config.get("benchmark_name") or f"harbor:{config['dataset']}")
        elif config.get("task"):
            benchmark_name = str(config.get("benchmark_name") or f"harbor:{config['task']}")
        elif config.get("config_path"):
            benchmark_name = str(
                config.get("benchmark_name") or f"harbor_config:{config['config_path']}"
            )
        else:
            benchmark_name = str(
                config.get("benchmark_name") or f"harbor:{config['dataset_path']}"
            )

        command: list[str] = [binary, "run"]

        if config.get("dataset"):
            command.extend(["-d", str(config["dataset"])])
        elif config.get("task"):
            command.extend(["-t", str(config["task"])])
        elif config.get("config_path"):
            command.extend(["-c", str(config["config_path"])])
        else:
            command.extend(["-p", str(config["dataset_path"])])

        command.extend(["-m", str(config["model"])])

        if config.get("agent"):
            command.extend(["-a", str(config["agent"])])
        else:
            command.extend(["--agent-import-path", str(config["agent_import_path"])])

        scalar_args = {
            "--registry-path": config.get("registry_path"),
            "--registry-url": config.get("registry_url"),
            "--env": config.get("sandbox_env"),
            "-n": config.get("num_trials"),
            "--job-name": config.get("job_name"),
        }
        for flag, value in scalar_args.items():
            if value is None:
                continue
            command.extend([flag, str(value)])

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
