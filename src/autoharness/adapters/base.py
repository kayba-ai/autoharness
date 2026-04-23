"""Base types and helpers for autoharness benchmark adapters."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Protocol


JsonDict = dict[str, Any]
StagingMode = Literal["off", "copy"]


@dataclass(frozen=True)
class TaskIdentityProfile:
    """How one adapter identifies and weights comparable task outcomes."""

    match_key_field: str = "task_id"
    tier_field: str | None = None
    weight_field: str | None = None
    tier_weights: MappingProxyType[str, float] = field(
        default_factory=lambda: MappingProxyType({})
    )
    default_weight: float = 1.0

    def to_dict(self) -> JsonDict:
        return {
            "match_key_field": self.match_key_field,
            "tier_field": self.tier_field,
            "weight_field": self.weight_field,
            "tier_weights": dict(self.tier_weights),
            "default_weight": self.default_weight,
        }


@dataclass(frozen=True)
class BenchmarkInvocation:
    """A normalized command invocation produced by one adapter."""

    benchmark_name: str
    command: tuple[str, ...]
    workdir: str | None = None
    env_overrides: MappingProxyType[str, str] = field(
        default_factory=lambda: MappingProxyType({})
    )
    timeout_seconds: float | None = None
    expected_exit_codes: tuple[int, ...] = (0,)

    def to_dict(self) -> JsonDict:
        return {
            "benchmark_name": self.benchmark_name,
            "command": list(self.command),
            "workdir": self.workdir,
            "env_overrides": dict(self.env_overrides),
            "timeout_seconds": self.timeout_seconds,
            "expected_exit_codes": list(self.expected_exit_codes),
        }


@dataclass(frozen=True)
class BenchmarkRunResult:
    """Normalized result from one benchmark invocation."""

    adapter_id: str
    benchmark_name: str
    command: tuple[str, ...]
    workdir: str | None
    exit_code: int | None
    success: bool
    timed_out: bool = False
    process_error: str | None = None
    signal_number: int | None = None
    duration_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""
    parsed_artifact_sources: MappingProxyType[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    task_identity_profile: MappingProxyType[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    task_results: tuple[JsonDict, ...] = ()
    metrics: MappingProxyType[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    metadata: MappingProxyType[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def to_dict(self) -> JsonDict:
        return {
            "adapter_id": self.adapter_id,
            "benchmark_name": self.benchmark_name,
            "command": list(self.command),
            "workdir": self.workdir,
            "exit_code": self.exit_code,
            "success": self.success,
            "timed_out": self.timed_out,
            "process_error": self.process_error,
            "signal_number": self.signal_number,
            "duration_seconds": self.duration_seconds,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "parsed_artifact_sources": dict(self.parsed_artifact_sources),
            "task_identity_profile": dict(self.task_identity_profile),
            "task_results": [dict(task_result) for task_result in self.task_results],
            "metrics": dict(self.metrics),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AdapterStagingProfile:
    """Adapter-specific defaults for isolated candidate execution."""

    default_mode: StagingMode = "off"
    default_workdir: bool = False
    target_path_fields: tuple[str, ...] = ()
    relative_path_fields: tuple[str, ...] = ()

    def to_dict(self) -> JsonDict:
        return {
            "default_mode": self.default_mode,
            "default_workdir": self.default_workdir,
            "target_path_fields": list(self.target_path_fields),
            "relative_path_fields": list(self.relative_path_fields),
        }


@dataclass(frozen=True)
class AdapterStagingSignal:
    """One adapter-specific signal that staging should be enabled."""

    reason: str

    def to_dict(self) -> JsonDict:
        return {"reason": self.reason}


@dataclass(frozen=True)
class AdapterCapabilityProfile:
    """Operator-facing description of one adapter's supported config surface."""

    required_fields: tuple[str, ...] = ()
    config_constraints: tuple[str, ...] = ()
    native_metrics_artifact_fields: tuple[str, ...] = ()
    native_task_results_artifact_fields: tuple[str, ...] = ()
    supports_custom_metrics_parser: bool = True
    supported_metrics_parser_formats: tuple[str, ...] = ()
    supports_custom_task_results_parser: bool = True
    supported_task_results_parser_formats: tuple[str, ...] = ()
    default_task_identity_profile: JsonDict | None = None
    staging_profile: JsonDict = field(default_factory=dict)
    available_starter_presets: tuple[str, ...] = ()
    selected_starter_preset: str = "default"
    starter_config: JsonDict | None = None

    def to_dict(self) -> JsonDict:
        return {
            "required_fields": list(self.required_fields),
            "config_constraints": list(self.config_constraints),
            "native_metrics_artifact_fields": list(self.native_metrics_artifact_fields),
            "native_task_results_artifact_fields": list(
                self.native_task_results_artifact_fields
            ),
            "supports_custom_metrics_parser": self.supports_custom_metrics_parser,
            "supported_metrics_parser_formats": list(
                self.supported_metrics_parser_formats
            ),
            "supports_custom_task_results_parser": (
                self.supports_custom_task_results_parser
            ),
            "supported_task_results_parser_formats": list(
                self.supported_task_results_parser_formats
            ),
            "default_task_identity_profile": (
                dict(self.default_task_identity_profile)
                if isinstance(self.default_task_identity_profile, dict)
                else None
            ),
            "staging_profile": dict(self.staging_profile),
            "available_starter_presets": list(self.available_starter_presets),
            "selected_starter_preset": self.selected_starter_preset,
            "starter_config": (
                dict(self.starter_config)
                if isinstance(self.starter_config, dict)
                else None
            ),
        }


class BenchmarkAdapter(Protocol):
    """Protocol implemented by every benchmark adapter."""

    adapter_id: str

    def validate_config(self, config: JsonDict) -> None:
        """Validate adapter-specific configuration or raise ``ValueError``."""

    def build_invocation(self, config: JsonDict) -> BenchmarkInvocation:
        """Translate adapter config into a normalized command invocation."""

    def run(self, config: JsonDict) -> BenchmarkRunResult:
        """Execute the benchmark invocation and return a normalized result."""

    def staging_profile(self) -> AdapterStagingProfile:
        """Return adapter-specific staging defaults."""

    def suggest_staging(
        self,
        config: JsonDict,
        *,
        source_root: Path,
    ) -> AdapterStagingSignal | None:
        """Return an adapter-specific staging signal when config warrants it."""

    def rewrite_config_for_stage(
        self,
        config: JsonDict,
        *,
        source_root: Path,
        staged_root: Path,
    ) -> JsonDict:
        """Apply adapter-specific config rewrites for staged execution."""

    def task_identity_profile(self, config: JsonDict) -> TaskIdentityProfile | None:
        """Return adapter-specific task identity hints for parsed task results."""

    def parsed_artifact_sources(
        self,
        config: JsonDict,
        *,
        result: BenchmarkRunResult,
    ) -> JsonDict:
        """Return file-backed sources used to parse benchmark outputs."""

    def capability_profile(
        self,
        *,
        starter_preset: str = "default",
    ) -> AdapterCapabilityProfile:
        """Return an operator-facing capability summary for the adapter."""

    def available_starter_presets(self) -> tuple[str, ...]:
        """Return the starter-config preset names supported by the adapter."""

    def starter_config(
        self,
        *,
        preset: str = "default",
    ) -> JsonDict:
        """Return a minimal operator-editable config scaffold for the adapter."""


def execute_invocation(
    adapter_id: str,
    invocation: BenchmarkInvocation,
    *,
    metadata: JsonDict | None = None,
) -> BenchmarkRunResult:
    """Execute one normalized benchmark command."""
    env = os.environ.copy()
    env.update(dict(invocation.env_overrides))
    started = time.monotonic()

    try:
        completed = subprocess.run(
            invocation.command,
            cwd=invocation.workdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=invocation.timeout_seconds,
            check=False,
        )
        duration = time.monotonic() - started
        exit_code = completed.returncode
        signal_number = abs(exit_code) if exit_code < 0 else None
        return BenchmarkRunResult(
            adapter_id=adapter_id,
            benchmark_name=invocation.benchmark_name,
            command=invocation.command,
            workdir=invocation.workdir,
            exit_code=exit_code,
            success=exit_code in invocation.expected_exit_codes and signal_number is None,
            timed_out=False,
            signal_number=signal_number,
            duration_seconds=duration,
            stdout=completed.stdout,
            stderr=completed.stderr,
            metadata=MappingProxyType(dict(metadata or {})),
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - started
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return BenchmarkRunResult(
            adapter_id=adapter_id,
            benchmark_name=invocation.benchmark_name,
            command=invocation.command,
            workdir=invocation.workdir,
            exit_code=None,
            success=False,
            timed_out=True,
            duration_seconds=duration,
            stdout=stdout,
            stderr=stderr,
            metadata=MappingProxyType(dict(metadata or {})),
        )
    except OSError as exc:
        duration = time.monotonic() - started
        return BenchmarkRunResult(
            adapter_id=adapter_id,
            benchmark_name=invocation.benchmark_name,
            command=invocation.command,
            workdir=invocation.workdir,
            exit_code=None,
            success=False,
            timed_out=False,
            process_error=str(exc),
            duration_seconds=duration,
            stdout="",
            stderr="",
            metadata=MappingProxyType(dict(metadata or {})),
        )


class CommandAdapterBase:
    """Shared command-backed adapter implementation."""

    adapter_id: str
    required_config_fields: tuple[str, ...] = ()
    config_constraints: tuple[str, ...] = ()
    native_metrics_artifact_fields: tuple[str, ...] = ()
    native_task_results_artifact_fields: tuple[str, ...] = ()
    supports_custom_metrics_parser: bool = True
    supported_metrics_parser_formats: tuple[str, ...] = ("json_stdout", "json_file")
    supports_custom_task_results_parser: bool = True
    supported_task_results_parser_formats: tuple[str, ...] = (
        "json_stdout",
        "json_file",
    )

    def validate_config(self, config: JsonDict) -> None:
        del config

    def build_invocation(self, config: JsonDict) -> BenchmarkInvocation:
        raise NotImplementedError

    def run(self, config: JsonDict) -> BenchmarkRunResult:
        self.validate_config(config)
        invocation = self.build_invocation(config)
        result = execute_invocation(
            self.adapter_id,
            invocation,
            metadata={"config": config},
        )
        if result.process_error is not None:
            return result
        task_identity_profile = self.task_identity_profile(config)
        metrics, metrics_parse_error = self.parse_metrics(
            config,
            result=result,
        )
        task_results, task_results_parse_error = self.parse_task_results(
            config,
            result=result,
            task_identity_profile=task_identity_profile,
        )
        parsed_artifact_sources = self.parsed_artifact_sources(
            config,
            result=result,
        )
        metadata = dict(result.metadata)
        if metrics_parse_error is not None:
            metadata["metrics_parse_error"] = metrics_parse_error
        if task_results_parse_error is not None:
            metadata["task_results_parse_error"] = task_results_parse_error
        if parsed_artifact_sources:
            metadata["parsed_artifact_sources"] = parsed_artifact_sources
        parse_failed = (
            metrics_parse_error is not None or task_results_parse_error is not None
        )
        return replace(
            result,
            success=result.success and not parse_failed,
            parsed_artifact_sources=MappingProxyType(parsed_artifact_sources),
            task_identity_profile=MappingProxyType(
                task_identity_profile.to_dict() if task_identity_profile is not None else {}
            ),
            task_results=task_results,
            metrics=MappingProxyType(metrics),
            metadata=MappingProxyType(metadata),
        )

    def staging_profile(self) -> AdapterStagingProfile:
        return AdapterStagingProfile()

    def suggest_staging(
        self,
        config: JsonDict,
        *,
        source_root: Path,
    ) -> AdapterStagingSignal | None:
        del config
        del source_root
        return None

    def rewrite_config_for_stage(
        self,
        config: JsonDict,
        *,
        source_root: Path,
        staged_root: Path,
    ) -> JsonDict:
        del source_root
        del staged_root
        return dict(config)

    def default_task_identity_profile(self) -> TaskIdentityProfile | None:
        return None

    def parse_metrics(
        self,
        config: JsonDict,
        *,
        result: BenchmarkRunResult,
    ) -> tuple[JsonDict, str | None]:
        if config.get("metrics_parser") is not None:
            return _parse_metrics_from_config(config, result=result)
        return self.default_metrics_from_result(config, result=result)

    def parse_task_results(
        self,
        config: JsonDict,
        *,
        result: BenchmarkRunResult,
        task_identity_profile: TaskIdentityProfile | None,
    ) -> tuple[tuple[JsonDict, ...], str | None]:
        if config.get("task_results_parser") is not None:
            return _parse_task_results_from_config(config, result=result)
        return self.default_task_results_from_result(
            config,
            result=result,
            task_identity_profile=task_identity_profile,
        )

    def default_metrics_from_result(
        self,
        config: JsonDict,
        *,
        result: BenchmarkRunResult,
    ) -> tuple[JsonDict, str | None]:
        del config
        del result
        return {}, None

    def default_task_results_from_result(
        self,
        config: JsonDict,
        *,
        result: BenchmarkRunResult,
        task_identity_profile: TaskIdentityProfile | None,
    ) -> tuple[tuple[JsonDict, ...], str | None]:
        del config
        del result
        del task_identity_profile
        return (), None

    def parsed_artifact_sources(
        self,
        config: JsonDict,
        *,
        result: BenchmarkRunResult,
    ) -> JsonDict:
        sources: JsonDict = {}
        metrics_source = _parsed_source_from_json_parser(
            config.get("metrics_parser"),
            result=result,
            origin="metrics_parser.path",
        )
        if metrics_source is not None:
            sources["metrics"] = [metrics_source]

        task_results_source = _parsed_source_from_json_parser(
            config.get("task_results_parser"),
            result=result,
            origin="task_results_parser.path",
        )
        if task_results_source is not None:
            sources["task_results"] = [task_results_source]
        return sources

    def task_identity_profile(self, config: JsonDict) -> TaskIdentityProfile | None:
        default_profile = self.default_task_identity_profile()
        profile_override = config.get("task_identity_profile")
        parser = config.get("task_results_parser")
        if not isinstance(profile_override, dict) and parser is None:
            return default_profile
        if profile_override is not None and not isinstance(profile_override, dict):
            return default_profile
        if parser is not None and not isinstance(parser, dict):
            return default_profile

        profile_data = (
            default_profile.to_dict()
            if default_profile is not None
            else TaskIdentityProfile().to_dict()
        )
        if isinstance(profile_override, dict):
            _apply_task_identity_profile_overrides(
                profile_data,
                profile_override,
            )
        if not isinstance(parser, dict):
            return _task_identity_profile_from_raw(profile_data)
        _apply_task_identity_profile_overrides(
            profile_data,
            parser,
        )
        return _task_identity_profile_from_raw(profile_data)

    def capability_profile(
        self,
        *,
        starter_preset: str = "default",
    ) -> AdapterCapabilityProfile:
        default_task_identity_profile = self.default_task_identity_profile()
        return AdapterCapabilityProfile(
            required_fields=self.required_config_fields,
            config_constraints=self.config_constraints,
            native_metrics_artifact_fields=self.native_metrics_artifact_fields,
            native_task_results_artifact_fields=self.native_task_results_artifact_fields,
            supports_custom_metrics_parser=self.supports_custom_metrics_parser,
            supported_metrics_parser_formats=(
                self.supported_metrics_parser_formats
                if self.supports_custom_metrics_parser
                else ()
            ),
            supports_custom_task_results_parser=(
                self.supports_custom_task_results_parser
            ),
            supported_task_results_parser_formats=(
                self.supported_task_results_parser_formats
                if self.supports_custom_task_results_parser
                else ()
            ),
            default_task_identity_profile=(
                default_task_identity_profile.to_dict()
                if default_task_identity_profile is not None
                else None
            ),
            staging_profile=self.staging_profile().to_dict(),
            available_starter_presets=self.available_starter_presets(),
            selected_starter_preset=starter_preset,
            starter_config=self.starter_config(preset=starter_preset),
        )

    def starter_preset_configs(self) -> dict[str, JsonDict]:
        return {"default": {}}

    def available_starter_presets(self) -> tuple[str, ...]:
        return tuple(self.starter_preset_configs().keys())

    def starter_config(
        self,
        *,
        preset: str = "default",
    ) -> JsonDict:
        preset_configs = self.starter_preset_configs()
        try:
            selected = preset_configs[preset]
        except KeyError as exc:
            available = ", ".join(sorted(preset_configs)) or "<none>"
            raise KeyError(
                f"Unknown starter preset `{preset}` for `{self.adapter_id}`. "
                f"Available presets: {available}."
            ) from exc
        return copy.deepcopy(selected)


def _apply_task_identity_profile_overrides(
    profile_data: JsonDict,
    override: JsonDict,
) -> None:
    override_fields = (
        "match_key_field",
        "tier_field",
        "weight_field",
        "default_weight",
    )
    for field_name in override_fields:
        if field_name in override:
            profile_data[field_name] = override[field_name]

    if "case_id_field" in override and "match_key_field" not in override:
        profile_data["match_key_field"] = override["case_id_field"]

    tier_weights = profile_data.get("tier_weights", {})
    if not isinstance(tier_weights, dict):
        tier_weights = {}
    if "tier_weights" in override and isinstance(override["tier_weights"], dict):
        tier_weights = {
            **{
                key: value
                for key, value in tier_weights.items()
                if isinstance(key, str)
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            },
            **{
                key: float(value)
                for key, value in override["tier_weights"].items()
                if isinstance(key, str)
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            },
        }
    profile_data["tier_weights"] = tier_weights


def normalize_command(value: Any, *, field_name: str = "command") -> tuple[str, ...]:
    """Validate and normalize a command sequence."""
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"`{field_name}` must be a non-empty list of strings.")
    normalized: list[str] = []
    for part in value:
        if not isinstance(part, str) or not part:
            raise ValueError(f"`{field_name}` entries must be non-empty strings.")
        normalized.append(part)
    return tuple(normalized)


def normalize_mapping(
    value: Any,
    *,
    field_name: str,
) -> MappingProxyType[str, str]:
    """Validate and normalize a string-keyed mapping."""
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, dict):
        raise ValueError(f"`{field_name}` must be a mapping of strings.")
    normalized: dict[str, str] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"`{field_name}` keys must be non-empty strings.")
        if not isinstance(raw, str):
            raise ValueError(f"`{field_name}` values must be strings.")
        normalized[key] = raw
    return MappingProxyType(normalized)


def normalize_workdir(value: Any) -> str | None:
    """Validate and normalize a working directory."""
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("`workdir` must be a non-empty string when provided.")
    return str(Path(value))


def rewrite_pathlike_mapping(
    value: Any,
    *,
    source_root: Path,
    staged_root: Path,
) -> Any:
    """Rewrite nested mapping values whose keys look path-like."""
    if isinstance(value, dict):
        rewritten: dict[str, Any] = {}
        for key, raw in value.items():
            if not isinstance(key, str):
                rewritten[key] = raw
                continue
            if isinstance(raw, dict):
                rewritten[key] = rewrite_pathlike_mapping(
                    raw,
                    source_root=source_root,
                    staged_root=staged_root,
                )
                continue
            if isinstance(raw, list):
                if _looks_pathlike_key(key):
                    rewritten[key] = [
                        _rewrite_pathlike_string(
                            item,
                            source_root=source_root,
                            staged_root=staged_root,
                        )
                        if isinstance(item, str)
                        else item
                        for item in raw
                    ]
                else:
                    rewritten[key] = [
                        rewrite_pathlike_mapping(
                            item,
                            source_root=source_root,
                            staged_root=staged_root,
                        )
                        if isinstance(item, dict)
                        else item
                        for item in raw
                    ]
                continue
            if isinstance(raw, str) and _looks_pathlike_key(key):
                rewritten[key] = _rewrite_pathlike_string(
                    raw,
                    source_root=source_root,
                    staged_root=staged_root,
                )
                continue
            rewritten[key] = raw
        return rewritten
    return value


def mapping_has_pathlike_hints(
    value: Any,
    *,
    source_root: Path,
) -> bool:
    """Return whether a nested mapping carries path-like staging hints."""
    placeholder_tokens = (
        "{target_root}",
        "$AUTOHARNESS_TARGET_ROOT",
        "${AUTOHARNESS_TARGET_ROOT}",
    )
    source_root_resolved = source_root.resolve()

    def has_hint(raw: Any, *, key: str | None = None) -> bool:
        if isinstance(raw, dict):
            return any(
                has_hint(child, key=child_key if isinstance(child_key, str) else None)
                for child_key, child in raw.items()
            )
        if isinstance(raw, list):
            if key is not None and _looks_pathlike_key(key):
                return any(
                    isinstance(item, str)
                    and _string_has_pathlike_hint(
                        item,
                        source_root=source_root_resolved,
                        placeholder_tokens=placeholder_tokens,
                    )
                    for item in raw
                )
            return any(has_hint(item) for item in raw)
        if isinstance(raw, str) and key is not None and _looks_pathlike_key(key):
            return _string_has_pathlike_hint(
                raw,
                source_root=source_root_resolved,
                placeholder_tokens=placeholder_tokens,
            )
        return False

    return has_hint(value)


def _looks_pathlike_key(key: str) -> bool:
    normalized = key.lower()
    tokens = (
        "path",
        "dir",
        "root",
        "file",
        "cache",
        "artifact",
        "output",
        "log",
        "folder",
    )
    return any(token in normalized for token in tokens)


def _rewrite_pathlike_string(
    value: str,
    *,
    source_root: Path,
    staged_root: Path,
) -> str:
    source_root_resolved = source_root.resolve()
    staged_root_resolved = staged_root.resolve()
    if str(source_root_resolved) in value:
        return value.replace(str(source_root_resolved), str(staged_root_resolved))
    if not value or Path(value).is_absolute():
        return value
    return str((staged_root_resolved / value).resolve())


def _string_has_pathlike_hint(
    value: str,
    *,
    source_root: Path,
    placeholder_tokens: tuple[str, ...],
) -> bool:
    if not value:
        return False
    if value in placeholder_tokens:
        return True
    if str(source_root) in value:
        return True
    return not Path(value).is_absolute()


def _parse_metrics_from_config(
    config: JsonDict,
    *,
    result: BenchmarkRunResult,
) -> tuple[JsonDict, str | None]:
    parser = config.get("metrics_parser")
    if parser is None:
        return {}, None
    payload, parse_error = _decode_json_parser_payload(
        parser,
        parser_name="metrics_parser",
        result=result,
    )
    if parse_error is not None:
        return {}, parse_error

    if not isinstance(payload, dict):
        return {}, "Decoded metrics payload must be a mapping."

    include = parser.get("include")
    if include is not None:
        if not isinstance(include, list) or not all(
            isinstance(key, str) and key for key in include
        ):
            return {}, "`metrics_parser.include` must be a list of strings."
        payload = {key: payload[key] for key in include if key in payload}

    return dict(payload), None


def _parse_task_results_from_config(
    config: JsonDict,
    *,
    result: BenchmarkRunResult,
) -> tuple[tuple[JsonDict, ...], str | None]:
    parser = config.get("task_results_parser")
    if parser is None:
        return (), None

    payload, parse_error = _decode_json_parser_payload(
        parser,
        parser_name="task_results_parser",
        result=result,
    )
    if parse_error is not None:
        return (), parse_error

    if not isinstance(parser, dict):
        return (), "`task_results_parser` must be a mapping when provided."
    task_id_field = parser.get("task_id_field", "task_id")
    score_field = parser.get("score_field")
    success_field = parser.get("success_field", "success")
    if not isinstance(task_id_field, str) or not task_id_field:
        return (), "`task_results_parser.task_id_field` must be a non-empty string."
    if score_field is not None and (not isinstance(score_field, str) or not score_field):
        return (), "`task_results_parser.score_field` must be a non-empty string."
    if not isinstance(success_field, str) or not success_field:
        return (), "`task_results_parser.success_field` must be a non-empty string."

    normalized = _normalize_task_results_payload(
        payload,
        task_id_field=task_id_field,
        score_field=score_field,
        success_field=success_field,
    )
    if isinstance(normalized, str):
        return (), normalized
    return tuple(normalized), None


def _decode_json_parser_payload(
    parser: Any,
    *,
    parser_name: str,
    result: BenchmarkRunResult,
) -> tuple[Any, str | None]:
    if not isinstance(parser, dict):
        return None, f"`{parser_name}` must be a mapping when provided."

    format_name = parser.get("format")
    if not isinstance(format_name, str) or not format_name:
        return None, f"`{parser_name}.format` is required."

    try:
        if format_name == "json_stdout":
            payload = _load_json_from_text(result.stdout, field_name="stdout")
        elif format_name == "json_stderr":
            payload = _load_json_from_text(result.stderr, field_name="stderr")
        elif format_name == "json_file":
            raw_path = parser.get("path")
            if not isinstance(raw_path, str) or not raw_path:
                return None, f"`{parser_name}.path` is required for json_file."
            source_path = Path(raw_path)
            if not source_path.is_absolute() and result.workdir:
                source_path = Path(result.workdir) / source_path
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        else:
            return None, f"Unsupported `{parser_name}.format`: {format_name}"
    except FileNotFoundError as exc:
        return None, f"Parser file not found: {exc.filename}"
    except json.JSONDecodeError as exc:
        return None, f"Could not decode parser JSON: {exc}"
    except OSError as exc:
        return None, f"Could not read parser source: {exc}"

    key_path = parser.get("key_path")
    if key_path is not None:
        if not isinstance(key_path, list):
            return None, f"`{parser_name}.key_path` must be a list when provided."
        try:
            for segment in key_path:
                if isinstance(payload, dict) and isinstance(segment, str):
                    payload = payload[segment]
                elif isinstance(payload, list) and isinstance(segment, int):
                    payload = payload[segment]
                else:
                    return None, f"{parser_name} key_path does not match the decoded payload."
        except (KeyError, IndexError) as exc:
            return None, f"{parser_name} key_path lookup failed: {exc}"
    return payload, None


def _load_json_artifact(
    raw_path: str,
    *,
    result: BenchmarkRunResult,
    field_name: str,
) -> tuple[Any | None, str | None]:
    source_path = _resolve_artifact_path(raw_path, result=result)
    try:
        return json.loads(source_path.read_text(encoding="utf-8")), None
    except FileNotFoundError as exc:
        return None, f"{field_name} file not found: {exc.filename}"
    except json.JSONDecodeError as exc:
        return None, f"Could not decode {field_name} JSON: {exc}"
    except OSError as exc:
        return None, f"Could not read {field_name}: {exc}"


def _load_json_artifact_from_config(
    config: JsonDict,
    *,
    result: BenchmarkRunResult,
    field_names: tuple[str, ...],
) -> tuple[Any | None, str | None]:
    for field_name in field_names:
        raw_path = config.get(field_name)
        if raw_path is None:
            continue
        if not isinstance(raw_path, str) or not raw_path:
            return None, f"`{field_name}` must be a non-empty string."
        return _load_json_artifact(
            raw_path,
            result=result,
            field_name=field_name,
        )
    return None, None


def _resolve_artifact_path(
    raw_path: str,
    *,
    result: BenchmarkRunResult,
) -> Path:
    source_path = Path(raw_path)
    if not source_path.is_absolute():
        base_dir = Path(result.workdir) if result.workdir is not None else Path.cwd()
        source_path = base_dir / source_path
    return source_path.resolve()


def _parsed_source_from_json_parser(
    parser: Any,
    *,
    result: BenchmarkRunResult,
    origin: str,
) -> JsonDict | None:
    if not isinstance(parser, dict):
        return None
    if parser.get("format") != "json_file":
        return None
    raw_path = parser.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return None
    return {
        "origin": origin,
        "path": str(_resolve_artifact_path(raw_path, result=result)),
    }


def _extract_numeric_metrics_from_payload(payload: Any) -> JsonDict:
    metrics: JsonDict = {}

    def update_from_mapping(mapping: Any) -> None:
        if not isinstance(mapping, dict):
            return
        for key, value in mapping.items():
            if (
                isinstance(key, str)
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                metrics[key] = float(value)

    if isinstance(payload, dict):
        update_from_mapping(payload.get("metrics"))
        update_from_mapping(payload.get("summary"))
        for key in (
            "pass_rate",
            "success_rate",
            "score",
            "accuracy",
            "reward",
            "mean_reward",
            "cost",
            "mean_cost",
        ):
            value = payload.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                metrics[key] = float(value)

    if "pass_rate" not in metrics and "success_rate" in metrics:
        metrics["pass_rate"] = float(metrics["success_rate"])

    return metrics


def _extract_task_results_from_payload(
    payload: Any,
    *,
    task_id_field: str,
    score_field: str | None = None,
    success_field: str = "success",
    search_keys: tuple[str, ...] = ("task_results", "results", "tasks", "cases", "records"),
) -> tuple[tuple[JsonDict, ...], str | None]:
    candidate_payload = payload
    if isinstance(payload, dict):
        candidate_payload = None
        for key in search_keys:
            candidate = payload.get(key)
            if isinstance(candidate, (list, dict)):
                candidate_payload = candidate
                break
        if candidate_payload is None:
            return (), None

    normalized = _normalize_task_results_payload(
        candidate_payload,
        task_id_field=task_id_field,
        score_field=score_field,
        success_field=success_field,
    )
    if isinstance(normalized, str):
        return (), normalized
    return tuple(normalized), None


def _normalize_task_results_payload(
    payload: Any,
    *,
    task_id_field: str,
    score_field: str | None,
    success_field: str,
) -> list[JsonDict] | str:
    normalized: list[JsonDict] = []
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            task_result = _normalize_one_task_result(
                item,
                fallback_task_id=None,
                task_id_field=task_id_field,
                score_field=score_field,
                success_field=success_field,
            )
            if isinstance(task_result, str):
                return f"Task result {index}: {task_result}"
            normalized.append(task_result)
        return normalized

    if isinstance(payload, dict):
        for task_id, item in payload.items():
            fallback_task_id = str(task_id) if isinstance(task_id, str) and task_id else None
            task_result = _normalize_one_task_result(
                item,
                fallback_task_id=fallback_task_id,
                task_id_field=task_id_field,
                score_field=score_field,
                success_field=success_field,
            )
            if isinstance(task_result, str):
                return f"Task result `{fallback_task_id or task_id}`: {task_result}"
            normalized.append(task_result)
        return normalized

    return "Decoded task results payload must be a list or mapping."


def _normalize_one_task_result(
    item: Any,
    *,
    fallback_task_id: str | None,
    task_id_field: str,
    score_field: str | None,
    success_field: str,
) -> JsonDict | str:
    if isinstance(item, (int, float, bool)):
        if not fallback_task_id:
            return "Missing task id."
        score = _coerce_task_score(item)
        if score is None:
            return "Task score was not numeric."
        return {"task_id": fallback_task_id, "score": score}

    if not isinstance(item, dict):
        return "Each task result must be a mapping, bool, or numeric score."

    task_id = item.get(task_id_field)
    if not isinstance(task_id, str) or not task_id:
        fallback_id = item.get("id")
        if isinstance(fallback_id, str) and fallback_id:
            task_id = fallback_id
        else:
            task_id = fallback_task_id
    if not isinstance(task_id, str) or not task_id:
        return "Missing task id."

    raw_score: Any = None
    if score_field is not None:
        raw_score = item.get(score_field)
    if raw_score is None and "score" in item:
        raw_score = item.get("score")
    if raw_score is None and success_field in item:
        raw_score = item.get(success_field)
    if raw_score is None and "passed" in item:
        raw_score = item.get("passed")
    if raw_score is None and "success" in item:
        raw_score = item.get("success")

    score = _coerce_task_score(raw_score)
    if score is None:
        return "Missing numeric or boolean score/success signal."
    normalized = dict(item)
    normalized["task_id"] = task_id
    normalized["score"] = score
    return normalized


def _coerce_task_score(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _load_json_from_text(text: str, *, field_name: str) -> Any:
    stripped = text.strip()
    if not stripped:
        raise json.JSONDecodeError(
            f"{field_name} was empty",
            text,
            0,
        )
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        if not lines:
            raise
        return json.loads(lines[-1])


def _task_identity_profile_from_raw(raw: JsonDict) -> TaskIdentityProfile:
    match_key_field = raw.get("match_key_field", "task_id")
    if not isinstance(match_key_field, str) or not match_key_field:
        raise ValueError("`task_results_parser.match_key_field` must be a non-empty string.")

    tier_field = raw.get("tier_field")
    if tier_field is not None and (not isinstance(tier_field, str) or not tier_field):
        raise ValueError("`task_results_parser.tier_field` must be a non-empty string.")

    weight_field = raw.get("weight_field")
    if weight_field is not None and (not isinstance(weight_field, str) or not weight_field):
        raise ValueError("`task_results_parser.weight_field` must be a non-empty string.")

    default_weight = raw.get("default_weight", 1.0)
    if (
        not isinstance(default_weight, (int, float))
        or isinstance(default_weight, bool)
        or float(default_weight) < 0.0
    ):
        raise ValueError("`task_results_parser.default_weight` must be a non-negative number.")

    raw_tier_weights = raw.get("tier_weights", {})
    if not isinstance(raw_tier_weights, dict):
        raise ValueError("`task_results_parser.tier_weights` must be a mapping when provided.")

    tier_weights: dict[str, float] = {}
    for tier_name, weight in raw_tier_weights.items():
        if not isinstance(tier_name, str) or not tier_name:
            raise ValueError("`task_results_parser.tier_weights` keys must be non-empty strings.")
        if (
            not isinstance(weight, (int, float))
            or isinstance(weight, bool)
            or float(weight) < 0.0
        ):
            raise ValueError(
                "`task_results_parser.tier_weights` values must be non-negative numbers."
            )
        tier_weights[tier_name] = float(weight)

    return TaskIdentityProfile(
        match_key_field=match_key_field,
        tier_field=tier_field,
        weight_field=weight_field,
        tier_weights=MappingProxyType(tier_weights),
        default_weight=float(default_weight),
    )
