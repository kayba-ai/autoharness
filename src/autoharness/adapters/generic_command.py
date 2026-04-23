"""Generic command adapter."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from .base import (
    AdapterStagingProfile,
    BenchmarkInvocation,
    CommandAdapterBase,
    normalize_command,
    normalize_mapping,
    normalize_workdir,
)


class GenericCommandAdapter(CommandAdapterBase):
    """Execute any stable benchmark command behind a normalized interface."""

    adapter_id = "generic_command"
    required_config_fields = ("command",)
    config_constraints = (
        "`command` must be a non-empty command list.",
    )

    def staging_profile(self) -> AdapterStagingProfile:
        return AdapterStagingProfile(
            default_mode="copy",
            default_workdir=True,
            target_path_fields=("workdir",),
        )

    def validate_config(self, config: dict[str, Any]) -> None:
        normalize_command(config.get("command"))
        normalize_mapping(config.get("env"), field_name="env")
        normalize_workdir(config.get("workdir"))

    def starter_preset_configs(self) -> dict[str, dict[str, Any]]:
        base_command = ["python", "-c", "print('replace me')"]
        return {
            "default": {
                "benchmark_name": "example-command",
                "workdir": ".",
                "command": base_command,
            },
            "search": {
                "benchmark_name": "search-command",
                "workdir": ".",
                "command": base_command,
                "timeout_seconds": 300,
            },
            "promotion": {
                "benchmark_name": "promotion-command",
                "workdir": ".",
                "command": base_command,
                "timeout_seconds": 1800,
            },
        }

    def build_invocation(self, config: dict[str, Any]) -> BenchmarkInvocation:
        command = normalize_command(config["command"])
        benchmark_name = str(config.get("benchmark_name") or self.adapter_id)
        timeout_seconds = config.get("timeout_seconds")
        if timeout_seconds is not None and not isinstance(timeout_seconds, (int, float)):
            raise ValueError("`timeout_seconds` must be numeric when provided.")

        expected_exit_codes = config.get("expected_exit_codes", [0])
        if not isinstance(expected_exit_codes, list) or not expected_exit_codes:
            raise ValueError("`expected_exit_codes` must be a non-empty list of ints.")
        normalized_exit_codes: list[int] = []
        for code in expected_exit_codes:
            if not isinstance(code, int):
                raise ValueError("`expected_exit_codes` entries must be integers.")
            normalized_exit_codes.append(code)

        return BenchmarkInvocation(
            benchmark_name=benchmark_name,
            command=command,
            workdir=normalize_workdir(config.get("workdir")),
            env_overrides=normalize_mapping(config.get("env"), field_name="env"),
            timeout_seconds=float(timeout_seconds) if timeout_seconds is not None else None,
            expected_exit_codes=tuple(normalized_exit_codes),
        )
