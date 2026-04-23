"""Pytest adapter."""

from __future__ import annotations

from typing import Any

from .base import (
    AdapterStagingProfile,
    BenchmarkInvocation,
    CommandAdapterBase,
    normalize_mapping,
    normalize_workdir,
)


class PytestAdapter(CommandAdapterBase):
    """Build and execute ``pytest`` commands."""

    adapter_id = "pytest"
    config_constraints = (
        "Defaults to `pytest` unless `binary` or `module_mode` changes the runner.",
    )

    def staging_profile(self) -> AdapterStagingProfile:
        return AdapterStagingProfile(
            default_mode="copy",
            default_workdir=True,
            target_path_fields=("workdir",),
            relative_path_fields=("targets",),
        )

    def validate_config(self, config: dict[str, Any]) -> None:
        normalize_workdir(config.get("workdir"))
        normalize_mapping(config.get("env"), field_name="env")

        targets = config.get("targets")
        if targets is not None:
            if not isinstance(targets, list) or not all(
                isinstance(target, str) and target for target in targets
            ):
                raise ValueError("`targets` must be a list of non-empty strings.")

        extra_args = config.get("extra_args")
        if extra_args is not None:
            if not isinstance(extra_args, list) or not all(
                isinstance(arg, str) and arg for arg in extra_args
            ):
                raise ValueError("`extra_args` must be a list of non-empty strings.")

    def starter_preset_configs(self) -> dict[str, dict[str, Any]]:
        return {
            "default": {
                "benchmark_name": "pytest",
                "workdir": ".",
                "targets": ["tests"],
                "extra_args": ["-q"],
            },
            "search": {
                "benchmark_name": "pytest-search",
                "workdir": ".",
                "targets": ["tests"],
                "extra_args": ["-q", "-x"],
            },
            "promotion": {
                "benchmark_name": "pytest-promotion",
                "workdir": ".",
                "targets": ["tests"],
                "extra_args": ["-q"],
            },
        }

    def build_invocation(self, config: dict[str, Any]) -> BenchmarkInvocation:
        self.validate_config(config)
        binary = str(config.get("binary") or "pytest")
        benchmark_name = str(config.get("benchmark_name") or "pytest")
        command: list[str] = [binary]

        if config.get("module_mode"):
            command = ["python", "-m", "pytest"]

        targets = config.get("targets")
        if targets:
            command.extend(targets)

        extra_args = config.get("extra_args")
        if extra_args:
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
