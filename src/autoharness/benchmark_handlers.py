"""Benchmark catalog and scaffold CLI handlers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapters import get_adapter, implemented_adapter_ids
from .benchmarks import benchmark_catalog, benchmark_catalog_entry
from .execution_support import _compose_benchmark_config
from .outputs import (
    _emit_json_output,
    _infer_structured_output_format,
    _write_json,
    _write_yaml,
)
from .stages import apply_stage_overrides


def _default_benchmark_config_output_path(
    *,
    adapter_id: str,
    preset: str,
) -> Path:
    if preset == "default":
        return Path.cwd() / f"{adapter_id}.yaml"
    return Path.cwd() / f"{adapter_id}.{preset}.yaml"


def _render_benchmark_entry(
    *,
    adapter_id: str,
    starter_preset: str = "default",
) -> dict[str, object]:
    spec = benchmark_catalog_entry(adapter_id)
    rendered = spec.to_dict()
    if adapter_id in set(implemented_adapter_ids()):
        adapter = get_adapter(adapter_id)
        try:
            capabilities = adapter.capability_profile(
                starter_preset=starter_preset,
            ).to_dict()
        except KeyError as exc:
            raise KeyError(str(exc)) from exc
        rendered["implemented"] = True
        rendered["capabilities"] = capabilities
    else:
        rendered["implemented"] = False
        rendered["capabilities"] = None
    return rendered


def _handle_list_benchmarks(args: argparse.Namespace) -> int:
    rendered_entries = []
    for spec in benchmark_catalog():
        if args.implemented_only and spec.adapter_id not in set(implemented_adapter_ids()):
            continue
        rendered_entries.append(
            _render_benchmark_entry(
                adapter_id=spec.adapter_id,
            )
        )

    payload = {"benchmarks": rendered_entries}
    if _emit_json_output(
        rendered=payload,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    for rendered in rendered_entries:
        print(f"{rendered['adapter_id']}: {rendered['label']}")
        print(f"  support_level: {rendered['support_level']}")
        print(f"  implemented: {'yes' if rendered['implemented'] else 'no'}")
        print(f"  kind: {rendered['kind']}")
        print(f"  source: {rendered['source']}")
        print(f"  why: {rendered['why_it_matters']}")
        if rendered["notes"]:
            print(f"  notes: {rendered['notes']}")
        capabilities = rendered.get("capabilities")
        if isinstance(capabilities, dict):
            required_fields = capabilities.get("required_fields") or []
            if required_fields:
                print(f"  required_fields: {', '.join(required_fields)}")
            native_metrics_fields = capabilities.get("native_metrics_artifact_fields") or []
            if native_metrics_fields:
                print(
                    "  native_metrics_artifact_fields: "
                    + ", ".join(native_metrics_fields)
                )
            native_task_fields = (
                capabilities.get("native_task_results_artifact_fields") or []
            )
            if native_task_fields:
                print(
                    "  native_task_results_artifact_fields: "
                    + ", ".join(native_task_fields)
                )
            staging_profile = capabilities.get("staging_profile")
            if isinstance(staging_profile, dict):
                print(
                    "  staging_default: "
                    + str(staging_profile.get("default_mode", "off"))
                )
        print()
    return 0


def _handle_show_benchmark(args: argparse.Namespace) -> int:
    try:
        rendered = _render_benchmark_entry(
            adapter_id=args.adapter,
            starter_preset=args.preset,
        )
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"{rendered['adapter_id']}: {rendered['label']}")
    print(f"support_level: {rendered['support_level']}")
    print(f"implemented: {'yes' if rendered['implemented'] else 'no'}")
    print(f"kind: {rendered['kind']}")
    print(f"source: {rendered['source']}")
    print(f"why: {rendered['why_it_matters']}")
    strengths = rendered.get("strengths") or []
    if strengths:
        print(f"strengths: {', '.join(strengths)}")
    risks = rendered.get("risks") or []
    if risks:
        print(f"risks: {', '.join(risks)}")
    if rendered["notes"]:
        print(f"notes: {rendered['notes']}")
    capabilities = rendered.get("capabilities")
    if isinstance(capabilities, dict):
        required_fields = capabilities.get("required_fields") or []
        if required_fields:
            print(f"required_fields: {', '.join(required_fields)}")
        constraints = capabilities.get("config_constraints") or []
        if constraints:
            print("config_constraints:")
            for constraint in constraints:
                print(f"  - {constraint}")
        native_metrics_fields = capabilities.get("native_metrics_artifact_fields") or []
        if native_metrics_fields:
            print(
                "native_metrics_artifact_fields: "
                + ", ".join(native_metrics_fields)
            )
        native_task_fields = (
            capabilities.get("native_task_results_artifact_fields") or []
        )
        if native_task_fields:
            print(
                "native_task_results_artifact_fields: "
                + ", ".join(native_task_fields)
            )
        default_profile = capabilities.get("default_task_identity_profile")
        if isinstance(default_profile, dict):
            print(
                "default_task_identity_profile: "
                + json.dumps(default_profile, sort_keys=True)
            )
        starter_presets = capabilities.get("available_starter_presets") or []
        if starter_presets:
            print("available_starter_presets: " + ", ".join(starter_presets))
            print(
                "selected_starter_preset: "
                + str(capabilities.get("selected_starter_preset", "default"))
            )
        staging_profile = capabilities.get("staging_profile")
        if isinstance(staging_profile, dict):
            print("staging_profile: " + json.dumps(staging_profile, sort_keys=True))
        starter_config = capabilities.get("starter_config")
        if isinstance(starter_config, dict):
            print("starter_config: " + json.dumps(starter_config, sort_keys=True))
    return 0


def _handle_init_benchmark_config(args: argparse.Namespace) -> int:
    try:
        adapter = get_adapter(args.adapter)
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc

    output = args.output or _default_benchmark_config_output_path(
        adapter_id=args.adapter,
        preset=args.preset,
    )
    if output.exists() and not args.force:
        raise SystemExit(
            f"Refusing to overwrite existing config scaffold: {output}. Use --force."
        )

    try:
        payload = adapter.starter_config(preset=args.preset)
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc
    output_format = _infer_structured_output_format(
        path=output,
        explicit_format=args.format,
    )
    if output_format == "json":
        _write_json(output, payload)
    else:
        _write_yaml(output, payload)

    print(f"Wrote benchmark config scaffold to {output}")
    print(f"Adapter: {args.adapter}")
    print(f"Preset: {args.preset}")
    print(f"Format: {output_format}")
    return 0


def _render_benchmark_config_preview(args: argparse.Namespace) -> dict[str, object]:
    try:
        adapter = get_adapter(args.adapter)
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc

    config = _compose_benchmark_config(
        adapter=adapter,
        config_path=args.config,
        selected_preset=args.preset,
        inline_overrides=list(args.set),
    )
    try:
        effective_config, applied_stage_override = (
            apply_stage_overrides(config, stage=args.stage)
            if args.stage is not None
            else (config, False)
        )
        adapter.validate_config(effective_config)
        invocation = adapter.build_invocation(effective_config)
    except (ValueError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc

    return {
        "adapter_id": args.adapter,
        "selected_preset": args.preset,
        "config_path": str(args.config) if args.config is not None else None,
        "inline_overrides": list(args.set),
        "stage": args.stage,
        "applied_stage_override": applied_stage_override,
        "effective_config": effective_config,
        "planned_invocation": invocation.to_dict(),
        "capabilities": adapter.capability_profile(
            starter_preset=args.preset or "default"
        ).to_dict(),
    }


def _render_benchmark_config_validation(args: argparse.Namespace) -> dict[str, object]:
    try:
        rendered = _render_benchmark_config_preview(args)
    except SystemExit as exc:
        return {
            "adapter_id": args.adapter,
            "selected_preset": args.preset,
            "config_path": str(args.config) if args.config is not None else None,
            "inline_overrides": list(args.set),
            "stage": args.stage,
            "valid": False,
            "error_count": 1,
            "validation_errors": [str(exc)],
        }
    return {
        **rendered,
        "valid": True,
        "error_count": 0,
        "validation_errors": [],
    }


def _handle_show_benchmark_config(args: argparse.Namespace) -> int:
    rendered = _render_benchmark_config_preview(args)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0

    print(f"Adapter: {rendered['adapter_id']}")
    print(f"Preset: {rendered['selected_preset'] or '(none)'}")
    print(f"Config path: {rendered['config_path'] or '(none)'}")
    print(f"Stage: {rendered['stage'] or '(none)'}")
    print(
        "Stage override applied: "
        + ("yes" if rendered["applied_stage_override"] else "no")
    )
    print(f"Inline overrides: {len(rendered['inline_overrides'])}")
    invocation = rendered["planned_invocation"]
    assert isinstance(invocation, dict)
    print(f"Benchmark: {invocation['benchmark_name']}")
    print("Command: " + json.dumps(invocation["command"]))
    if invocation.get("workdir") is not None:
        print(f"Workdir: {invocation['workdir']}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_validate_benchmark_config(args: argparse.Namespace) -> int:
    rendered = _render_benchmark_config_validation(args)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0 if bool(rendered["valid"]) else 1

    print(f"Adapter: {rendered['adapter_id']}")
    print(f"Preset: {rendered['selected_preset'] or '(none)'}")
    print(f"Config path: {rendered['config_path'] or '(none)'}")
    print(f"Stage: {rendered['stage'] or '(none)'}")
    print(f"Valid: {'yes' if rendered['valid'] else 'no'}")
    print(f"Errors: {rendered['error_count']}")
    validation_errors = rendered["validation_errors"]
    assert isinstance(validation_errors, list)
    for error in validation_errors:
        print(f"- {error}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0 if bool(rendered["valid"]) else 1
