"""CLI handlers for proposal artifact generation and inspection."""

from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime
from pathlib import Path

from .adapters import get_adapter
from .cli_support import (
    _load_structured_file,
    _resolve_workspace_id,
    _resolve_workspace_track,
)
from .editing import edit_plan_from_dict, start_edit_session
from .execution_support import (
    _compose_benchmark_config,
    _resolve_stage_config_preset,
    _suggest_iteration_hypothesis,
)
from .generators import (
    ProposalGenerationError,
    ProposalGenerationRequest,
    generator_catalog,
    generator_catalog_entry,
    get_generator,
)
from .listings import _build_proposal_listing_payload
from .outputs import (
    _emit_json_output,
    _emit_text_listing_output,
    _export_listing_payload,
)
from .events import append_workspace_event
from .preflight import resolve_preflight_commands
from .proposal_context import build_proposal_generation_context
from .provider_profiles import (
    merge_provider_profile,
    resolve_provider_profile,
    summarize_provider_profile,
)
from .proposals import (
    create_proposal_record,
    load_proposal_effective_config,
    load_proposal_edit_plan,
    load_proposal_preview_application,
    persist_proposal,
    resolve_proposal_artifact_paths,
    resolve_workspace_proposal,
)
from .queries import ProposalQuerySpec
from .search import resolve_focus_task_ids
from .stages import apply_stage_overrides, stage_policy_for
from .tracking import load_workspace
from .execution_handlers import _handle_run_iteration


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _preview_state_from_application(application: dict[str, object]) -> str:
    if bool(application.get("blocked")):
        return "blocked"
    if bool(application.get("proposal_only")):
        return "proposal_only"
    return "preview"


def _resolve_saved_proposal(args: argparse.Namespace):
    workspace_id = _resolve_workspace_id(
        root=args.root,
        requested_workspace_id=args.workspace_id,
    )
    try:
        return resolve_workspace_proposal(
            root=args.root,
            workspace_id=workspace_id,
            proposal_id=args.proposal_id,
            track_id=args.track_id,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


def _prepare_proposal_listing(args: argparse.Namespace):
    workspace_id = _resolve_workspace_id(
        root=args.root,
        requested_workspace_id=args.workspace_id,
    )
    if args.track_id is not None:
        workspace, _, resolved_track_id = _resolve_workspace_track(
            root=args.root,
            workspace_id=workspace_id,
            requested_track_id=args.track_id,
        )
    else:
        workspace = load_workspace(args.root, workspace_id)
        resolved_track_id = None
    spec = ProposalQuerySpec.from_args(args, resolved_track_id=resolved_track_id)
    rendered = _build_proposal_listing_payload(
        root=args.root,
        workspace_id=workspace_id,
        spec=spec,
    )
    return workspace_id, workspace, resolved_track_id, spec, rendered


def _handle_list_generators(args: argparse.Namespace) -> int:
    rendered = {"generators": list(generator_catalog())}
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0

    for item in rendered["generators"]:
        assert isinstance(item, dict)
        print(f"{item['generator_id']}: {item['label']}")
        print(f"  kind: {item['kind']}")
        print(
            "  synthesize_without_edit_plan: "
            + ("yes" if item["can_generate_without_edit_plan"] else "no")
        )
        option_keys = item.get("generator_option_keys") or []
        if option_keys:
            assert isinstance(option_keys, list)
            print("  generator_option_keys: " + ", ".join(str(value) for value in option_keys))
        env_vars = item.get("environment_variables") or []
        if env_vars:
            assert isinstance(env_vars, list)
            print("  environment_variables: " + ", ".join(str(value) for value in env_vars))
        print(f"  description: {item['description']}")
        if item.get("notes"):
            print(f"  notes: {item['notes']}")
        print()
    return 0


def _handle_show_generator(args: argparse.Namespace) -> int:
    try:
        rendered = generator_catalog_entry(args.generator)
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc

    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0

    print(f"{rendered['generator_id']}: {rendered['label']}")
    print(f"kind: {rendered['kind']}")
    print(
        "requires_edit_plan_input: "
        + ("yes" if rendered["requires_edit_plan_input"] else "no")
    )
    print(
        "can_generate_without_edit_plan: "
        + ("yes" if rendered["can_generate_without_edit_plan"] else "no")
    )
    print(
        "accepts_intervention_class: "
        + ("yes" if rendered["accepts_intervention_class"] else "no")
    )
    option_keys = rendered.get("generator_option_keys") or []
    if option_keys:
        assert isinstance(option_keys, list)
        print("generator_option_keys: " + ", ".join(str(value) for value in option_keys))
    env_vars = rendered.get("environment_variables") or []
    if env_vars:
        assert isinstance(env_vars, list)
        print("environment_variables: " + ", ".join(str(value) for value in env_vars))
    print(f"description: {rendered['description']}")
    if rendered.get("notes"):
        print(f"notes: {rendered['notes']}")
    return 0


def _parse_generator_options(raw_options: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_entry in raw_options:
        if "=" not in raw_entry:
            raise SystemExit("`--generator-option` must use key=value format.")
        key, value = raw_entry.split("=", 1)
        if not key.strip() or not value.strip():
            raise SystemExit("`--generator-option` requires non-empty key and value.")
        parsed[key.strip()] = value.strip()
    return parsed


def _parse_fallback_generator_ids(metadata: dict[str, str]) -> tuple[str, ...]:
    raw_value = metadata.get("fallback_generators") or metadata.get(
        "fallback_generator_ids"
    )
    if not isinstance(raw_value, str) or not raw_value.strip():
        return ()
    fallback_ids: list[str] = []
    for entry in raw_value.split(","):
        fallback_id = entry.strip()
        if not fallback_id or fallback_id in fallback_ids:
            continue
        fallback_ids.append(fallback_id)
    return tuple(fallback_ids)


def _generation_resource_usage(metadata: dict[str, object]) -> dict[str, float | int]:
    usage = metadata.get("usage")
    usage_payload = usage if isinstance(usage, dict) else {}
    input_tokens = int(usage_payload.get("input_tokens", 0) or 0)
    output_tokens = int(usage_payload.get("output_tokens", 0) or 0)
    total_tokens = int(usage_payload.get("total_tokens", 0) or 0)
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens
    return {
        "generation_total_tokens": total_tokens,
        "generation_total_cost_usd": float(usage_payload.get("cost_usd", 0.0) or 0.0),
        "generation_total_duration_seconds": float(
            metadata.get("generation_duration_seconds", 0.0) or 0.0
        ),
        "benchmark_total_cost": 0.0,
        "benchmark_total_duration_seconds": 0.0,
    }


def _handle_generate_proposal(args: argparse.Namespace) -> int:
    args.workspace_id = _resolve_workspace_id(
        root=args.root,
        requested_workspace_id=args.workspace_id,
    )
    workspace, state, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    try:
        adapter = get_adapter(args.adapter)
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        requested_generator = get_generator(args.generator)
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc

    track = workspace.tracks[track_id]
    try:
        stage_policy = stage_policy_for(
            args.stage,
            min_judge_pass_rate=track.evaluator.min_judge_pass_rate,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    benchmark_target = workspace.benchmark_policy.get(stage_policy.benchmark_policy_key)
    track_policy = None
    from .mutations import _resolve_track_benchmark_policy  # local import avoids cycle risk

    track_policy, _ = _resolve_track_benchmark_policy(
        root=args.root,
        workspace=workspace,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )
    benchmark_target = getattr(track_policy, stage_policy.benchmark_policy_key)
    selected_preset, policy_preset, preset_source = _resolve_stage_config_preset(
        cli_preset=args.preset,
        track_policy=track_policy,
        stage_policy=stage_policy,
    )
    composed_config = _compose_benchmark_config(
        adapter=adapter,
        config_path=args.config,
        selected_preset=selected_preset,
        inline_overrides=list(args.set),
    )
    try:
        effective_config, applied_stage_override = apply_stage_overrides(
            composed_config,
            stage=args.stage,
        )
        invocation = adapter.build_invocation(effective_config)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    benchmark_label = str(benchmark_target) if benchmark_target is not None else None
    generation_context = build_proposal_generation_context(
        root=args.root,
        workspace=workspace,
        state=state,
        track_id=track_id,
        adapter_id=args.adapter,
        stage=args.stage,
        benchmark_target=benchmark_label,
        selected_preset=selected_preset,
        selected_preset_source=preset_source,
        policy_preset=policy_preset,
        effective_track_policy=track_policy.to_dict(),
        effective_config=effective_config,
        target_root=args.target_root,
    )
    failure_focus_task_ids = tuple(
        str(item)
        for item in getattr(args, "failure_focus_task_ids", ())
        if isinstance(item, str) and item
    )
    regressed_task_ids = tuple(
        str(item)
        for item in getattr(args, "regressed_task_ids", ())
        if isinstance(item, str) and item
    )
    if not failure_focus_task_ids and not regressed_task_ids:
        failure_focus_task_ids, regressed_task_ids = resolve_focus_task_ids(
            strategy_id=str(getattr(args, "generation_strategy_id", "direct")),
            candidate_index=int(getattr(args, "generation_candidate_index", 0)),
            latest_failure_summary=generation_context.latest_failure_summary,
            latest_regression_summary=generation_context.latest_regression_summary,
        )
    explicit_generation_metadata = {
        **dict(getattr(args, "generation_metadata", {})),
        **_parse_generator_options(list(getattr(args, "generator_option", []))),
    }
    provider_profile = resolve_provider_profile(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
        provider_id=requested_generator.generator_id,
    )
    provider_profile_summary = summarize_provider_profile(
        provider_id=requested_generator.generator_id,
        profile=provider_profile,
        explicit_metadata=explicit_generation_metadata,
    )
    generation_metadata = merge_provider_profile(
        explicit_metadata=explicit_generation_metadata,
        profile=provider_profile,
    )
    generation_request = ProposalGenerationRequest(
        format_version="autoharness.proposal_generation_request.v1",
        candidate_index=int(getattr(args, "generation_candidate_index", 0)),
        strategy_id=str(getattr(args, "generation_strategy_id", "direct")),
        source_mode=str(getattr(args, "generation_source_mode", "direct_cli")),
        campaign_run_id=(
            str(getattr(args, "campaign_run_id"))
            if getattr(args, "campaign_run_id", None) is not None
            else None
        ),
        intervention_class=(
            str(args.intervention_class)
            if getattr(args, "intervention_class", None) is not None
            else None
        ),
        input_edit_plan_path=str(args.edit_plan) if args.edit_plan is not None else None,
        failure_focus_task_ids=failure_focus_task_ids,
        regressed_task_ids=regressed_task_ids,
        hypothesis_seed=(
            str(getattr(args, "hypothesis_seed"))
            if getattr(args, "hypothesis_seed", None) is not None
            else None
        ),
        metadata=generation_metadata,
    )
    if requested_generator.generator_id == "manual" and args.edit_plan is None:
        raise SystemExit("The `manual` generator requires --edit-plan.")
    fallback_generator_ids = _parse_fallback_generator_ids(generation_metadata)
    attempt_generator_ids = (requested_generator.generator_id,) + tuple(
        generator_id
        for generator_id in fallback_generator_ids
        if generator_id != requested_generator.generator_id
    )
    generation_started = time.monotonic()
    generated = None
    generation_attempts: list[dict[str, object]] = []
    last_generation_error: ProposalGenerationError | None = None
    for generator_id in attempt_generator_ids:
        try:
            attempt_generator = get_generator(generator_id)
        except KeyError as exc:
            raise SystemExit(str(exc)) from exc
        attempt_started = time.monotonic()
        if attempt_generator.generator_id == "manual" and args.edit_plan is None:
            generation_attempts.append(
                {
                    "generator_id": generator_id,
                    "status": "error",
                    "error_type": "ProposalGenerationError",
                    "error": "The `manual` generator requires --edit-plan.",
                    "duration_seconds": time.monotonic() - attempt_started,
                }
            )
            continue
        try:
            generated = attempt_generator.generate(
                context=generation_context,
                request=generation_request,
                edit_plan_path=args.edit_plan,
            )
        except ProposalGenerationError as exc:
            last_generation_error = exc
            generation_attempts.append(
                {
                    "generator_id": generator_id,
                    "status": "error",
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                    "duration_seconds": time.monotonic() - attempt_started,
                }
            )
            continue
        generation_attempts.append(
            {
                "generator_id": generator_id,
                "status": "success",
                "duration_seconds": time.monotonic() - attempt_started,
            }
        )
        break
    if generated is None:
        append_workspace_event(
            root=args.root,
            workspace_id=args.workspace_id,
            track_id=track_id,
            campaign_run_id=generation_request.campaign_run_id,
            event_type="proposal_generation_failed",
            status="failed",
            generator_id=requested_generator.generator_id,
            provider_id=requested_generator.generator_id,
            adapter_id=args.adapter,
            benchmark_name=invocation.benchmark_name,
            details={
                "generator_attempts": generation_attempts,
                "provider_profile_summary": provider_profile_summary,
            },
        )
        if last_generation_error is not None:
            raise SystemExit(str(last_generation_error)) from last_generation_error
        raise SystemExit("Proposal generation did not produce a candidate.")
    generated_metadata = dict(generated.metadata)
    generated_metadata["generation_duration_seconds"] = (
        time.monotonic() - generation_started
    )
    generated_metadata["requested_generator_id"] = requested_generator.generator_id
    generated_metadata["generator_attempts"] = generation_attempts
    generated_metadata["fallback_chain"] = list(attempt_generator_ids)
    generated_metadata["fallback_used"] = generated.generator_id != requested_generator.generator_id
    generated_metadata["provider_profile_summary"] = provider_profile_summary
    try:
        edit_session = start_edit_session(
            plan=generated.edit_plan,
            target_root=args.target_root,
            policy=workspace.autonomy,
            preview_only=True,
            plan_path=args.edit_plan if args.edit_plan is not None else None,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    preview_application = edit_session.application.to_dict()
    preview_state = _preview_state_from_application(preview_application)
    hypothesis = (
        args.hypothesis
        or generated.hypothesis
        or _suggest_iteration_hypothesis(
            stage=args.stage,
            adapter_id=args.adapter,
            benchmark_target=benchmark_label,
            selected_preset=selected_preset,
        )
    )
    summary = args.summary or generated.summary or hypothesis
    proposal = create_proposal_record(
        workspace_id=args.workspace_id,
        track_id=track_id,
        adapter_id=args.adapter,
        benchmark_name=invocation.benchmark_name,
        stage=args.stage,
        hypothesis=hypothesis,
        notes=args.notes,
        generator_id=generated.generator_id,
        intervention_class=generated.intervention_class or generation_request.intervention_class,
        summary=summary,
        generator_metadata=generated_metadata,
        generation_context=generation_context.to_dict(),
        input_edit_plan_path=str(args.edit_plan) if args.edit_plan is not None else None,
        config_path=str(args.config) if args.config is not None else None,
        selected_preset=selected_preset,
        selected_preset_source=preset_source,
        policy_preset=policy_preset,
        benchmark_target=benchmark_label,
        inline_overrides=list(args.set),
        effective_config=effective_config,
        stage_policy=stage_policy.to_dict(),
        applied_stage_override=applied_stage_override,
        planned_invocation=invocation.to_dict(),
        target_root=args.target_root,
        preview_state=preview_state,
        operation_count=edit_session.application.operation_count,
        touched_paths=edit_session.application.touched_paths,
        preview_reasons=edit_session.application.reasons,
    )
    proposal, proposal_path = persist_proposal(
        root=args.root,
        proposal=proposal,
        edit_plan_payload=generated.edit_plan.to_dict(),
        preview_application_payload=preview_application,
        patch_text=edit_session.render_unified_diff(),
    )
    artifact_paths = resolve_proposal_artifact_paths(root=args.root, proposal=proposal)
    rendered = {
        "workspace_id": args.workspace_id,
        "track_id": track_id,
        "proposal": proposal.to_dict(),
        "generation_request": generation_request.to_dict(),
        "artifacts": artifact_paths,
    }
    append_workspace_event(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
        campaign_run_id=generation_request.campaign_run_id,
        proposal_id=proposal.proposal_id,
        event_type="proposal_generated",
        status="success",
        generator_id=proposal.generator_id,
        provider_id=requested_generator.generator_id,
        adapter_id=args.adapter,
        benchmark_name=proposal.benchmark_name,
        details={
            "preview_state": proposal.preview_state,
            "operation_count": proposal.operation_count,
            "provider_profile_summary": provider_profile_summary,
            "resource_usage": _generation_resource_usage(generated_metadata),
        },
    )

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Proposal: {proposal.proposal_id}")
    print(f"Adapter: {proposal.adapter_id}")
    print(f"Stage: {proposal.stage}")
    print(f"Benchmark: {proposal.benchmark_name}")
    print(f"Preview state: {proposal.preview_state}")
    print(f"Hypothesis: {proposal.hypothesis}")
    print(f"Operations: {proposal.operation_count}")
    print(f"Proposal path: {proposal_path}")
    if artifact_paths["patch_path"] is not None:
        print(f"Patch path: {artifact_paths['patch_path']}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_show_proposal(args: argparse.Namespace) -> int:
    args.workspace_id = _resolve_workspace_id(
        root=args.root,
        requested_workspace_id=args.workspace_id,
    )
    track_id, proposal = _resolve_saved_proposal(args)

    artifact_paths = resolve_proposal_artifact_paths(root=args.root, proposal=proposal)
    rendered = {
        "workspace_id": args.workspace_id,
        "track_id": track_id,
        "proposal": proposal.to_dict(),
        "edit_plan": load_proposal_edit_plan(root=args.root, proposal=proposal),
        "preview_application": load_proposal_preview_application(
            root=args.root,
            proposal=proposal,
        ),
        "artifacts": artifact_paths,
    }

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Proposal: {proposal.proposal_id}")
    print(f"Adapter: {proposal.adapter_id}")
    print(f"Stage: {proposal.stage}")
    print(f"Benchmark: {proposal.benchmark_name}")
    print(f"Preview state: {proposal.preview_state}")
    print(f"Hypothesis: {proposal.hypothesis}")
    if proposal.summary:
        print(f"Summary: {proposal.summary}")
    print(f"Target root: {proposal.target_root}")
    print(f"Operations: {proposal.operation_count}")
    print(f"Proposal path: {artifact_paths['proposal_path']}")
    if artifact_paths["patch_path"] is not None:
        print(f"Patch path: {artifact_paths['patch_path']}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_apply_proposal(args: argparse.Namespace) -> int:
    args.workspace_id = _resolve_workspace_id(
        root=args.root,
        requested_workspace_id=args.workspace_id,
    )
    track_id, proposal = _resolve_saved_proposal(args)
    workspace = load_workspace(args.root, args.workspace_id)
    target_root = args.target_root or Path(proposal.target_root)
    edit_plan = edit_plan_from_dict(
        load_proposal_edit_plan(root=args.root, proposal=proposal)
    )
    try:
        edit_session = start_edit_session(
            plan=edit_plan,
            target_root=target_root,
            policy=workspace.autonomy,
            preview_only=False,
            plan_path=Path(
                resolve_proposal_artifact_paths(root=args.root, proposal=proposal)["edit_plan_path"]
            ),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    edit_application = edit_session.application
    edit_restore = edit_session.finalize(keep_applied=True)
    rendered = {
        "workspace_id": args.workspace_id,
        "track_id": track_id,
        "proposal_id": proposal.proposal_id,
        "target_root": str(target_root.resolve()),
        "edit_application": edit_application.to_dict(),
        "edit_restore": edit_restore.to_dict(),
        "artifacts": resolve_proposal_artifact_paths(root=args.root, proposal=proposal),
    }

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Proposal: {proposal.proposal_id}")
    print(f"Target root: {target_root.resolve()}")
    print(f"Edit status: {edit_application.status}")
    print(f"Edit restore: {edit_restore.status}")
    if edit_application.touched_paths:
        print(f"Edited paths: {', '.join(edit_application.touched_paths)}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _build_run_iteration_args_from_proposal(
    *,
    proposal,
    args: argparse.Namespace,
    preflight_commands: list[str],
    preflight_timeout_seconds: int | None,
    repeat_count: int | None,
) -> argparse.Namespace:
    artifact_paths = resolve_proposal_artifact_paths(root=args.root, proposal=proposal)
    effective_config_path = artifact_paths["effective_config_path"]
    edit_plan_path = artifact_paths["edit_plan_path"]
    if effective_config_path is None or edit_plan_path is None:
        raise SystemExit(
            f"Proposal `{proposal.proposal_id}` is missing its effective-config or edit-plan artifact."
        )
    return argparse.Namespace(
        workspace_id=args.workspace_id,
        adapter=proposal.adapter_id,
        config=Path(effective_config_path),
        preset=None,
        set=[],
        hypothesis=proposal.hypothesis,
        notes=proposal.notes,
        edit_plan=Path(edit_plan_path),
        target_root=args.target_root or Path(proposal.target_root),
        keep_applied_edits=args.keep_applied_edits,
        staging_mode=args.staging_mode,
        track_id=proposal.track_id,
        root=args.root,
        dry_run=args.dry_run,
        source_plan_path=None,
        source_proposal_id=proposal.proposal_id,
        source_proposal_path=Path(artifact_paths["proposal_path"]),
        stage=proposal.stage,
        preflight_command=list(preflight_commands),
        preflight_timeout_seconds=preflight_timeout_seconds,
        repeat=repeat_count,
        seed_field=None,
        seed_start=0,
        seed_stride=1,
        baseline_source="none",
        baseline_record_id=None,
        min_success_rate=None,
        max_regressed_tasks=None,
        max_regressed_task_fraction=None,
        max_regressed_task_weight=None,
        max_regressed_task_weight_fraction=None,
        task_regression_margin=0.0,
        min_improvement=0.0,
        output=args.output,
    )


def _handle_run_proposal(args: argparse.Namespace) -> int:
    args.workspace_id = _resolve_workspace_id(
        root=args.root,
        requested_workspace_id=args.workspace_id,
    )
    track_id, proposal = _resolve_saved_proposal(args)
    load_proposal_effective_config(root=args.root, proposal=proposal)
    explicit_preflight_commands = list(getattr(args, "preflight_command", []))
    explicit_preflight_checks = list(getattr(args, "preflight_check", []))
    preflight_timeout_seconds = getattr(args, "preflight_timeout_seconds", None)
    repeat_count = getattr(args, "repeat", None)
    if (
        not explicit_preflight_commands
        and not explicit_preflight_checks
        or preflight_timeout_seconds is None
        or repeat_count is None
    ):
        workspace = load_workspace(args.root, args.workspace_id)
        from .mutations import _resolve_track_campaign_policy  # local import avoids cycle risk

        effective_campaign_policy, _ = _resolve_track_campaign_policy(
            workspace=workspace,
            track_id=track_id,
        )
        if not explicit_preflight_commands and not explicit_preflight_checks:
            explicit_preflight_commands = [
                str(entry)
                for entry in effective_campaign_policy.get("preflight_commands", [])
            ]
            explicit_preflight_checks = [
                str(entry)
                for entry in effective_campaign_policy.get("preflight_checks", [])
            ]
        if preflight_timeout_seconds is None:
            preflight_timeout_seconds = effective_campaign_policy.get(
                "preflight_timeout_seconds"
            )
        if repeat_count is None:
            repeat_count = effective_campaign_policy.get("repeat_count")
    try:
        preflight_commands = resolve_preflight_commands(
            commands=explicit_preflight_commands,
            checks=explicit_preflight_checks,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    run_iteration_args = _build_run_iteration_args_from_proposal(
        proposal=proposal,
        args=args,
        preflight_commands=preflight_commands,
        preflight_timeout_seconds=preflight_timeout_seconds,
        repeat_count=repeat_count,
    )
    return _handle_run_iteration(run_iteration_args)


def _handle_show_proposals(args: argparse.Namespace) -> int:
    (
        args.workspace_id,
        _,
        resolved_track_id,
        spec,
        rendered,
    ) = _prepare_proposal_listing(args)
    rendered_items = rendered["proposals"]
    non_executable_proposals_total = rendered["non_executable_proposals_total"]

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    item_lines = []
    for item in rendered_items:
        item_lines.append(
            f"- {item['proposal_id']}: "
            f"track={item['track_id']}, adapter={item['adapter_id']}, "
            f"stage={item['stage']}, state={item['preview_state']}, "
            f"ops={item['operation_count']}"
        )
    _emit_text_listing_output(
        workspace_id=args.workspace_id,
        collection_label="Proposals",
        collection_count=len(rendered_items),
        summary_label="Non-executable proposals",
        summary_count=non_executable_proposals_total,
        sort_by=spec.sort_by,
        descending=spec.descending,
        resolved_track_id=resolved_track_id,
        named_filters=[
            ("Stage filter", spec.stage),
            ("Adapter filter", spec.adapter_id),
            ("Hypothesis filter", spec.hypothesis_contains),
            ("Notes filter", spec.notes_contains),
            ("Since filter", spec.since),
            ("Until filter", spec.until),
        ],
        enabled_filters=[],
        extra_lines=[],
        item_lines=item_lines,
        output=args.output,
    )
    return 0


def _handle_export_proposals(args: argparse.Namespace) -> int:
    args.workspace_id, _, _, _, rendered = _prepare_proposal_listing(args)
    output_format = _export_listing_payload(
        output=args.output,
        explicit_format=args.format,
        format_version="autoharness.proposal_export.v1",
        rendered=rendered,
        exported_at=_utc_now(),
    )

    print(f"Workspace: {args.workspace_id}")
    print(f"Proposals exported: {len(rendered['proposals'])}")
    print(f"Non-executable proposals: {rendered['non_executable_proposals_total']}")
    print(f"Format: {output_format}")
    print(f"Export path: {args.output}")
    return 0
