import json
import sys
from pathlib import Path

import pytest
import yaml

from autoharness.cli import main
from autoharness.tracking import (
    create_benchmark_record,
    create_promotion_record,
    load_benchmark_record,
    load_champion_manifest,
    load_workspace_state,
    persist_benchmark_record,
    persist_champion_manifest,
    persist_promotion_record,
    update_state_after_promotion,
)


def test_setup_defaults_to_full(tmp_path: Path) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    exit_code = main(["setup", "--output", str(settings)])
    assert exit_code == 0

    payload = yaml.safe_load(settings.read_text(encoding="utf-8"))
    assert payload["autonomy"]["mode"] == "full"
    assert payload["autonomy"]["allows_repo_wide_edits"] is True


def test_init_workspace_uses_settings(tmp_path: Path) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(
        [
            "setup",
            "--output",
            str(settings),
            "--autonomy",
            "bounded",
            "--editable-surface",
            "src/agent",
        ]
    )

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    exit_code = main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )
    assert exit_code == 0

    workspace_path = workspaces_root / "demo"
    workspace = json.loads((workspace_path / "workspace.json").read_text("utf-8"))
    campaign = json.loads(
        (workspace_path / "tracks" / "main" / "campaign.json").read_text("utf-8")
    )
    promotion_policy = json.loads(
        (workspace_path / "tracks" / "main" / "promotion_policy.json").read_text("utf-8")
    )
    track_policy = json.loads(
        (workspace_path / "tracks" / "main" / "track_policy.json").read_text("utf-8")
    )

    assert workspace["autonomy"]["mode"] == "bounded"
    assert workspace["tracks"]["main"]["benchmark"] == "tau-bench-airline"
    assert campaign["campaign_id"] == "demo_main"
    assert promotion_policy["track_id"] == "main"
    assert promotion_policy["min_improvement"] == 0.0
    assert track_policy["track_id"] == "main"
    assert track_policy["search_benchmark"] == "tau-bench-airline"
    assert track_policy["promotion_benchmark"] == "tau-bench-airline"
    assert track_policy["regression_benchmark"] == "tau-bench-airline"
    assert track_policy["search_preset"] is None
    assert track_policy["promotion_preset"] is None
    assert track_policy["regression_preset"] is None


def test_init_alias_and_report_alias_support_single_workspace_flow(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    capsys.readouterr()
    assert main(["report", "--root", str(workspaces_root), "--json"]) == 0
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["workspace_id"] == "demo"
    assert rendered["counts"]["tracks_total"] == 1


def test_show_and_set_promotion_policy_commands(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    show_output_path = tmp_path / "promotion_policy.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-promotion-policy",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(show_output_path),
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["track_id"] == "main"
    assert shown["min_improvement"] == 0.0
    assert json.loads(show_output_path.read_text(encoding="utf-8")) == shown

    set_output_path = tmp_path / "updated_policy.json"
    assert (
        main(
            [
                "set-promotion-policy",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--stage",
                "holdout",
                "--min-improvement",
                "0.2",
                "--max-regressed-tasks",
                "1",
                "--notes",
                "Tighten champion promotion",
                "--output",
                str(set_output_path),
            ]
        )
        == 0
    )
    updated = json.loads(set_output_path.read_text(encoding="utf-8"))
    assert updated["stage"] == "holdout"
    assert updated["min_improvement"] == 0.2
    assert updated["max_regressed_tasks"] == 1
    assert updated["notes"] == "Tighten champion promotion"

    persisted = json.loads(
        (
            workspaces_root / "demo" / "tracks" / "main" / "promotion_policy.json"
        ).read_text(encoding="utf-8")
    )
    assert persisted == updated


def test_show_and_set_track_policy_commands(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    show_output_path = tmp_path / "track_policy.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-track-policy",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(show_output_path),
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["track_id"] == "main"
    assert shown["search_benchmark"] == "tau-bench-airline"
    assert shown["promotion_benchmark"] == "tau-bench-airline"
    assert shown["regression_benchmark"] == "tau-bench-airline"
    assert shown["search_preset"] is None
    assert shown["promotion_preset"] is None
    assert shown["regression_preset"] is None
    assert shown["raw_policy_exists"] is True
    assert shown["effective_sources"]["search_benchmark"] == "track_policy"
    assert shown["effective_sources"]["promotion_preset"] == "unset"
    assert json.loads(show_output_path.read_text(encoding="utf-8")) == shown

    main(
        [
            "set-workspace",
            "--workspace-id",
            "demo",
            "--root",
            str(workspaces_root),
            "--promotion-preset",
            "promotion",
        ]
    )
    fallback_output_path = tmp_path / "track_policy_fallback.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-track-policy",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(fallback_output_path),
            ]
        )
        == 0
    )
    fallback_rendered = json.loads(capsys.readouterr().out)
    assert fallback_rendered["promotion_preset"] == "promotion"
    assert fallback_rendered["raw_policy"]["promotion_preset"] is None
    assert fallback_rendered["effective_sources"]["promotion_preset"] == "workspace_fallback"
    assert json.loads(fallback_output_path.read_text(encoding="utf-8")) == fallback_rendered

    set_output_path = tmp_path / "updated_track_policy.json"
    assert (
        main(
            [
                "set-track-policy",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--promotion-benchmark",
                "custom-holdout",
                "--regression-benchmark",
                "custom-regression",
                "--search-preset",
                "search",
                "--promotion-preset",
                "promotion",
                "--notes",
                "Route holdout and regression elsewhere",
                "--output",
                str(set_output_path),
            ]
        )
        == 0
    )
    updated = json.loads(set_output_path.read_text(encoding="utf-8"))
    assert updated["search_benchmark"] == "tau-bench-airline"
    assert updated["promotion_benchmark"] == "custom-holdout"
    assert updated["regression_benchmark"] == "custom-regression"
    assert updated["search_preset"] == "search"
    assert updated["promotion_preset"] == "promotion"
    assert updated["regression_preset"] is None
    assert updated["notes"] == "Route holdout and regression elsewhere"

    persisted = json.loads(
        (workspaces_root / "demo" / "tracks" / "main" / "track_policy.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted == updated


def test_show_and_set_track_commands(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    show_output_path = tmp_path / "track.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-track",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(show_output_path),
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["track_id"] == "main"
    assert shown["objective"] == "Improve harness correctness"
    assert shown["kind"] == "search"
    assert shown["campaign_policy"] == {}
    assert shown["effective_campaign_policy"]["effective_policy"]["generator_id"] == "manual"
    assert (
        shown["effective_campaign_policy"]["effective_sources"]["generator_id"]
        == "built_in"
    )
    assert shown["evaluator"]["judge_model"] == "gpt-4.1-mini"
    assert json.loads(show_output_path.read_text(encoding="utf-8")) == shown

    set_output_path = tmp_path / "updated_track.json"
    assert (
        main(
            [
                "set-track",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--objective",
                "Improve airline support outcomes",
                "--kind",
                "holdout",
                "--benchmark-reference-id",
                "tau2-public-v1",
                "--benchmark-reference-id",
                "airline-regression-v3",
                "--evaluator-version",
                "2026-04-17",
                "--judge-model",
                "gpt-5.4",
                "--diagnostic-model",
                "gpt-5.4-mini",
                "--max-diagnostic-tasks",
                "12",
                "--min-judge-pass-rate",
                "0.7",
                "--campaign-generator",
                "failure_summary",
                "--campaign-strategy",
                "greedy_failure_focus",
                "--campaign-stage-progression",
                "advance_on_success",
                "--campaign-beam-groups",
                "2",
                "--campaign-generator-option",
                "model=gpt-5.1",
                "--campaign-intervention-class",
                "source",
                "--campaign-max-iterations",
                "5",
                "--campaign-max-successes",
                "2",
                "--campaign-max-promotions",
                "1",
                "--campaign-auto-promote",
                "--campaign-auto-promote-min-stage",
                "holdout",
                "--notes",
                "Pinned operator-updated evaluator settings",
                "--output",
                str(set_output_path),
            ]
        )
        == 0
    )
    updated = json.loads(set_output_path.read_text(encoding="utf-8"))
    assert updated["objective"] == "Improve airline support outcomes"
    assert updated["kind"] == "holdout"
    assert updated["benchmark_reference_ids"] == [
        "tau2-public-v1",
        "airline-regression-v3",
    ]
    assert updated["evaluator"]["evaluator_version"] == "2026-04-17"
    assert updated["evaluator"]["judge_model"] == "gpt-5.4"
    assert updated["evaluator"]["diagnostic_model"] == "gpt-5.4-mini"
    assert updated["evaluator"]["max_diagnostic_tasks"] == 12
    assert updated["evaluator"]["min_judge_pass_rate"] == 0.7
    assert updated["campaign_policy"]["generator_id"] == "failure_summary"
    assert updated["campaign_policy"]["strategy"] == "greedy_failure_focus"
    assert updated["campaign_policy"]["stage_progression_mode"] == "advance_on_success"
    assert updated["campaign_policy"]["beam_group_limit"] == 2
    assert updated["campaign_policy"]["generator_metadata"] == {"model": "gpt-5.1"}
    assert updated["campaign_policy"]["intervention_classes"] == ["source"]
    assert updated["campaign_policy"]["max_iterations"] == 5
    assert updated["campaign_policy"]["max_successes"] == 2
    assert updated["campaign_policy"]["max_promotions"] == 1
    assert updated["campaign_policy"]["auto_promote"] is True
    assert updated["campaign_policy"]["auto_promote_min_stage"] == "holdout"
    assert updated["notes"] == "Pinned operator-updated evaluator settings"

    workspace = json.loads(
        (workspaces_root / "demo" / "workspace.json").read_text(encoding="utf-8")
    )
    campaign = json.loads(
        (workspaces_root / "demo" / "tracks" / "main" / "campaign.json").read_text(
            encoding="utf-8"
        )
    )
    assert workspace["tracks"]["main"] == updated
    assert campaign == updated

    assert (
        main(
            [
                "set-track",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--clear-benchmark-reference-ids",
                "--clear-notes",
            ]
        )
        == 0
    )
    cleared = json.loads(
        (workspaces_root / "demo" / "tracks" / "main" / "campaign.json").read_text(
            encoding="utf-8"
        )
    )
    assert cleared["benchmark_reference_ids"] == []
    assert cleared["notes"] == ""


def test_show_and_set_workspace_commands(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    workspace_root = workspaces_root / "demo"
    workspace_path = workspace_root / "workspace.json"
    state_path = workspace_root / "state.json"
    alt_campaign_path = workspace_root / "tracks" / "alt" / "campaign.json"

    workspace_payload = json.loads(workspace_path.read_text(encoding="utf-8"))
    alt_track = dict(workspace_payload["tracks"]["main"])
    alt_track["track_id"] = "alt"
    alt_track["campaign_id"] = "demo_alt"
    alt_track["objective"] = "Alternate promotion lane"
    workspace_payload["tracks"]["alt"] = alt_track
    workspace_path.write_text(json.dumps(workspace_payload, indent=2) + "\n", encoding="utf-8")
    alt_campaign_path.parent.mkdir(parents=True, exist_ok=True)
    alt_campaign_path.write_text(json.dumps(alt_track, indent=2) + "\n", encoding="utf-8")

    show_output_path = tmp_path / "workspace.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-workspace",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(show_output_path),
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["workspace_id"] == "demo"
    assert shown["objective"] == "Improve harness correctness"
    assert shown["active_track_id"] == "main"
    assert shown["state"]["active_track_id"] == "main"
    assert shown["autonomy"]["mode"] == "full"
    assert shown["active_track_effective_policy"]["track_id"] == "main"
    assert shown["campaign_policy"] == {}
    assert (
        shown["active_track_effective_campaign_policy"]["effective_policy"]["generator_id"]
        == "manual"
    )
    assert (
        shown["active_track_effective_campaign_policy"]["effective_sources"][
            "generator_id"
        ]
        == "built_in"
    )
    assert (
        shown["active_track_effective_policy"]["effective_sources"]["search_benchmark"]
        == "track_policy"
    )
    assert (
        shown["active_track_effective_policy"]["effective_sources"]["promotion_preset"]
        == "unset"
    )
    assert json.loads(show_output_path.read_text(encoding="utf-8")) == shown

    set_output_path = tmp_path / "updated_workspace.json"
    assert (
        main(
            [
                "set-workspace",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--objective",
                "Improve airline support outcomes",
                "--domain",
                "airline",
                "--active-track-id",
                "alt",
                "--promotion-benchmark",
                "tau-bench-airline-holdout",
                "--regression-benchmark",
                "tau-bench-airline-regression",
                "--promotion-preset",
                "promotion",
                "--regression-preset",
                "promotion",
                "--campaign-stage",
                "holdout",
                "--campaign-generator",
                "failure_summary",
                "--campaign-strategy",
                "greedy_failure_focus",
                "--campaign-stage-progression",
                "advance_on_promotion",
                "--campaign-beam-groups",
                "3",
                "--campaign-generator-option",
                "model=gpt-5.2",
                "--campaign-generator-option",
                "reasoning_effort=low",
                "--campaign-intervention-class",
                "config",
                "--campaign-intervention-class",
                "source",
                "--campaign-max-iterations",
                "4",
                "--campaign-max-successes",
                "3",
                "--campaign-max-promotions",
                "2",
                "--campaign-auto-promote",
                "--campaign-auto-promote-min-stage",
                "validation",
                "--notes",
                "Pinned workspace-level fallback routing",
                "--output",
                str(set_output_path),
            ]
        )
        == 0
    )
    updated = json.loads(set_output_path.read_text(encoding="utf-8"))
    assert updated["objective"] == "Improve airline support outcomes"
    assert updated["domain"] == "airline"
    assert updated["active_track_id"] == "alt"
    assert updated["benchmark_policy"]["search_benchmark"] == "tau-bench-airline"
    assert updated["benchmark_policy"]["promotion_benchmark"] == "tau-bench-airline-holdout"
    assert updated["benchmark_policy"]["regression_benchmark"] == "tau-bench-airline-regression"
    assert updated["benchmark_policy"].get("search_preset") is None
    assert updated["benchmark_policy"]["promotion_preset"] == "promotion"
    assert updated["benchmark_policy"]["regression_preset"] == "promotion"
    assert updated["campaign_policy"]["stage"] == "holdout"
    assert updated["campaign_policy"]["generator_id"] == "failure_summary"
    assert updated["campaign_policy"]["strategy"] == "greedy_failure_focus"
    assert updated["campaign_policy"]["stage_progression_mode"] == "advance_on_promotion"
    assert updated["campaign_policy"]["beam_group_limit"] == 3
    assert updated["campaign_policy"]["generator_metadata"] == {
        "model": "gpt-5.2",
        "reasoning_effort": "low",
    }
    assert updated["campaign_policy"]["intervention_classes"] == ["config", "source"]
    assert updated["campaign_policy"]["max_iterations"] == 4
    assert updated["campaign_policy"]["max_successes"] == 3
    assert updated["campaign_policy"]["max_promotions"] == 2
    assert updated["campaign_policy"]["auto_promote"] is True
    assert updated["campaign_policy"]["auto_promote_min_stage"] == "validation"
    assert updated["notes"] == "Pinned workspace-level fallback routing"

    persisted_workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    persisted_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted_workspace == updated
    assert persisted_state["active_track_id"] == "alt"

    active_track_output_path = tmp_path / "workspace_active_track.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-workspace",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(active_track_output_path),
            ]
        )
        == 0
    )
    active_track_rendered = json.loads(capsys.readouterr().out)
    assert active_track_rendered["active_track_id"] == "alt"
    assert active_track_rendered["state"]["active_track_id"] == "alt"
    assert active_track_rendered["active_track_effective_policy"]["track_id"] == "alt"
    assert (
        active_track_rendered["active_track_effective_campaign_policy"][
            "effective_sources"
        ]["generator_id"]
        == "workspace_default"
    )
    assert (
        active_track_rendered["active_track_effective_campaign_policy"][
            "effective_policy"
        ]["stage"]
        == "holdout"
    )
    assert (
        active_track_rendered["active_track_effective_campaign_policy"][
            "effective_policy"
        ]["beam_group_limit"]
        == 3
    )
    assert (
        active_track_rendered["active_track_effective_campaign_policy"][
            "effective_sources"
        ]["beam_group_limit"]
        == "workspace_default"
    )
    assert (
        active_track_rendered["active_track_effective_campaign_policy"][
            "effective_policy"
        ]["intervention_classes"]
        == ["config", "source"]
    )
    assert (
        active_track_rendered["active_track_effective_policy"]["effective_sources"][
            "promotion_preset"
        ]
        == "workspace_fallback"
    )
    assert (
        active_track_rendered["active_track_effective_policy"]["effective_sources"][
            "promotion_benchmark"
        ]
        == "workspace_fallback"
    )
    assert (
        active_track_rendered["active_track_effective_policy"]["effective_policy"][
            "promotion_preset"
        ]
        == "promotion"
    )
    assert json.loads(
        active_track_output_path.read_text(encoding="utf-8")
    ) == active_track_rendered

    assert (
        main(
            [
                "set-workspace",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--clear-notes",
            ]
        )
        == 0
    )
    cleared = json.loads(workspace_path.read_text(encoding="utf-8"))
    assert cleared["notes"] == ""


def test_archive_and_purge_workspace_commands(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    assert (
        main(
            [
                "create-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "set-workspace",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--campaign-generator",
                "failure_summary",
                "--campaign-strategy",
                "beam_interventions",
                "--campaign-beam-width",
                "2",
                "--campaign-beam-groups",
                "3",
                "--campaign-max-generation-timeout-retries",
                "5",
                "--campaign-max-generation-provider-retries",
                "6",
                "--campaign-max-generation-provider-transport-retries",
                "8",
                "--campaign-max-generation-provider-auth-retries",
                "9",
                "--campaign-max-generation-provider-rate-limit-retries",
                "10",
                "--campaign-max-generation-process-retries",
                "7",
                "--campaign-max-benchmark-timeout-retries",
                "11",
                "--campaign-max-benchmark-command-retries",
                "2",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "set-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
                "--campaign-strategy",
                "regression_first",
                "--campaign-beam-groups",
                "4",
            ]
        )
        == 0
    )

    archive_output_path = tmp_path / "archive_workspace.json"
    assert (
        main(
            [
                "archive-workspace",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(archive_output_path),
            ]
        )
        == 0
    )
    archived = json.loads(archive_output_path.read_text(encoding="utf-8"))
    assert archived["workspace_id"] == "demo"
    assert archived["status"] == "archived"
    assert archived["tracks_total"] == 2

    state_path = workspaces_root / "demo" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "archived"

    capsys.readouterr()
    assert (
        main(
            [
                "show-workspace",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["state"]["status"] == "archived"

    with pytest.raises(SystemExit, match="archived and cannot be modified"):
        main(
            [
                "create-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "third",
                "--root",
                str(workspaces_root),
            ]
        )

    with pytest.raises(SystemExit, match="exactly match"):
        main(
            [
                "purge-workspace",
                "--workspace-id",
                "demo",
                "--confirm-workspace-id",
                "wrong",
                "--root",
                str(workspaces_root),
            ]
        )

    purge_output_path = tmp_path / "purge_workspace.json"
    assert (
        main(
            [
                "purge-workspace",
                "--workspace-id",
                "demo",
                "--confirm-workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(purge_output_path),
            ]
        )
        == 0
    )
    purged = json.loads(purge_output_path.read_text(encoding="utf-8"))
    assert purged["purged_workspace_id"] == "demo"
    assert purged["removed_tracks_total"] == 2
    assert purged["removed_iterations_total"] == 0
    assert purged["removed_records_total"] == 0
    assert purged["removed_promotions_total"] == 0
    assert purged["removed_champion_tracks_total"] == 0
    assert not (workspaces_root / "demo").exists()




def test_show_create_and_switch_track_commands(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    show_output_path = tmp_path / "tracks.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-tracks",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(show_output_path),
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["active_track_id"] == "main"
    assert shown["state_active_track_id"] == "main"
    assert [item["track_id"] for item in shown["tracks"]] == ["main"]
    assert shown["tracks"][0]["active"] is True
    assert json.loads(show_output_path.read_text(encoding="utf-8")) == shown

    create_output_path = tmp_path / "alt_track.json"
    assert (
        main(
            [
                "create-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
                "--benchmark",
                "tau-bench-retail",
                "--objective",
                "Improve retail support outcomes",
                "--kind",
                "holdout",
                "--benchmark-reference-id",
                "tau2-retail-v1",
                "--judge-model",
                "gpt-5.4",
                "--output",
                str(create_output_path),
            ]
        )
        == 0
    )
    created = json.loads(create_output_path.read_text(encoding="utf-8"))
    assert created["track_id"] == "alt"
    assert created["status"] == "active"
    assert created["benchmark"] == "tau-bench-retail"
    assert created["objective"] == "Improve retail support outcomes"
    assert created["kind"] == "holdout"
    assert created["benchmark_reference_ids"] == ["tau2-retail-v1"]
    assert created["evaluator"]["judge_model"] == "gpt-5.4"
    assert created["evaluator"]["diagnostic_model"] == "gpt-4.1-mini"

    workspace_root = workspaces_root / "demo"
    workspace = json.loads((workspace_root / "workspace.json").read_text(encoding="utf-8"))
    state = json.loads((workspace_root / "state.json").read_text(encoding="utf-8"))
    alt_campaign = json.loads(
        (workspace_root / "tracks" / "alt" / "campaign.json").read_text(encoding="utf-8")
    )
    alt_promotion_policy = json.loads(
        (
            workspace_root / "tracks" / "alt" / "promotion_policy.json"
        ).read_text(encoding="utf-8")
    )
    alt_track_policy = json.loads(
        (workspace_root / "tracks" / "alt" / "track_policy.json").read_text(
            encoding="utf-8"
        )
    )
    assert workspace["tracks"]["alt"] == created
    assert alt_campaign == created
    assert state["active_track_id"] == "main"
    assert state["summary"]["tracks_total"] == 2
    assert alt_promotion_policy["track_id"] == "alt"
    assert alt_track_policy["track_id"] == "alt"
    assert alt_track_policy["search_benchmark"] == "tau-bench-retail"
    assert alt_track_policy["search_preset"] is None

    switch_output_path = tmp_path / "switch_track.json"
    assert (
        main(
            [
                "switch-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
                "--output",
                str(switch_output_path),
            ]
        )
        == 0
    )
    switched = json.loads(switch_output_path.read_text(encoding="utf-8"))
    assert switched["previous_active_track_id"] == "main"
    assert switched["active_track_id"] == "alt"

    workspace = json.loads((workspace_root / "workspace.json").read_text(encoding="utf-8"))
    state = json.loads((workspace_root / "state.json").read_text(encoding="utf-8"))
    assert workspace["active_track_id"] == "alt"
    assert state["active_track_id"] == "alt"

    capsys.readouterr()
    assert (
        main(
            [
                "show-tracks",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    updated_listing = json.loads(capsys.readouterr().out)
    assert [item["track_id"] for item in updated_listing["tracks"]] == ["alt", "main"]
    active_track = next(item for item in updated_listing["tracks"] if item["track_id"] == "alt")
    assert active_track["active"] is True
    assert active_track["status"] == "active"


def test_archive_track_command(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "create-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    archive_output_path = tmp_path / "archive_track.json"
    assert (
        main(
            [
                "archive-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(archive_output_path),
            ]
        )
        == 0
    )
    archived = json.loads(archive_output_path.read_text(encoding="utf-8"))
    assert archived["track_id"] == "main"
    assert archived["status"] == "archived"
    assert archived["replacement_track_id"] == "alt"
    assert archived["active_track_id"] == "alt"

    workspace_root = workspaces_root / "demo"
    workspace = json.loads((workspace_root / "workspace.json").read_text(encoding="utf-8"))
    state = json.loads((workspace_root / "state.json").read_text(encoding="utf-8"))
    main_campaign = json.loads(
        (workspace_root / "tracks" / "main" / "campaign.json").read_text(encoding="utf-8")
    )
    assert workspace["tracks"]["main"]["status"] == "archived"
    assert main_campaign["status"] == "archived"
    assert workspace["active_track_id"] == "alt"
    assert state["active_track_id"] == "alt"
    assert state["summary"]["tracks_total"] == 2
    assert state["summary"]["active_tracks_total"] == 1
    assert state["summary"]["archived_tracks_total"] == 1

    capsys.readouterr()
    assert (
        main(
            [
                "show-tracks",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    listing = json.loads(capsys.readouterr().out)
    archived_track = next(item for item in listing["tracks"] if item["track_id"] == "main")
    assert archived_track["status"] == "archived"
    assert archived_track["active"] is False

    with pytest.raises(SystemExit, match="archived"):
        main(
            [
                "switch-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
            ]
        )


def test_purge_track_command(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "create-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    alt_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="alt-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "alt-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="alt",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=alt_record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="alt",
        record=alt_record,
        target_root=tmp_path / "target",
        notes="Promote the archived candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=alt_record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    iteration_dir = workspaces_root / "demo" / "iterations" / "iter_0001"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    (iteration_dir / "summary.json").write_text(
        json.dumps(
            {
                "iteration_id": "iter_0001",
                "workspace_id": "demo",
                "track_id": "alt",
                "record_id": alt_record.record_id,
                "adapter_id": alt_record.adapter_id,
                "benchmark_name": alt_record.benchmark_name,
                "stage": "validation",
                "created_at": alt_record.created_at,
                "status": alt_record.status,
                "dry_run": alt_record.dry_run,
                "success": alt_record.success,
                "hypothesis": alt_record.hypothesis,
                "notes": alt_record.notes,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    state_path = workspaces_root / "demo" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["last_iteration_id"] = "iter_0001"
    state["last_experiment_id"] = alt_record.record_id
    state["current_champion_experiment_id"] = alt_record.record_id
    state["summary"]["iterations_total"] = 1
    state["summary"]["promotions_total"] = 1
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="must be archived"):
        main(
            [
                "purge-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--confirm-track-id",
                "alt",
                "--root",
                str(workspaces_root),
            ]
        )

    assert (
        main(
            [
                "archive-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    with pytest.raises(SystemExit, match="exactly match"):
        main(
            [
                "purge-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--confirm-track-id",
                "wrong",
                "--root",
                str(workspaces_root),
            ]
        )

    purge_output_path = tmp_path / "purge_track.json"
    assert (
        main(
            [
                "purge-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--confirm-track-id",
                "alt",
                "--root",
                str(workspaces_root),
                "--output",
                str(purge_output_path),
            ]
        )
        == 0
    )
    purged = json.loads(purge_output_path.read_text(encoding="utf-8"))
    assert purged["purged_track_id"] == "alt"
    assert purged["removed_records_total"] == 1
    assert purged["removed_promotions_total"] == 1
    assert purged["removed_champion_manifest"] is True
    assert purged["purged_iteration_ids"] == ["iter_0001"]
    assert purged["remaining_tracks_total"] == 1
    assert purged["active_track_id"] == "main"

    workspace = json.loads((workspaces_root / "demo" / "workspace.json").read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert list(workspace["tracks"]) == ["main"]
    assert workspace["active_track_id"] == "main"
    assert state["active_track_id"] == "main"
    assert state["summary"]["tracks_total"] == 1
    assert state["summary"]["active_tracks_total"] == 1
    assert state["summary"]["archived_tracks_total"] == 0
    assert state["summary"]["iterations_total"] == 0
    assert state["summary"]["promotions_total"] == 0
    assert state["last_iteration_id"] is None
    assert state["last_experiment_id"] is None
    assert state["current_champion_experiment_id"] is None
    assert not (workspaces_root / "demo" / "tracks" / "alt").exists()
    assert not iteration_dir.exists()

    capsys.readouterr()
    assert (
        main(
            [
                "show-tracks",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    listing = json.loads(capsys.readouterr().out)
    assert [item["track_id"] for item in listing["tracks"]] == ["main"]



def test_show_track_summary_command(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text('{"pass_rate": 1.0}\n', encoding="utf-8")
    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
            "parsed_artifact_sources": {
                "metrics": [
                    {
                        "origin": "metrics_parser.path",
                        "path": str(metrics_path.resolve()),
                    }
                ]
            },
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        hypothesis="Keep the smoke command passing",
        stage="validation",
        source_plan_path=str((tmp_path / "planned_track_summary.json").resolve()),
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )
    assert (
        main(
            [
                "set-workspace",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--campaign-generator",
                "failure_summary",
                "--campaign-strategy",
                "beam_interventions",
                "--campaign-beam-width",
                "2",
                "--campaign-beam-groups",
                "3",
                "--campaign-max-generation-timeout-retries",
                "5",
                "--campaign-max-generation-provider-retries",
                "6",
                "--campaign-max-generation-provider-transport-retries",
                "8",
                "--campaign-max-generation-provider-auth-retries",
                "9",
                "--campaign-max-generation-provider-rate-limit-retries",
                "10",
                "--campaign-max-generation-process-retries",
                "7",
                "--campaign-max-benchmark-timeout-retries",
                "11",
                "--campaign-max-benchmark-command-retries",
                "2",
            ]
        )
        == 0
    )

    summary_output_path = tmp_path / "track_summary.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-track-summary",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(summary_output_path),
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["workspace_id"] == "demo"
    assert summary["track_id"] == "main"
    assert summary["active"] is True
    assert summary["status"] == "active"
    assert summary["records"]["total"] == 1
    assert summary["records"]["by_status"]["success"] == 1
    assert summary["records"]["by_stage"]["validation"] == 1
    assert summary["records"]["source_plan_total"] == 1
    assert summary["records"]["source_plan_by_stage"]["validation"] == 1
    assert summary["promotions"]["total"] == 1
    assert (
        summary["effective_campaign_policy"]["effective_policy"]["generator_id"]
        == "failure_summary"
    )
    assert (
        summary["effective_campaign_policy"]["effective_policy"]["strategy"]
        == "beam_interventions"
    )
    assert summary["effective_campaign_policy"]["effective_policy"]["beam_width"] == 2
    assert (
        summary["effective_campaign_policy"]["effective_policy"]["beam_group_limit"]
        == 3
    )
    assert (
        summary["effective_campaign_policy"]["effective_policy"][
            "max_generation_timeout_retries"
        ]
        == 5
    )
    assert (
        summary["effective_campaign_policy"]["effective_sources"][
            "max_generation_timeout_retries"
        ]
        == "workspace_default"
    )
    assert (
        summary["effective_campaign_policy"]["effective_policy"][
            "max_generation_provider_retries"
        ]
        == 6
    )
    assert (
        summary["effective_campaign_policy"]["effective_policy"][
            "max_generation_provider_transport_retries"
        ]
        == 8
    )
    assert (
        summary["effective_campaign_policy"]["effective_policy"][
            "max_generation_provider_auth_retries"
        ]
        == 9
    )
    assert (
        summary["effective_campaign_policy"]["effective_policy"][
            "max_generation_provider_rate_limit_retries"
        ]
        == 10
    )
    assert (
        summary["effective_campaign_policy"]["effective_policy"][
            "max_generation_process_retries"
        ]
        == 7
    )
    assert (
        summary["effective_campaign_policy"]["effective_policy"][
            "max_benchmark_timeout_retries"
        ]
        == 11
    )
    assert (
        summary["effective_campaign_policy"]["effective_policy"][
            "max_benchmark_command_retries"
        ]
        == 2
    )
    assert (
        summary["effective_campaign_policy"]["effective_sources"]["beam_group_limit"]
        == "workspace_default"
    )
    assert (
        summary["effective_campaign_policy"]["effective_sources"][
            "max_benchmark_timeout_retries"
        ]
        == "workspace_default"
    )
    assert (
        summary["effective_campaign_policy"]["effective_sources"][
            "max_benchmark_command_retries"
        ]
        == "workspace_default"
    )
    assert summary["champion"]["record_id"] == record.record_id
    assert summary["records"]["latest"]["record_id"] == record.record_id
    assert summary["records"]["latest"]["source_plan_path"] == str(
        (tmp_path / "planned_track_summary.json").resolve()
    )
    assert summary["promotions"]["latest"]["promotion_id"] == promotion.promotion_id
    assert json.loads(summary_output_path.read_text(encoding="utf-8")) == summary


def test_show_workspace_summary_command(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "create-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
                "--benchmark",
                "tau-bench-retail",
                "--objective",
                "Improve retail support outcomes",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "set-workspace",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--campaign-generator",
                "failure_summary",
                "--campaign-strategy",
                "beam_interventions",
                "--campaign-beam-width",
                "2",
                "--campaign-beam-groups",
                "3",
                "--campaign-max-generation-timeout-retries",
                "5",
                "--campaign-max-generation-provider-retries",
                "6",
                "--campaign-max-generation-provider-transport-retries",
                "8",
                "--campaign-max-generation-provider-auth-retries",
                "9",
                "--campaign-max-generation-provider-rate-limit-retries",
                "10",
                "--campaign-max-generation-process-retries",
                "7",
                "--campaign-max-benchmark-command-retries",
                "2",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "set-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
                "--campaign-strategy",
                "regression_first",
                "--campaign-beam-groups",
                "4",
            ]
        )
        == 0
    )

    main_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
        source_plan_path=str((tmp_path / "planned_workspace_summary.json").resolve()),
    )
    alt_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="alt-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "alt-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": False,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="alt",
        iteration_id="iter_0002",
        stage="screening",
    )
    persist_benchmark_record(root=workspaces_root, record=main_record)
    persist_benchmark_record(root=workspaces_root, record=alt_record)

    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=main_record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=main_record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    iterations_root = workspaces_root / "demo" / "iterations"
    for iteration_id, record, stage in [
        ("iter_0001", main_record, "validation"),
        ("iter_0002", alt_record, "screening"),
    ]:
        iteration_dir = iterations_root / iteration_id
        iteration_dir.mkdir(parents=True, exist_ok=True)
        (iteration_dir / "summary.json").write_text(
            json.dumps(
                {
                    "iteration_id": iteration_id,
                    "workspace_id": "demo",
                    "track_id": record.track_id,
                    "record_id": record.record_id,
                    "adapter_id": record.adapter_id,
                    "benchmark_name": record.benchmark_name,
                    "stage": stage,
                    "created_at": record.created_at,
                    "status": record.status,
                    "dry_run": record.dry_run,
                    "success": record.success,
                    "hypothesis": record.hypothesis,
                    "notes": record.notes,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    state_path = workspaces_root / "demo" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["last_iteration_id"] = "iter_0002"
    state["last_experiment_id"] = alt_record.record_id
    state["current_champion_experiment_id"] = main_record.record_id
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    output_path = tmp_path / "workspace_summary.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-workspace-summary",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["workspace_id"] == "demo"
    assert rendered["counts"]["tracks_total"] == 2
    assert rendered["counts"]["records_total"] == 2
    assert rendered["counts"]["source_plan_records_total"] == 1
    assert rendered["counts"]["promotions_total"] == 1
    assert rendered["counts"]["champion_tracks_total"] == 1
    assert rendered["counts"]["iterations_total"] == 2
    assert rendered["records"]["by_status"]["success"] == 1
    assert rendered["records"]["by_status"]["failed"] == 1
    assert rendered["records"]["by_stage"]["validation"] == 1
    assert rendered["records"]["by_stage"]["screening"] == 1
    assert rendered["records"]["source_plan_by_stage"]["validation"] == 1
    assert (
        rendered["active_track_effective_campaign_policy"]["effective_policy"][
            "beam_group_limit"
        ]
        == 3
    )
    assert (
        rendered["active_track_effective_campaign_policy"]["effective_policy"][
            "max_generation_timeout_retries"
        ]
        == 5
    )
    assert (
        rendered["active_track_effective_campaign_policy"]["effective_sources"][
            "max_generation_timeout_retries"
        ]
        == "workspace_default"
    )
    assert (
        rendered["active_track_effective_campaign_policy"]["effective_policy"][
            "max_generation_provider_retries"
        ]
        == 6
    )
    assert (
        rendered["active_track_effective_campaign_policy"]["effective_policy"][
            "max_generation_process_retries"
        ]
        == 7
    )
    assert (
        rendered["active_track_effective_campaign_policy"]["effective_policy"][
            "max_benchmark_command_retries"
        ]
        == 2
    )
    assert (
        rendered["active_track_effective_campaign_policy"]["effective_sources"][
            "beam_group_limit"
        ]
        == "workspace_default"
    )
    main_track = next(item for item in rendered["tracks"] if item["track_id"] == "main")
    alt_track = next(item for item in rendered["tracks"] if item["track_id"] == "alt")
    assert (
        main_track["campaign_defaults"]["effective_policy"]["strategy"]
        == "beam_interventions"
    )
    assert main_track["campaign_defaults"]["effective_policy"]["beam_group_limit"] == 3
    assert (
        main_track["campaign_defaults"]["effective_sources"]["beam_group_limit"]
        == "workspace_default"
    )
    assert (
        main_track["campaign_defaults"]["effective_policy"][
            "max_generation_timeout_retries"
        ]
        == 5
    )
    assert (
        main_track["campaign_defaults"]["effective_policy"][
            "max_generation_provider_retries"
        ]
        == 6
    )
    assert (
        main_track["campaign_defaults"]["effective_policy"][
            "max_generation_process_retries"
        ]
        == 7
    )
    assert (
        alt_track["campaign_defaults"]["effective_policy"][
            "max_generation_timeout_retries"
        ]
        == 5
    )
    assert (
        alt_track["campaign_defaults"]["effective_policy"][
            "max_generation_provider_retries"
        ]
        == 6
    )
    assert (
        alt_track["campaign_defaults"]["effective_policy"][
            "max_generation_process_retries"
        ]
        == 7
    )
    assert (
        main_track["campaign_defaults"]["effective_policy"][
            "max_benchmark_command_retries"
        ]
        == 2
    )
    assert (
        alt_track["campaign_defaults"]["effective_policy"]["strategy"]
        == "regression_first"
    )
    assert alt_track["campaign_defaults"]["effective_policy"]["beam_group_limit"] == 4
    assert (
        alt_track["campaign_defaults"]["effective_policy"][
            "max_benchmark_command_retries"
        ]
        == 2
    )
    assert (
        alt_track["campaign_defaults"]["effective_sources"]["beam_group_limit"]
        == "track_override"
    )
    assert main_track["source_plan_records_total"] == 1
    assert main_track["promotions_total"] == 1
    assert main_track["champion_record_id"] == main_record.record_id
    assert alt_track["source_plan_records_total"] == 0
    assert alt_track["records_total"] == 1
    assert alt_track["latest_record_id"] == alt_record.record_id
    assert rendered["state"]["last_iteration_id"] == "iter_0002"
    assert json.loads(output_path.read_text(encoding="utf-8")) == rendered


def test_show_and_export_root_summary_commands(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    for workspace_id, benchmark, objective in [
        ("demo", "tau-bench-airline", "Improve harness correctness"),
        ("retail", "tau-bench-retail", "Improve retail support outcomes"),
    ]:
        assert (
            main(
                [
                    "init-workspace",
                    "--workspace-id",
                    workspace_id,
                    "--objective",
                    objective,
                    "--benchmark",
                    benchmark,
                    "--settings",
                    str(settings),
                    "--root",
                    str(workspaces_root),
                ]
            )
            == 0
        )

    assert (
        main(
            [
                "set-workspace",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--campaign-generator",
                "failure_summary",
                "--campaign-strategy",
                "beam_interventions",
                "--campaign-beam-width",
                "2",
                "--campaign-beam-groups",
                "3",
                "--campaign-max-generation-timeout-retries",
                "5",
                "--campaign-max-generation-provider-retries",
                "6",
                "--campaign-max-generation-provider-transport-retries",
                "8",
                "--campaign-max-generation-provider-auth-retries",
                "9",
                "--campaign-max-generation-provider-rate-limit-retries",
                "10",
                "--campaign-max-generation-process-retries",
                "7",
                "--campaign-max-benchmark-command-retries",
                "2",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "set-track",
                "--workspace-id",
                "retail",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--campaign-strategy",
                "regression_first",
                "--campaign-beam-groups",
                "4",
                "--campaign-max-generation-timeout-retries",
                "6",
                "--campaign-max-generation-provider-retries",
                "7",
                "--campaign-max-generation-provider-transport-retries",
                "9",
                "--campaign-max-generation-provider-auth-retries",
                "10",
                "--campaign-max-generation-provider-rate-limit-retries",
                "11",
                "--campaign-max-generation-process-retries",
                "8",
                "--campaign-max-benchmark-command-retries",
                "4",
            ]
        )
        == 0
    )

    demo_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="demo-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={"benchmark_name": "demo-smoke", "success": True},
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
        source_plan_path=str((tmp_path / "planned_root_demo.json").resolve()),
    )
    retail_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="retail-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={"benchmark_name": "retail-smoke", "success": False},
        dry_run=False,
        workspace_id="retail",
        track_id="main",
        iteration_id="iter_0002",
        stage="screening",
    )
    persist_benchmark_record(root=workspaces_root, record=demo_record)
    persist_benchmark_record(root=workspaces_root, record=retail_record)

    output_path = tmp_path / "root_summary.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-root-summary",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["workspace_total"] == 2
    assert rendered["counts"]["workspaces_total"] == 2
    assert rendered["counts"]["records_total"] == 2
    assert rendered["counts"]["source_plan_records_total"] == 1
    assert rendered["active_track_campaign_default_mix"]["by_generator_id"] == {
        "failure_summary": 1,
        "manual": 1,
    }
    assert rendered["active_track_campaign_default_mix"]["by_strategy"] == {
        "beam_interventions": 1,
        "regression_first": 1,
    }
    assert rendered["active_track_campaign_default_mix"]["by_beam_group_limit"] == {
        "3": 1,
        "4": 1,
    }
    assert rendered["active_track_campaign_default_mix"][
        "by_max_generation_timeout_retries"
    ] == {"5": 1, "6": 1}
    assert rendered["active_track_campaign_default_mix"][
        "by_max_generation_provider_retries"
    ] == {"6": 1, "7": 1}
    assert rendered["active_track_campaign_default_mix"][
        "by_max_generation_provider_transport_retries"
    ] == {"8": 1, "9": 1}
    assert rendered["active_track_campaign_default_mix"][
        "by_max_generation_provider_auth_retries"
    ] == {"10": 1, "9": 1}
    assert rendered["active_track_campaign_default_mix"][
        "by_max_generation_provider_rate_limit_retries"
    ] == {"10": 1, "11": 1}
    assert rendered["active_track_campaign_default_mix"][
        "by_max_generation_process_retries"
    ] == {"7": 1, "8": 1}
    assert rendered["active_track_campaign_default_mix"][
        "by_max_benchmark_command_retries"
    ] == {"2": 1, "4": 1}
    demo_workspace = next(
        item for item in rendered["workspaces"] if item["workspace_id"] == "demo"
    )
    retail_workspace = next(
        item for item in rendered["workspaces"] if item["workspace_id"] == "retail"
    )
    assert (
        demo_workspace["active_track_effective_campaign_policy"]["effective_policy"][
            "generator_id"
        ]
        == "failure_summary"
    )
    assert (
        retail_workspace["active_track_effective_campaign_policy"]["effective_policy"][
            "strategy"
        ]
        == "regression_first"
    )
    assert json.loads(output_path.read_text(encoding="utf-8")) == rendered

    capsys.readouterr()
    assert main(["show-root-summary", "--root", str(workspaces_root)]) == 0
    text_output = capsys.readouterr().out
    assert "Workspaces: 2" in text_output
    assert "Active-track generation-timeout retry mix: 5=1, 6=1" in text_output
    assert "Active-track generation-provider retry mix: 6=1, 7=1" in text_output
    assert "Active-track generation-provider-transport retry mix: 8=1, 9=1" in text_output
    assert "Active-track generation-provider-auth retry mix: 10=1, 9=1" in text_output
    assert "Active-track generation-provider-rate-limit retry mix: 10=1, 11=1" in text_output
    assert "Active-track generation-process retry mix: 7=1, 8=1" in text_output
    assert "Active-track benchmark-command retry mix: 2=1, 4=1" in text_output

    exported_path = tmp_path / "root_summary.yaml"
    capsys.readouterr()
    assert (
        main(
            [
                "export-root-summary",
                "--root",
                str(workspaces_root),
                "--output",
                str(exported_path),
            ]
        )
        == 0
    )
    assert "Exported root summary" in capsys.readouterr().out
    exported = yaml.safe_load(exported_path.read_text(encoding="utf-8"))
    assert exported["format_version"] == "autoharness.root_summary_export.v1"
    assert exported["summary"]["counts"]["records_total"] == 2
    assert (
        exported["summary"]["active_track_campaign_default_mix"][
            "by_max_generation_timeout_retries"
        ]
        == {"5": 1, "6": 1}
    )
    assert (
        exported["summary"]["active_track_campaign_default_mix"][
            "by_max_generation_provider_retries"
        ]
        == {"6": 1, "7": 1}
    )
    assert (
        exported["summary"]["active_track_campaign_default_mix"][
            "by_max_generation_provider_transport_retries"
        ]
        == {"8": 1, "9": 1}
    )
    assert (
        exported["summary"]["active_track_campaign_default_mix"][
            "by_max_generation_provider_auth_retries"
        ]
        == {"10": 1, "9": 1}
    )
    assert (
        exported["summary"]["active_track_campaign_default_mix"][
            "by_max_generation_provider_rate_limit_retries"
        ]
        == {"10": 1, "11": 1}
    )
    assert (
        exported["summary"]["active_track_campaign_default_mix"][
            "by_max_generation_process_retries"
        ]
        == {"7": 1, "8": 1}
    )
    assert (
        exported["summary"]["active_track_campaign_default_mix"][
            "by_max_benchmark_command_retries"
        ]
        == {"2": 1, "4": 1}
    )

    capsys.readouterr()
    assert main(["show-report-file", str(exported_path), "--json"]) == 0
    report_rendered = json.loads(capsys.readouterr().out)
    assert report_rendered["report_type"] == "root_summary_export"
    assert report_rendered["workspace_total"] == 2
    assert report_rendered["record_total"] == 2

    capsys.readouterr()
    assert main(["validate-report-file", str(exported_path)]) == 0
    validation_text = capsys.readouterr().out
    assert "Report type: root_summary_export" in validation_text
    assert "Valid: yes" in validation_text

    capsys.readouterr()
    assert main(["validate-artifact-file", str(exported_path), "--json"]) == 0
    artifact_validation = json.loads(capsys.readouterr().out)
    assert artifact_validation["report_type"] == "root_summary_export"
    assert artifact_validation["valid"] is True

    root_report_path = tmp_path / "root_report.json"
    capsys.readouterr()
    assert (
        main(
            [
                "export-root-report",
                "--root",
                str(workspaces_root),
                "--output",
                str(root_report_path),
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert "Exported root report" in capsys.readouterr().out
    root_report = json.loads(root_report_path.read_text(encoding="utf-8"))
    assert root_report["format_version"] == "autoharness.root_report_export.v1"
    assert root_report["root_summary"]["counts"]["workspaces_total"] == 2
    assert len(root_report["workspace_reports"]) == 2
    assert (
        root_report["workspace_reports"][0]["workspace"]["workspace_id"] in {"demo", "retail"}
    )

    capsys.readouterr()
    assert main(["show-report-file", str(root_report_path), "--json"]) == 0
    root_report_rendered = json.loads(capsys.readouterr().out)
    assert root_report_rendered["report_type"] == "root_report_export"
    assert root_report_rendered["workspace_total"] == 2
    assert root_report_rendered["workspace_report_total"] == 2

    capsys.readouterr()
    assert main(["validate-report-file", str(root_report_path), "--json"]) == 0
    root_report_validation = json.loads(capsys.readouterr().out)
    assert root_report_validation["report_type"] == "root_report_export"
    assert root_report_validation["valid"] is True


def test_show_and_export_root_champion_report_commands(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert main(["setup", "--output", str(settings)]) == 0
    for workspace_id in ("source", "dest"):
        assert (
            main(
                [
                    "init-workspace",
                    "--workspace-id",
                    workspace_id,
                    "--objective",
                    f"Optimize {workspace_id}",
                    "--benchmark",
                    "tau-bench-airline",
                    "--settings",
                    str(settings),
                    "--root",
                    str(workspaces_root),
                ]
            )
            == 0
        )

    source_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="root-champion-smoke",
        config={"benchmark_name": "root-champion-smoke"},
        payload={
            "command": [sys.executable, "-c", "print('ok')"],
            "success": True,
            "metrics": {"pass_rate": 1.0},
            "edit_application": {
                "summary": "Set root champion state",
                "status": "applied",
                "operations": [
                    {
                        "type": "write_file",
                        "path": "src/agent.py",
                        "content": "STATE = 'root'\n",
                    }
                ],
            },
            "edit_restore": {},
            "staging": {"status": "applied"},
        },
        dry_run=False,
        workspace_id="source",
        track_id="main",
        hypothesis="Source champion",
        notes="Root champion",
        stage="screening",
    )
    persist_benchmark_record(root=workspaces_root, record=source_record)
    source_target_root = tmp_path / "root-source-target"
    source_target_root.mkdir()
    source_promotion = create_promotion_record(
        workspace_id="source",
        track_id="main",
        record=source_record,
        target_root=source_target_root,
        notes="Promote source champion",
        edit_restore={},
    )
    source_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=source_promotion,
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=source_record,
        promotion=source_promotion,
        promotion_artifacts=source_artifacts,
    )
    source_state = load_workspace_state(workspaces_root, "source")
    update_state_after_promotion(
        root=workspaces_root,
        workspace_id="source",
        state=source_state,
        record_id=source_record.record_id,
    )

    destination_target_root = tmp_path / "root-dest-target"
    destination_target_root.mkdir()
    assert (
        main(
            [
                "transfer-champion",
                "--source-workspace-id",
                "source",
                "--workspace-id",
                "dest",
                "--target-root",
                str(destination_target_root),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    capsys.readouterr()
    assert (
        main(
            [
                "show-root-champions",
                "--workspace-id",
                "source",
                "--workspace-id",
                "dest",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["workspace_total"] == 2
    assert shown["champion_total"] == 2
    assert shown["transferred_champion_total"] == 1
    assert shown["mix"]["by_source_workspace_id"]["(native)"] == 1
    assert shown["mix"]["by_source_workspace_id"]["source"] == 1

    export_path = tmp_path / "root-champions.yaml"
    assert (
        main(
            [
                "export-root-champion-report",
                "--workspace-id",
                "source",
                "--workspace-id",
                "dest",
                "--root",
                str(workspaces_root),
                "--output",
                str(export_path),
            ]
        )
        == 0
    )
    export_payload = yaml.safe_load(export_path.read_text(encoding="utf-8"))
    assert export_payload["format_version"] == "autoharness.root_champion_report.v1"
    assert export_payload["champions"]["champion_total"] == 2

    capsys.readouterr()
    assert main(["show-report-file", str(export_path), "--json"]) == 0
    shown_report = json.loads(capsys.readouterr().out)
    assert shown_report["report_type"] == "root_champion_report"
    assert shown_report["champion_total"] == 2
    assert shown_report["transferred_champion_total"] == 1

    capsys.readouterr()
    assert main(["validate-report-file", str(export_path), "--json"]) == 0
    validated_report = json.loads(capsys.readouterr().out)
    assert validated_report["valid"] is True
    assert validated_report["report_type"] == "root_champion_report"


def test_export_and_repair_root_bundle_commands(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    for workspace_id, benchmark, objective in [
        ("demo", "tau-bench-airline", "Improve harness correctness"),
        ("retail", "tau-bench-retail", "Improve retail support outcomes"),
    ]:
        assert (
            main(
                [
                    "init-workspace",
                    "--workspace-id",
                    workspace_id,
                    "--objective",
                    objective,
                    "--benchmark",
                    benchmark,
                    "--settings",
                    str(settings),
                    "--root",
                    str(workspaces_root),
                ]
            )
            == 0
        )

    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="demo-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={"benchmark_name": "demo-smoke", "success": True},
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote root bundle candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    bundle_output = tmp_path / "root_bundle"
    capsys.readouterr()
    assert (
        main(
            [
                "export-root-bundle",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
            ]
        )
        == 0
    )
    export_text = capsys.readouterr().out
    assert "Workspace bundles: 2" in export_text

    capsys.readouterr()
    assert main(["show-bundle", str(bundle_output), "--json"]) == 0
    bundle_rendered = json.loads(capsys.readouterr().out)
    assert bundle_rendered["bundle_type"] == "root_bundle"
    assert bundle_rendered["workspace_bundle_total"] == 2
    assert bundle_rendered["artifact_status"]["root_report"]["exists"] is True

    capsys.readouterr()
    assert main(["show-bundle", str(bundle_output), "--recursive", "--json"]) == 0
    recursive_rendered = json.loads(capsys.readouterr().out)
    assert recursive_rendered["bundle_type"] == "root_bundle"
    assert recursive_rendered["nested_bundle_total"] == 2
    demo_workspace_bundle = next(
        item
        for item in recursive_rendered["nested_bundles"]
        if item["manifest"].get("workspace_id") == "demo"
    )
    assert demo_workspace_bundle["bundle_type"] == "workspace_bundle"
    assert demo_workspace_bundle["nested_bundle_total"] == 1

    broken_manifest = bundle_output / "workspaces" / "demo" / "champions" / "main" / "champion.json"
    broken_manifest.unlink()

    capsys.readouterr()
    assert main(["validate-bundle", str(bundle_output), "--recursive", "--json"]) == 1
    invalid_validation = json.loads(capsys.readouterr().out)
    assert invalid_validation["bundle_type"] == "root_bundle"
    assert invalid_validation["valid"] is False
    assert invalid_validation["nested_error_count"] >= 1

    capsys.readouterr()
    assert main(["reindex-bundle", str(bundle_output), "--recursive", "--json"]) == 0
    reindexed = json.loads(capsys.readouterr().out)
    assert reindexed["bundle_type"] == "root_bundle"
    assert Path(
        bundle_output / "workspaces" / "demo" / "champions" / "main" / "champion.json"
    ).exists()

    capsys.readouterr()
    assert main(["validate-bundle", str(bundle_output), "--recursive", "--json"]) == 0
    valid_validation = json.loads(capsys.readouterr().out)
    assert valid_validation["valid"] is True

    imported_bundle = tmp_path / "imported_root_bundle"
    capsys.readouterr()
    assert (
        main(
            [
                "import-bundle",
                str(bundle_output),
                "--output",
                str(imported_bundle),
                "--recursive",
                "--json",
            ]
        )
        == 0
    )
    imported = json.loads(capsys.readouterr().out)
    assert imported["valid"] is True
    assert imported["bundle_type"] == "root_bundle"

    capsys.readouterr()
    assert main(["validate-bundle", str(imported_bundle), "--recursive", "--json"]) == 0
    imported_validation = json.loads(capsys.readouterr().out)
    assert imported_validation["bundle_type"] == "root_bundle"
    assert imported_validation["valid"] is True


def test_export_track_and_workspace_summary_commands(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
        source_plan_path=str((tmp_path / "planned_export_summary.json").resolve()),
    )
    persist_benchmark_record(root=workspaces_root, record=record)

    workspace_output = tmp_path / "workspace_summary.yaml"
    track_output = tmp_path / "track_summary.json"

    capsys.readouterr()
    assert (
        main(
            [
                "export-workspace-summary",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(workspace_output),
            ]
        )
        == 0
    )
    assert "Exported workspace summary" in capsys.readouterr().out
    workspace_export = yaml.safe_load(workspace_output.read_text(encoding="utf-8"))
    assert workspace_export["format_version"] == "autoharness.workspace_summary_export.v1"
    assert workspace_export["summary"]["workspace_id"] == "demo"
    assert workspace_export["summary"]["counts"]["records_total"] == 1
    assert "active_track_effective_campaign_policy" in workspace_export["summary"]

    assert (
        main(
            [
                "export-track-summary",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(track_output),
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert "Exported track summary" in capsys.readouterr().out
    track_export = json.loads(track_output.read_text(encoding="utf-8"))
    assert track_export["format_version"] == "autoharness.track_summary_export.v1"
    assert track_export["summary"]["workspace_id"] == "demo"
    assert track_export["summary"]["track_id"] == "main"
    assert track_export["summary"]["records"]["total"] == 1
    assert "effective_campaign_policy" in track_export["summary"]


def test_export_workspace_and_track_report_commands(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "create-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
                "--benchmark",
                "tau-bench-retail",
                "--objective",
                "Improve retail support outcomes",
            ]
        )
        == 0
    )

    main_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
        source_plan_path=str((tmp_path / "planned_workspace_report.json").resolve()),
    )
    persist_benchmark_record(root=workspaces_root, record=main_record)

    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=main_record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=main_record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    workspace_report_output = tmp_path / "workspace_report.json"
    track_report_output = tmp_path / "track_report.yaml"

    capsys.readouterr()
    assert (
        main(
            [
                "export-workspace-report",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(workspace_report_output),
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert "Exported workspace report" in capsys.readouterr().out
    workspace_report = json.loads(workspace_report_output.read_text(encoding="utf-8"))
    assert workspace_report["format_version"] == "autoharness.workspace_report_export.v1"
    assert workspace_report["workspace"]["workspace_id"] == "demo"
    assert workspace_report["workspace_summary"]["counts"]["records_total"] == 1
    assert len(workspace_report["track_reports"]) == 2
    main_track_report = next(
        item for item in workspace_report["track_reports"] if item["track_id"] == "main"
    )
    assert main_track_report["summary"]["champion"]["record_id"] == main_record.record_id
    assert (
        main_track_report["effective_track_policy"]["promotion_benchmark"]
        == "tau-bench-airline"
    )

    assert (
        main(
            [
                "export-track-report",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(track_report_output),
            ]
        )
        == 0
    )
    assert "Exported track report" in capsys.readouterr().out
    track_report = yaml.safe_load(track_report_output.read_text(encoding="utf-8"))
    assert track_report["format_version"] == "autoharness.track_report_export.v1"
    assert track_report["track"]["track_id"] == "main"
    assert track_report["track_summary"]["records"]["total"] == 1
    assert track_report["promotion_policy"]["exists"] is True
    assert track_report["track_artifacts"]["champion_artifacts"]["record_id"] == main_record.record_id


def test_show_and_validate_report_file_commands(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "create-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
                "--benchmark",
                "tau-bench-retail",
                "--objective",
                "Improve retail support outcomes",
            ]
        )
        == 0
    )

    main_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
        source_plan_path=str((tmp_path / "planned_report_file.json").resolve()),
    )
    persist_benchmark_record(root=workspaces_root, record=main_record)

    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=main_record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=main_record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    workspace_summary_output = tmp_path / "workspace_summary.yaml"
    track_summary_output = tmp_path / "track_summary.json"
    workspace_report_output = tmp_path / "workspace_report.json"
    track_report_output = tmp_path / "track_report.yaml"

    assert (
        main(
            [
                "export-workspace-summary",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(workspace_summary_output),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "export-track-summary",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(track_summary_output),
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "export-workspace-report",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(workspace_report_output),
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "export-track-report",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(track_report_output),
            ]
        )
        == 0
    )

    capsys.readouterr()
    assert main(["show-report-file", str(workspace_summary_output), "--json"]) == 0
    workspace_summary_rendered = json.loads(capsys.readouterr().out)
    assert workspace_summary_rendered["report_type"] == "workspace_summary_export"
    assert workspace_summary_rendered["workspace_id"] == "demo"
    assert workspace_summary_rendered["track_total"] == 2
    assert workspace_summary_rendered["record_total"] == 1

    assert main(["show-report-file", str(track_report_output)]) == 0
    track_report_text = capsys.readouterr().out
    assert "Report type: track_report_export" in track_report_text
    assert "Track: main" in track_report_text
    assert "Champion: present" in track_report_text

    assert (
        main(["validate-report-file", str(workspace_report_output), "--json"]) == 0
    )
    workspace_report_validation = json.loads(capsys.readouterr().out)
    assert workspace_report_validation["report_type"] == "workspace_report_export"
    assert workspace_report_validation["valid"] is True
    assert workspace_report_validation["track_report_total"] == 2

    assert main(["validate-report-file", str(track_summary_output)]) == 0
    track_summary_validation_text = capsys.readouterr().out
    assert "Report type: track_summary_export" in track_summary_validation_text
    assert "Valid: yes" in track_summary_validation_text

    invalid_report_output = tmp_path / "invalid_track_summary.json"
    invalid_report_output.write_text(
        json.dumps(
            {
                "format_version": "autoharness.track_summary_export.v1",
                "exported_at": "2026-04-22T00:00:00Z",
                "summary": {
                    "workspace_id": "demo",
                },
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(["validate-report-file", str(invalid_report_output), "--json"]) == 1
    )
    invalid_validation = json.loads(capsys.readouterr().out)
    assert invalid_validation["report_type"] == "track_summary_export"
    assert invalid_validation["valid"] is False
    assert "Missing or invalid `summary.track_id`." in invalid_validation[
        "validation_errors"
    ]
    assert "Missing or invalid `summary.records`." in invalid_validation[
        "validation_errors"
    ]

    capsys.readouterr()
    assert main(["show-artifact-file", str(workspace_report_output), "--json"]) == 0
    generic_shown = json.loads(capsys.readouterr().out)
    assert generic_shown["report_type"] == "workspace_report_export"
    assert generic_shown["workspace_id"] == "demo"

    capsys.readouterr()
    assert main(["validate-artifact-file", str(track_summary_output), "--json"]) == 0
    generic_validated = json.loads(capsys.readouterr().out)
    assert generic_validated["report_type"] == "track_summary_export"
    assert generic_validated["valid"] is True


def test_export_workspace_bundle_command(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "create-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
                "--benchmark",
                "tau-bench-retail",
                "--objective",
                "Improve retail support outcomes",
            ]
        )
        == 0
    )

    main_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
        source_plan_path=str((tmp_path / "planned_workspace_bundle.json").resolve()),
    )
    persist_benchmark_record(root=workspaces_root, record=main_record)

    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=main_record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=main_record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    bundle_output = tmp_path / "workspace_bundle"
    capsys.readouterr()
    assert (
        main(
            [
                "export-workspace-bundle",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
                "--format",
                "json",
            ]
        )
        == 0
    )
    bundle_stdout = capsys.readouterr().out
    assert "Exported" not in bundle_stdout
    assert "Bundle manifest:" in bundle_stdout

    bundle_manifest = json.loads(
        (bundle_output / "bundle_manifest.json").read_text(encoding="utf-8")
    )
    assert bundle_manifest["format_version"] == "autoharness.workspace_bundle.v1"
    assert bundle_manifest["workspace_id"] == "demo"
    assert bundle_manifest["artifact_format"] == "json"
    assert bundle_manifest["artifacts"]["workspace_report_path"] == "workspace_report.json"
    assert bundle_manifest["artifacts"]["event_log_path"] == "events.jsonl"
    assert bundle_manifest["artifacts"]["iterations_path"] == "listings/iterations.json"
    assert len(bundle_manifest["artifacts"]["track_reports"]) == 2
    assert bundle_manifest["artifacts"]["champion_bundles"] == [
        {
            "track_id": "main",
            "path": "champions/main",
            "record_id": main_record.record_id,
            "promotion_id": promotion.promotion_id,
        }
    ]

    workspace_report = json.loads(
        (bundle_output / "workspace_report.json").read_text(encoding="utf-8")
    )
    assert workspace_report["workspace"]["workspace_id"] == "demo"
    assert workspace_report["workspace_summary"]["counts"]["records_total"] == 1

    iterations_listing = json.loads(
        (bundle_output / "listings" / "iterations.json").read_text(encoding="utf-8")
    )
    assert iterations_listing["format_version"] == "autoharness.iteration_export.v1"
    assert iterations_listing["workspace_id"] == "demo"

    records_listing = json.loads(
        (bundle_output / "listings" / "records.json").read_text(encoding="utf-8")
    )
    assert records_listing["format_version"] == "autoharness.record_export.v1"
    assert records_listing["records"][0]["record_id"] == main_record.record_id

    promotions_listing = json.loads(
        (bundle_output / "listings" / "promotions.json").read_text(encoding="utf-8")
    )
    assert promotions_listing["format_version"] == "autoharness.promotion_export.v1"
    assert promotions_listing["promotions"][0]["promotion_id"] == promotion.promotion_id

    main_track_report = json.loads(
        (bundle_output / "tracks" / "main" / "report.json").read_text(encoding="utf-8")
    )
    assert main_track_report["format_version"] == "autoharness.track_report_export.v1"
    assert main_track_report["track_summary"]["champion"]["record_id"] == main_record.record_id

    alt_track_report = json.loads(
        (bundle_output / "tracks" / "alt" / "report.json").read_text(encoding="utf-8")
    )
    assert alt_track_report["track"]["track_id"] == "alt"
    assert alt_track_report["track_summary"]["records"]["total"] == 0

    champion_bundle = json.loads(
        (bundle_output / "champions" / "main" / "champion.json").read_text(encoding="utf-8")
    )
    assert champion_bundle["format_version"] == "autoharness.champion_export.v1"
    assert champion_bundle["record_id"] == main_record.record_id


def test_export_track_bundle_command(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "create-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
                "--benchmark",
                "tau-bench-retail",
                "--objective",
                "Improve retail support outcomes",
            ]
        )
        == 0
    )

    main_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
        source_plan_path=str((tmp_path / "planned_track_bundle.json").resolve()),
    )
    persist_benchmark_record(root=workspaces_root, record=main_record)

    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=main_record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=main_record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    bundle_output = tmp_path / "track_bundle"
    capsys.readouterr()
    assert (
        main(
            [
                "export-track-bundle",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
                "--format",
                "json",
            ]
        )
        == 0
    )
    bundle_stdout = capsys.readouterr().out
    assert "Bundle manifest:" in bundle_stdout
    assert "Champion bundle: present" in bundle_stdout

    bundle_manifest = json.loads(
        (bundle_output / "bundle_manifest.json").read_text(encoding="utf-8")
    )
    assert bundle_manifest["format_version"] == "autoharness.track_bundle.v1"
    assert bundle_manifest["workspace_id"] == "demo"
    assert bundle_manifest["track_id"] == "main"
    assert bundle_manifest["artifact_format"] == "json"
    assert bundle_manifest["artifacts"]["track_report_path"] == "track_report.json"
    assert bundle_manifest["artifacts"]["iterations_path"] == "listings/iterations.json"
    assert bundle_manifest["artifacts"]["records_path"] == "listings/records.json"
    assert bundle_manifest["artifacts"]["promotions_path"] == "listings/promotions.json"
    assert bundle_manifest["artifacts"]["champion_bundle"] == {
        "path": "champion",
        "record_id": main_record.record_id,
        "promotion_id": promotion.promotion_id,
    }

    track_report = json.loads((bundle_output / "track_report.json").read_text(encoding="utf-8"))
    assert track_report["format_version"] == "autoharness.track_report_export.v1"
    assert track_report["track"]["track_id"] == "main"

    iterations_listing = json.loads(
        (bundle_output / "listings" / "iterations.json").read_text(encoding="utf-8")
    )
    assert iterations_listing["track_id"] == "main"
    assert iterations_listing["format_version"] == "autoharness.iteration_export.v1"

    records_listing = json.loads(
        (bundle_output / "listings" / "records.json").read_text(encoding="utf-8")
    )
    assert records_listing["track_id"] == "main"
    assert records_listing["format_version"] == "autoharness.record_export.v1"
    assert [item["record_id"] for item in records_listing["records"]] == [main_record.record_id]

    promotions_listing = json.loads(
        (bundle_output / "listings" / "promotions.json").read_text(encoding="utf-8")
    )
    assert promotions_listing["track_id"] == "main"
    assert promotions_listing["format_version"] == "autoharness.promotion_export.v1"
    assert [item["promotion_id"] for item in promotions_listing["promotions"]] == [
        promotion.promotion_id
    ]

    champion_bundle = json.loads(
        (bundle_output / "champion" / "champion.json").read_text(encoding="utf-8")
    )
    assert champion_bundle["format_version"] == "autoharness.champion_export.v1"
    assert champion_bundle["record_id"] == main_record.record_id


def test_export_workspace_bundle_skip_flags(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    main_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=main_record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=main_record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=main_record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    bundle_output = tmp_path / "workspace_bundle_skip"
    capsys.readouterr()
    assert (
        main(
            [
                "export-workspace-bundle",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
                "--format",
                "json",
                "--skip-listings",
                "--skip-track-reports",
                "--skip-champions",
            ]
        )
        == 0
    )
    bundle_stdout = capsys.readouterr().out
    assert "Listings: skipped" in bundle_stdout
    assert "Track reports: skipped" in bundle_stdout
    assert "Champion bundles: skipped" in bundle_stdout

    bundle_manifest = json.loads(
        (bundle_output / "bundle_manifest.json").read_text(encoding="utf-8")
    )
    assert bundle_manifest["includes"] == {
        "listings": False,
        "track_reports": False,
        "champion_bundles": False,
        "event_log": True,
    }
    assert bundle_manifest["artifacts"]["workspace_report_path"] == "workspace_report.json"
    assert bundle_manifest["artifacts"]["event_log_path"] == "events.jsonl"
    assert bundle_manifest["artifacts"]["iterations_path"] is None
    assert bundle_manifest["artifacts"]["records_path"] is None
    assert bundle_manifest["artifacts"]["promotions_path"] is None
    assert bundle_manifest["artifacts"]["track_reports"] == []
    assert bundle_manifest["artifacts"]["champion_bundles"] == []

    assert (bundle_output / "workspace_report.json").exists()
    assert (bundle_output / "events.jsonl").exists()
    assert not (bundle_output / "listings").exists()
    assert not (bundle_output / "tracks").exists()
    assert not (bundle_output / "champions").exists()


def test_export_track_bundle_skip_flags(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    main_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=main_record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=main_record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=main_record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    bundle_output = tmp_path / "track_bundle_skip"
    capsys.readouterr()
    assert (
        main(
            [
                "export-track-bundle",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
                "--format",
                "json",
                "--skip-listings",
                "--skip-champion",
            ]
        )
        == 0
    )
    bundle_stdout = capsys.readouterr().out
    assert "Listings: skipped" in bundle_stdout
    assert "Champion bundle: skipped" in bundle_stdout

    bundle_manifest = json.loads(
        (bundle_output / "bundle_manifest.json").read_text(encoding="utf-8")
    )
    assert bundle_manifest["includes"] == {
        "listings": False,
        "champion_bundle": False,
        "event_log": True,
    }
    assert bundle_manifest["artifacts"]["track_report_path"] == "track_report.json"
    assert bundle_manifest["artifacts"]["event_log_path"] == "events.jsonl"
    assert bundle_manifest["artifacts"]["iterations_path"] is None
    assert bundle_manifest["artifacts"]["records_path"] is None
    assert bundle_manifest["artifacts"]["promotions_path"] is None
    assert bundle_manifest["artifacts"]["champion_bundle"] is None

    assert (bundle_output / "track_report.json").exists()
    assert (bundle_output / "events.jsonl").exists()
    assert not (bundle_output / "listings").exists()
    assert not (bundle_output / "champion").exists()


def test_show_bundle_command_for_workspace_and_champion_bundle(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    bundle_output = tmp_path / "workspace_bundle_for_show"
    assert (
        main(
            [
                "export-workspace-bundle",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
                "--format",
                "json",
            ]
        )
        == 0
    )

    show_output = tmp_path / "bundle_view.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-bundle",
                str(bundle_output),
                "--json",
                "--output",
                str(show_output),
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["bundle_type"] == "workspace_bundle"
    assert shown["workspace_id"] == "demo"
    assert shown["artifact_format"] == "json"
    assert shown["includes"]["listings"] is True
    assert shown["artifact_status"]["workspace_report"]["exists"] is True
    assert shown["track_reports_total"] == 1
    assert shown["champion_bundles_total"] == 1
    assert shown["missing_artifacts"] == []
    assert json.loads(show_output.read_text(encoding="utf-8")) == shown

    capsys.readouterr()
    assert (
        main(
            [
                "show-bundle",
                str(bundle_output / "champions" / "main"),
                "--json",
            ]
        )
        == 0
    )
    champion_view = json.loads(capsys.readouterr().out)
    assert champion_view["bundle_type"] == "champion_bundle"
    assert champion_view["workspace_id"] == "demo"
    assert champion_view["track_id"] == "main"
    assert champion_view["record_id"] == record.record_id
    assert champion_view["promotion_id"] == promotion.promotion_id
    assert champion_view["missing_artifacts"] == []


def test_show_bundle_command_for_track_bundle_text_output(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    bundle_output = tmp_path / "track_bundle_for_show"
    assert (
        main(
            [
                "export-track-bundle",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
                "--format",
                "json",
                "--skip-listings",
                "--skip-champion",
            ]
        )
        == 0
    )

    capsys.readouterr()
    assert main(["show-bundle", str(bundle_output)]) == 0
    text = capsys.readouterr().out
    assert "Bundle type: track_bundle" in text
    assert "Workspace: demo" in text
    assert "Track: main" in text
    assert "Listings: skipped" in text
    assert "Champion bundle: skipped" in text
    assert "Missing artifacts: 0" in text


def test_show_bundle_command_can_recurse_into_nested_champion_bundles(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    bundle_output = tmp_path / "workspace_bundle_recursive_show"
    assert (
        main(
            [
                "export-workspace-bundle",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
                "--format",
                "json",
                "--skip-track-reports",
            ]
        )
        == 0
    )

    (bundle_output / "champions" / "main" / "source_champion.json").unlink()

    capsys.readouterr()
    assert (
        main(
            [
                "show-bundle",
                str(bundle_output),
                "--recursive",
                "--json",
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["bundle_type"] == "workspace_bundle"
    assert shown["recursive"] is True
    assert shown["nested_bundle_total"] == 1
    assert shown["nested_error_count"] == 1
    assert shown["missing_artifacts"] == []
    nested_bundle = shown["nested_bundles"][0]
    assert nested_bundle["path"] == "champions/main"
    assert nested_bundle["bundle_type"] == "champion_bundle"
    assert nested_bundle["valid"] is False
    assert nested_bundle["validation_errors"] == ["Missing artifact: source_champion.json"]

    capsys.readouterr()
    assert main(["show-bundle", str(bundle_output), "--recursive"]) == 0
    text = capsys.readouterr().out
    assert "Recursive: yes" in text
    assert "Nested bundles: 1" in text
    assert "Nested bundle champions/main: invalid (1 errors)" in text


def test_validate_bundle_command_reports_valid_workspace_bundle(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    bundle_output = tmp_path / "workspace_bundle_for_validate"
    assert (
        main(
            [
                "export-workspace-bundle",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
                "--format",
                "json",
                "--skip-track-reports",
                "--skip-champions",
            ]
        )
        == 0
    )

    validation_output = tmp_path / "bundle_validation.json"
    capsys.readouterr()
    assert (
        main(
            [
                "validate-bundle",
                str(bundle_output),
                "--json",
                "--output",
                str(validation_output),
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["bundle_type"] == "workspace_bundle"
    assert rendered["valid"] is True
    assert rendered["error_count"] == 0
    assert rendered["validation_errors"] == []
    assert json.loads(validation_output.read_text(encoding="utf-8")) == rendered


def test_validate_bundle_command_reports_missing_artifacts(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    bundle_output = tmp_path / "track_bundle_for_validate"
    assert (
        main(
            [
                "export-track-bundle",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
                "--format",
                "json",
                "--skip-champion",
            ]
        )
        == 0
    )

    (bundle_output / "track_report.json").unlink()

    validation_output = tmp_path / "track_bundle_validation.json"
    capsys.readouterr()
    assert (
        main(
            [
                "validate-bundle",
                str(bundle_output),
                "--json",
                "--output",
                str(validation_output),
            ]
        )
        == 1
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["bundle_type"] == "track_bundle"
    assert rendered["valid"] is False
    assert rendered["error_count"] == 1
    assert rendered["missing_artifacts"] == ["track_report.json"]
    assert rendered["validation_errors"] == ["Missing artifact: track_report.json"]
    assert json.loads(validation_output.read_text(encoding="utf-8")) == rendered


def test_validate_bundle_command_can_recurse_into_nested_champion_bundles(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    bundle_output = tmp_path / "workspace_bundle_recursive_validate"
    assert (
        main(
            [
                "export-workspace-bundle",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
                "--format",
                "json",
                "--skip-track-reports",
            ]
        )
        == 0
    )

    (bundle_output / "champions" / "main" / "source_champion.json").unlink()

    capsys.readouterr()
    assert main(["validate-bundle", str(bundle_output), "--json"]) == 0
    non_recursive = json.loads(capsys.readouterr().out)
    assert non_recursive["valid"] is True
    assert non_recursive["recursive"] is False

    capsys.readouterr()
    assert main(["validate-bundle", str(bundle_output), "--recursive", "--json"]) == 1
    recursive = json.loads(capsys.readouterr().out)
    assert recursive["bundle_type"] == "workspace_bundle"
    assert recursive["recursive"] is True
    assert recursive["nested_bundle_total"] == 1
    nested_bundle = recursive["nested_bundles"][0]
    assert nested_bundle["path"] == "champions/main"
    assert nested_bundle["bundle_type"] == "champion_bundle"
    assert nested_bundle["valid"] is False
    assert recursive["valid"] is False
    assert recursive["nested_error_count"] == 1
    assert recursive["validation_errors"] == [
        "Nested bundle champions/main: Missing artifact: source_champion.json"
    ]


def test_reindex_bundle_command_recreates_workspace_manifest(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    bundle_output = tmp_path / "workspace_bundle_for_reindex"
    assert (
        main(
            [
                "export-workspace-bundle",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
                "--format",
                "json",
            ]
        )
        == 0
    )

    manifest_path = bundle_output / "bundle_manifest.json"
    manifest_path.unlink()

    capsys.readouterr()
    assert main(["reindex-bundle", str(bundle_output), "--json"]) == 0
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["bundle_type"] == "workspace_bundle"
    assert rendered["bundle_path"] == str(bundle_output)
    assert rendered["manifest_path"] == str(manifest_path)
    assert rendered["manifest_existed"] is False
    assert rendered["artifact_format"] == "json"
    assert rendered["written_format"] == "json"
    rebuilt_manifest = rendered["manifest"]
    assert rebuilt_manifest["format_version"] == "autoharness.workspace_bundle.v1"
    assert rebuilt_manifest["workspace_id"] == "demo"
    assert rebuilt_manifest["includes"]["listings"] is True
    assert rebuilt_manifest["includes"]["track_reports"] is True
    assert rebuilt_manifest["includes"]["champion_bundles"] is False
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == rebuilt_manifest


def test_reindex_bundle_command_updates_track_manifest_after_artifact_removal(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    bundle_output = tmp_path / "track_bundle_for_reindex"
    assert (
        main(
            [
                "export-track-bundle",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
                "--format",
                "json",
            ]
        )
        == 0
    )

    champion_dir = bundle_output / "champion"
    for child in champion_dir.iterdir():
        child.unlink()
    champion_dir.rmdir()

    capsys.readouterr()
    assert main(["validate-bundle", str(bundle_output), "--json"]) == 1
    invalid_rendered = json.loads(capsys.readouterr().out)
    assert invalid_rendered["valid"] is False
    assert invalid_rendered["missing_artifacts"] == ["champion"]

    capsys.readouterr()
    assert main(["reindex-bundle", str(bundle_output), "--json"]) == 0
    rebuilt = json.loads(capsys.readouterr().out)
    assert rebuilt["bundle_type"] == "track_bundle"
    assert rebuilt["manifest_existed"] is True
    rebuilt_manifest = rebuilt["manifest"]
    assert rebuilt_manifest["includes"]["listings"] is True
    assert rebuilt_manifest["includes"]["champion_bundle"] is False
    assert rebuilt_manifest["artifacts"]["champion_bundle"] is None

    capsys.readouterr()
    assert main(["validate-bundle", str(bundle_output), "--json"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["valid"] is True
    assert validated["missing_artifacts"] == []


def test_reindex_bundle_command_can_recurse_into_nested_champion_bundles(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    bundle_output = tmp_path / "track_bundle_recursive_reindex"
    assert (
        main(
            [
                "export-track-bundle",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
                "--format",
                "json",
            ]
        )
        == 0
    )

    (bundle_output / "champion" / "champion.json").unlink()

    capsys.readouterr()
    assert main(["validate-bundle", str(bundle_output), "--recursive", "--json"]) == 1
    invalid_rendered = json.loads(capsys.readouterr().out)
    assert invalid_rendered["validation_errors"] == [
        f"Nested bundle champion: Bundle manifest not found under: {bundle_output / 'champion'}"
    ]

    capsys.readouterr()
    assert (
        main(
            [
                "reindex-bundle",
                str(bundle_output),
                "--recursive",
                "--format",
                "yaml",
                "--json",
            ]
        )
        == 0
    )
    rebuilt = json.loads(capsys.readouterr().out)
    assert rebuilt["bundle_type"] == "track_bundle"
    assert rebuilt["recursive"] is True
    assert rebuilt["nested_bundle_total"] == 1
    assert rebuilt["manifest_path"] == str(bundle_output / "bundle_manifest.yaml")
    assert rebuilt["written_format"] == "yaml"
    nested_bundle = rebuilt["nested_bundles"][0]
    assert nested_bundle["path"] == "champion"
    assert nested_bundle["bundle_type"] == "champion_bundle"
    assert nested_bundle["manifest_path"] == str(bundle_output / "champion" / "champion.yaml")
    assert nested_bundle["written_format"] == "yaml"
    assert (bundle_output / "champion" / "champion.yaml").exists()
    assert not (bundle_output / "champion" / "champion.json").exists()

    capsys.readouterr()
    assert main(["validate-bundle", str(bundle_output), "--recursive", "--json"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["valid"] is True
    assert validated["nested_bundle_total"] == 1
    assert validated["nested_bundles"][0]["valid"] is True


def test_reindex_bundle_command_can_normalize_manifest_format_in_place(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    bundle_output = tmp_path / "workspace_bundle_reindexed_yaml"
    assert (
        main(
            [
                "export-workspace-bundle",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_output),
                "--format",
                "json",
                "--skip-track-reports",
                "--skip-champions",
            ]
        )
        == 0
    )

    capsys.readouterr()
    assert (
        main(
            [
                "reindex-bundle",
                str(bundle_output),
                "--format",
                "yaml",
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["bundle_type"] == "workspace_bundle"
    assert rendered["target_format"] == "yaml"
    assert rendered["manifest_path"] == str(bundle_output / "bundle_manifest.yaml")
    assert rendered["written_format"] == "yaml"
    assert (bundle_output / "bundle_manifest.yaml").exists()
    assert not (bundle_output / "bundle_manifest.json").exists()

    rebuilt_manifest = yaml.safe_load(
        (bundle_output / "bundle_manifest.yaml").read_text(encoding="utf-8")
    )
    assert rebuilt_manifest["format_version"] == "autoharness.workspace_bundle.v1"
    assert rebuilt_manifest["artifact_format"] == "json"

    capsys.readouterr()
    assert main(["validate-bundle", str(bundle_output), "--json"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["valid"] is True


def test_import_bundle_command_copies_and_validates_workspace_bundle(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)

    source_bundle = tmp_path / "workspace_bundle_source"
    assert (
        main(
            [
                "export-workspace-bundle",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(source_bundle),
                "--format",
                "json",
                "--skip-track-reports",
                "--skip-champions",
            ]
        )
        == 0
    )

    imported_bundle = tmp_path / "workspace_bundle_imported"
    capsys.readouterr()
    assert (
        main(
            [
                "import-bundle",
                str(source_bundle),
                "--output",
                str(imported_bundle),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["bundle_type"] == "workspace_bundle"
    assert rendered["source_bundle_path"] == str(source_bundle)
    assert rendered["destination_bundle_path"] == str(imported_bundle)
    assert rendered["manifest_generated"] is False
    assert rendered["valid"] is True
    assert rendered["error_count"] == 0
    assert (imported_bundle / "bundle_manifest.json").exists()
    assert (imported_bundle / "workspace_report.json").exists()

    capsys.readouterr()
    assert main(["validate-bundle", str(imported_bundle), "--json"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["valid"] is True


def test_import_bundle_command_generates_manifest_when_source_manifest_missing(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    source_bundle = tmp_path / "track_bundle_source"
    assert (
        main(
            [
                "export-track-bundle",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(source_bundle),
                "--format",
                "json",
                "--skip-listings",
                "--skip-champion",
            ]
        )
        == 0
    )
    (source_bundle / "bundle_manifest.json").unlink()

    imported_bundle = tmp_path / "track_bundle_imported"
    capsys.readouterr()
    assert (
        main(
            [
                "import-bundle",
                str(source_bundle),
                "--output",
                str(imported_bundle),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["bundle_type"] == "track_bundle"
    assert rendered["manifest_generated"] is True
    assert rendered["valid"] is True
    rebuilt_manifest = json.loads(
        (imported_bundle / "bundle_manifest.json").read_text(encoding="utf-8")
    )
    assert rebuilt_manifest["format_version"] == "autoharness.track_bundle.v1"
    assert rebuilt_manifest["includes"]["listings"] is False
    assert rebuilt_manifest["includes"]["champion_bundle"] is False


def test_import_bundle_command_rewrites_manifest_to_target_format(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    source_bundle = tmp_path / "workspace_bundle_target_format_source"
    assert (
        main(
            [
                "export-workspace-bundle",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(source_bundle),
                "--format",
                "json",
                "--skip-track-reports",
                "--skip-champions",
            ]
        )
        == 0
    )

    imported_bundle = tmp_path / "workspace_bundle_target_format_imported"
    capsys.readouterr()
    assert (
        main(
            [
                "import-bundle",
                str(source_bundle),
                "--output",
                str(imported_bundle),
                "--target-format",
                "yaml",
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["bundle_type"] == "workspace_bundle"
    assert rendered["target_format"] == "yaml"
    assert rendered["manifest_generated"] is False
    assert rendered["manifest_reindexed"] is False
    assert rendered["manifest_path"] == str(imported_bundle / "bundle_manifest.yaml")
    assert (imported_bundle / "bundle_manifest.yaml").exists()
    assert not (imported_bundle / "bundle_manifest.json").exists()

    imported_manifest = yaml.safe_load(
        (imported_bundle / "bundle_manifest.yaml").read_text(encoding="utf-8")
    )
    assert imported_manifest["format_version"] == "autoharness.workspace_bundle.v1"
    assert imported_manifest["artifact_format"] == "json"

    capsys.readouterr()
    assert main(["validate-bundle", str(imported_bundle), "--json"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["valid"] is True


def test_import_bundle_command_reindexes_stale_manifest_when_requested(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    source_bundle = tmp_path / "track_bundle_stale_source"
    assert (
        main(
            [
                "export-track-bundle",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(source_bundle),
                "--format",
                "json",
            ]
        )
        == 0
    )
    champion_dir = source_bundle / "champion"
    for child in champion_dir.iterdir():
        child.unlink()
    champion_dir.rmdir()

    imported_bundle = tmp_path / "track_bundle_reindexed_import"
    capsys.readouterr()
    assert (
        main(
            [
                "import-bundle",
                str(source_bundle),
                "--output",
                str(imported_bundle),
                "--reindex",
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["bundle_type"] == "track_bundle"
    assert rendered["manifest_generated"] is False
    assert rendered["manifest_reindexed"] is True
    assert rendered["valid"] is True

    rebuilt_manifest = json.loads(
        (imported_bundle / "bundle_manifest.json").read_text(encoding="utf-8")
    )
    assert rebuilt_manifest["format_version"] == "autoharness.track_bundle.v1"
    assert rebuilt_manifest["includes"]["champion_bundle"] is False
    assert rebuilt_manifest["artifacts"]["champion_bundle"] is None

    capsys.readouterr()
    assert main(["validate-bundle", str(imported_bundle), "--json"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["valid"] is True
    assert validated["missing_artifacts"] == []


def test_import_bundle_command_verify_source_fails_before_copying_invalid_source(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    source_bundle = tmp_path / "track_bundle_verify_source"
    assert (
        main(
            [
                "export-track-bundle",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(source_bundle),
                "--format",
                "json",
            ]
        )
        == 0
    )
    champion_dir = source_bundle / "champion"
    for child in champion_dir.iterdir():
        child.unlink()
    champion_dir.rmdir()

    imported_bundle = tmp_path / "track_bundle_verify_source_imported"
    capsys.readouterr()
    assert (
        main(
            [
                "import-bundle",
                str(source_bundle),
                "--output",
                str(imported_bundle),
                "--verify-source",
                "--json",
            ]
        )
        == 1
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["bundle_type"] == "track_bundle"
    assert rendered["source_verified"] is True
    assert rendered["import_performed"] is False
    assert rendered["valid"] is False
    assert rendered["missing_artifacts"] == ["champion"]
    assert rendered["validation_errors"] == ["Missing artifact: champion"]
    assert not imported_bundle.exists()


def test_import_bundle_command_verify_source_can_recurse_into_nested_bundles(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    source_bundle = tmp_path / "workspace_bundle_recursive_verify_source"
    assert (
        main(
            [
                "export-workspace-bundle",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(source_bundle),
                "--format",
                "json",
                "--skip-track-reports",
            ]
        )
        == 0
    )
    (source_bundle / "champions" / "main" / "source_champion.json").unlink()

    imported_bundle = tmp_path / "workspace_bundle_recursive_verify_source_imported"
    capsys.readouterr()
    assert (
        main(
            [
                "import-bundle",
                str(source_bundle),
                "--output",
                str(imported_bundle),
                "--verify-source",
                "--recursive",
                "--json",
            ]
        )
        == 1
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["bundle_type"] == "workspace_bundle"
    assert rendered["recursive"] is True
    assert rendered["source_verified"] is True
    assert rendered["import_performed"] is False
    assert rendered["nested_bundle_total"] == 1
    assert rendered["nested_bundles"][0]["path"] == "champions/main"
    assert rendered["validation_errors"] == [
        "Nested bundle champions/main: Missing artifact: source_champion.json"
    ]
    assert not imported_bundle.exists()


def test_import_bundle_command_allow_invalid_overrides_verify_source_abort(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    source_bundle = tmp_path / "track_bundle_allow_invalid_source"
    assert (
        main(
            [
                "export-track-bundle",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(source_bundle),
                "--format",
                "json",
            ]
        )
        == 0
    )
    champion_dir = source_bundle / "champion"
    for child in champion_dir.iterdir():
        child.unlink()
    champion_dir.rmdir()

    imported_bundle = tmp_path / "track_bundle_allow_invalid_imported"
    capsys.readouterr()
    assert (
        main(
            [
                "import-bundle",
                str(source_bundle),
                "--output",
                str(imported_bundle),
                "--verify-source",
                "--allow-invalid",
                "--json",
            ]
        )
        == 1
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["bundle_type"] == "track_bundle"
    assert rendered["source_verified"] is True
    assert rendered["source_valid"] is False
    assert rendered["source_validation_errors"] == ["Missing artifact: champion"]
    assert rendered["allow_invalid"] is True
    assert rendered["import_performed"] is True
    assert rendered["valid"] is False
    assert rendered["missing_artifacts"] == ["champion"]
    assert imported_bundle.exists()
    assert (imported_bundle / "bundle_manifest.json").exists()


def test_import_bundle_command_dry_run_reports_plan_without_writing_destination(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    source_bundle = tmp_path / "track_bundle_dry_run_source"
    assert (
        main(
            [
                "export-track-bundle",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(source_bundle),
                "--format",
                "json",
                "--skip-listings",
                "--skip-champion",
            ]
        )
        == 0
    )

    imported_bundle = tmp_path / "track_bundle_dry_run_imported"
    capsys.readouterr()
    assert (
        main(
            [
                "import-bundle",
                str(source_bundle),
                "--output",
                str(imported_bundle),
                "--reindex",
                "--target-format",
                "yaml",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["bundle_type"] == "track_bundle"
    assert rendered["dry_run"] is True
    assert rendered["would_import"] is True
    assert rendered["import_performed"] is False
    assert rendered["manifest_generated"] is False
    assert rendered["manifest_reindexed"] is True
    assert rendered["target_format"] == "yaml"
    assert rendered["valid"] is True
    assert rendered["bundle_path"] == str(imported_bundle)
    assert rendered["manifest_path"] == str(imported_bundle / "bundle_manifest.yaml")
    assert not imported_bundle.exists()


def test_import_bundle_command_can_reindex_nested_bundles_when_recursive(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    source_bundle = tmp_path / "track_bundle_recursive_import_reindex_source"
    assert (
        main(
            [
                "export-track-bundle",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(source_bundle),
                "--format",
                "json",
            ]
        )
        == 0
    )
    (source_bundle / "champion" / "champion.json").unlink()

    imported_bundle = tmp_path / "track_bundle_recursive_import_reindex_imported"
    capsys.readouterr()
    assert (
        main(
            [
                "import-bundle",
                str(source_bundle),
                "--output",
                str(imported_bundle),
                "--reindex",
                "--recursive",
                "--target-format",
                "yaml",
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["bundle_type"] == "track_bundle"
    assert rendered["recursive"] is True
    assert rendered["valid"] is True
    assert rendered["nested_bundle_total"] == 1
    assert len(rendered["nested_reindexed_bundles"]) == 1
    nested_bundle = rendered["nested_reindexed_bundles"][0]
    assert nested_bundle["path"] == "champion"
    assert nested_bundle["manifest_path"] == str(imported_bundle / "champion" / "champion.yaml")
    assert nested_bundle["written_format"] == "yaml"
    assert (imported_bundle / "champion" / "champion.yaml").exists()
    assert not (imported_bundle / "champion" / "champion.json").exists()

    capsys.readouterr()
    assert main(["validate-bundle", str(imported_bundle), "--recursive", "--json"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["valid"] is True
    assert validated["nested_bundle_total"] == 1
    assert validated["nested_bundles"][0]["valid"] is True


def test_import_bundle_command_supports_yaml_manifests_for_champion_bundles(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="main-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "main-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    source_bundle = tmp_path / "champion_bundle_target_format_source"
    assert (
        main(
            [
                "export-champion",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--output",
                str(source_bundle),
            ]
        )
        == 0
    )

    imported_bundle = tmp_path / "champion_bundle_target_format_imported"
    capsys.readouterr()
    assert (
        main(
            [
                "import-bundle",
                str(source_bundle),
                "--output",
                str(imported_bundle),
                "--target-format",
                "yaml",
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["bundle_type"] == "champion_bundle"
    assert rendered["target_format"] == "yaml"
    assert rendered["manifest_path"] == str(imported_bundle / "champion.yaml")
    assert (imported_bundle / "champion.yaml").exists()
    assert not (imported_bundle / "champion.json").exists()

    capsys.readouterr()
    assert main(["show-bundle", str(imported_bundle), "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["bundle_type"] == "champion_bundle"
    assert shown["manifest_path"] == str(imported_bundle / "champion.yaml")

    capsys.readouterr()
    assert main(["validate-bundle", str(imported_bundle), "--json"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["valid"] is True


def test_show_record_and_promotion_commands(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text('{"pass_rate": 1.0}\n', encoding="utf-8")
    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
            "parsed_artifact_sources": {
                "metrics": [
                    {
                        "origin": "metrics_parser.path",
                        "path": str(metrics_path.resolve()),
                    }
                ]
            },
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        hypothesis="Keep the smoke command passing",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )

    record_output_path = tmp_path / "record.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-record",
                "--workspace-id",
                "demo",
                "--record-id",
                record.record_id,
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(record_output_path),
            ]
        )
        == 0
    )
    rendered_record = json.loads(capsys.readouterr().out)
    assert rendered_record["record_id"] == record.record_id
    assert rendered_record["stage"] == "validation"
    assert rendered_record["status"] == "success"
    assert rendered_record["record_path"].endswith(f"{record.record_id}.json")
    assert json.loads(record_output_path.read_text(encoding="utf-8")) == rendered_record

    promotion_output_path = tmp_path / "promotion.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-promotion",
                "--workspace-id",
                "demo",
                "--promotion-id",
                promotion.promotion_id,
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(promotion_output_path),
            ]
        )
        == 0
    )
    rendered_promotion = json.loads(capsys.readouterr().out)
    assert rendered_promotion["promotion_id"] == promotion.promotion_id
    assert rendered_promotion["record_id"] == record.record_id
    assert rendered_promotion["promotion_path"].endswith(f"{promotion.promotion_id}.json")
    assert rendered_promotion["diff_path"].endswith(f"{promotion.promotion_id}.patch")
    assert rendered_promotion["parsed_artifact_sources_path"].endswith(
        f"{promotion.promotion_id}.parsed_artifact_sources.json"
    )
    assert json.loads(promotion_output_path.read_text(encoding="utf-8")) == rendered_promotion


def test_show_promotions_command(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "create-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    main_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=main_record)
    main_promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=main_record,
        target_root=tmp_path / "main-target",
        notes="Promote the main candidate",
        edit_restore={"status": "kept"},
    )
    persist_promotion_record(
        root=workspaces_root,
        promotion=main_promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )

    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text('{"pass_rate": 1.0}\n', encoding="utf-8")
    alt_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="alt-smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "alt-smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
            "parsed_artifact_sources": {
                "metrics": [
                    {
                        "origin": "metrics_parser.path",
                        "path": str(metrics_path.resolve()),
                    }
                ]
            },
        },
        dry_run=False,
        workspace_id="demo",
        track_id="alt",
        iteration_id="iter_0002",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=alt_record)
    alt_promotion = create_promotion_record(
        workspace_id="demo",
        track_id="alt",
        record=alt_record,
        target_root=tmp_path / "alt-target",
        notes="Promote the alt candidate",
        edit_restore={"status": "kept"},
    )
    persist_promotion_record(
        root=workspaces_root,
        promotion=alt_promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )

    promotion_output_path = tmp_path / "promotions.json"
    export_output_path = tmp_path / "promotions.report"
    capsys.readouterr()
    assert (
        main(
            [
                "show-promotions",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(promotion_output_path),
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["track_id"] is None
    assert rendered["parsed_artifact_sources_only"] is False
    assert rendered["parsed_artifact_sources_total"] == 1
    assert len(rendered["promotions"]) == 2
    assert {item["track_id"] for item in rendered["promotions"]} == {"main", "alt"}
    assert sum(1 for item in rendered["promotions"] if item["has_parsed_artifact_sources"]) == 1
    assert json.loads(promotion_output_path.read_text(encoding="utf-8")) == rendered

    capsys.readouterr()
    assert (
        main(
            [
                "show-promotions",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--parsed-artifact-sources-only",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    filtered_rendered = json.loads(capsys.readouterr().out)
    assert filtered_rendered["track_id"] == "alt"
    assert filtered_rendered["parsed_artifact_sources_only"] is True
    assert filtered_rendered["parsed_artifact_sources_total"] == 1
    assert len(filtered_rendered["promotions"]) == 1
    assert filtered_rendered["promotions"][0]["track_id"] == "alt"
    assert filtered_rendered["promotions"][0]["record_id"] == alt_record.record_id
    assert filtered_rendered["promotions"][0]["has_parsed_artifact_sources"] is True
    assert filtered_rendered["promotions"][0]["parsed_artifact_sources_path"].endswith(
        f"{alt_promotion.promotion_id}.parsed_artifact_sources.json"
    )

    capsys.readouterr()
    assert (
        main(
            [
                "show-promotions",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--parsed-artifact-sources-only",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert "Track filter: alt" in text_output
    assert "Parsed artifact sources: 1" in text_output
    assert "Filter: parsed artifact sources only" in text_output
    assert "track=main" not in text_output
    assert "track=alt" in text_output
    assert "parsed_artifact_sources=yes" in text_output

    capsys.readouterr()
    assert (
        main(
            [
                "export-promotions",
                "--workspace-id",
                "demo",
                "--track-id",
                "alt",
                "--parsed-artifact-sources-only",
                "--root",
                str(workspaces_root),
                "--format",
                "yaml",
                "--output",
                str(export_output_path),
            ]
        )
        == 0
    )
    export_text_output = capsys.readouterr().out
    assert "Workspace: demo" in export_text_output
    assert "Promotions exported: 1" in export_text_output
    assert "Parsed artifact sources: 1" in export_text_output
    assert "Format: yaml" in export_text_output
    assert f"Export path: {export_output_path}" in export_text_output

    exported = yaml.safe_load(export_output_path.read_text(encoding="utf-8"))
    assert exported["format_version"] == "autoharness.promotion_export.v1"
    assert exported["workspace_id"] == "demo"
    assert exported["track_id"] == "alt"
    assert exported["parsed_artifact_sources_only"] is True
    assert exported["parsed_artifact_sources_total"] == 1
    assert len(exported["promotions"]) == 1
    assert exported["promotions"][0]["track_id"] == "alt"
    assert exported["promotions"][0]["record_id"] == alt_record.record_id
    assert exported["promotions"][0]["has_parsed_artifact_sources"] is True

    capsys.readouterr()
    assert main(["show-listing-file", str(export_output_path), "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["listing_type"] == "promotion_export"
    assert shown["workspace_id"] == "demo"
    assert shown["item_total"] == 1
    assert shown["summary_total"] == 1

    capsys.readouterr()
    assert main(["validate-listing-file", str(export_output_path), "--json"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["listing_type"] == "promotion_export"
    assert validated["valid"] is True


def test_show_track_artifacts_command(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    main(["setup", "--output", str(settings)])

    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text('{"pass_rate": 1.0}\n', encoding="utf-8")
    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
            "parsed_artifact_sources": {
                "metrics": [
                    {
                        "origin": "metrics_parser.path",
                        "path": str(metrics_path.resolve()),
                    }
                ]
            },
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
        stage="validation",
    )
    persist_benchmark_record(root=workspaces_root, record=record)
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote the validated candidate",
        edit_restore={"status": "kept"},
    )
    promotion_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=record,
        promotion=promotion,
        promotion_artifacts=promotion_artifacts,
    )

    artifact_output_path = tmp_path / "track_artifacts.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-track-artifacts",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(artifact_output_path),
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["workspace_id"] == "demo"
    assert rendered["track_id"] == "main"
    assert rendered["exists"]["campaign"] is True
    assert rendered["exists"]["promotion_policy"] is True
    assert rendered["exists"]["track_policy"] is True
    assert rendered["exists"]["champion"] is True
    assert rendered["registry_records"][0]["record_id"] == record.record_id
    assert rendered["promotions"][0]["promotion_id"] == promotion.promotion_id
    assert rendered["promotions"][0]["diff_path"].endswith(f"{promotion.promotion_id}.patch")
    assert rendered["champion_artifacts"]["record_id"] == record.record_id
    assert rendered["champion_artifacts"]["promotion_id"] == promotion.promotion_id
    assert json.loads(artifact_output_path.read_text(encoding="utf-8")) == rendered


def test_campaign_preflight_defaults_appear_in_workspace_and_track_summaries(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    main(["setup", "--output", str(settings)])
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    preflight_script = tmp_path / "preflight_ok.py"
    preflight_script.write_text("print('ok')\n", encoding="utf-8")

    assert (
        main(
            [
                "set-workspace",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--campaign-preflight-command",
                f"{sys.executable} {preflight_script}",
                "--campaign-preflight-check",
                "python_compile",
                "--campaign-preflight-timeout-seconds",
                "12",
                "--campaign-max-preflight-retries",
                "2",
                "--campaign-repeat-count",
                "3",
                "--campaign-max-generation-total-tokens",
                "11",
                "--campaign-max-benchmark-total-cost",
                "1.5",
                "--campaign-allow-flaky-promotion",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "set-track",
                "--workspace-id",
                "demo",
                "--track-id",
                "main",
                "--root",
                str(workspaces_root),
                "--campaign-preflight-command",
                "python -c \"print('override')\"",
                "--campaign-preflight-check",
                "pytest_collect",
                "--campaign-preflight-timeout-seconds",
                "34",
                "--campaign-max-preflight-retries",
                "4",
                "--campaign-repeat-count",
                "5",
                "--campaign-max-generation-total-tokens",
                "13",
                "--campaign-max-benchmark-total-cost",
                "2.5",
                "--no-campaign-allow-flaky-promotion",
            ]
        )
        == 0
    )

    capsys.readouterr()
    assert (
        main(
            [
                "show-workspace-summary",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    workspace_summary = json.loads(capsys.readouterr().out)
    active_policy = workspace_summary["active_track_effective_campaign_policy"]
    assert active_policy["effective_policy"]["preflight_checks"] == ["pytest_collect"]
    assert active_policy["effective_policy"]["preflight_check_count"] == 1
    assert active_policy["effective_policy"]["preflight_command_count"] == 1
    assert active_policy["effective_policy"]["preflight_timeout_seconds"] == 34
    assert active_policy["effective_policy"]["max_preflight_retries"] == 4
    assert active_policy["effective_policy"]["repeat_count"] == 5
    assert active_policy["effective_policy"]["max_generation_total_tokens"] == 13
    assert active_policy["effective_policy"]["max_benchmark_total_cost"] == 2.5
    assert active_policy["effective_policy"]["allow_flaky_promotion"] is False
    assert active_policy["effective_sources"]["preflight_checks"] == "track_override"
    assert active_policy["effective_sources"]["preflight_commands"] == "track_override"
    assert active_policy["effective_sources"]["preflight_timeout_seconds"] == "track_override"
    assert active_policy["effective_sources"]["max_preflight_retries"] == "track_override"
    assert active_policy["effective_sources"]["repeat_count"] == "track_override"
    assert (
        active_policy["effective_sources"]["max_generation_total_tokens"]
        == "track_override"
    )
    assert (
        active_policy["effective_sources"]["max_benchmark_total_cost"]
        == "track_override"
    )
    assert (
        active_policy["effective_sources"]["allow_flaky_promotion"]
        == "track_override"
    )

    capsys.readouterr()
    assert (
        main(
            [
                "show-track-summary",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    track_summary = json.loads(capsys.readouterr().out)
    effective_policy = track_summary["effective_campaign_policy"]
    assert effective_policy["effective_policy"]["preflight_checks"] == ["pytest_collect"]
    assert effective_policy["effective_policy"]["preflight_check_count"] == 1
    assert effective_policy["effective_policy"]["preflight_command_count"] == 1
    assert effective_policy["effective_policy"]["preflight_timeout_seconds"] == 34
    assert effective_policy["effective_policy"]["max_preflight_retries"] == 4
    assert effective_policy["effective_policy"]["repeat_count"] == 5
    assert effective_policy["effective_policy"]["max_generation_total_tokens"] == 13
    assert effective_policy["effective_policy"]["max_benchmark_total_cost"] == 2.5
    assert effective_policy["effective_policy"]["allow_flaky_promotion"] is False
    assert effective_policy["effective_sources"]["preflight_checks"] == "track_override"
    assert effective_policy["effective_sources"]["preflight_commands"] == "track_override"
    assert effective_policy["effective_sources"]["repeat_count"] == "track_override"
    assert (
        effective_policy["effective_sources"]["max_generation_total_tokens"]
        == "track_override"
    )
    assert (
        effective_policy["effective_sources"]["max_benchmark_total_cost"]
        == "track_override"
    )
    assert (
        effective_policy["effective_sources"]["allow_flaky_promotion"]
        == "track_override"
    )


def test_transfer_champion_command_moves_active_champion_between_workspaces(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert main(["setup", "--output", str(settings)]) == 0
    for workspace_id in ("source", "dest"):
        assert (
            main(
                [
                    "init-workspace",
                    "--workspace-id",
                    workspace_id,
                    "--objective",
                    f"Optimize {workspace_id}",
                    "--benchmark",
                    "tau-bench-airline",
                    "--settings",
                    str(settings),
                    "--root",
                    str(workspaces_root),
                ]
            )
            == 0
        )

    source_target_root = tmp_path / "source-target"
    source_file = source_target_root / "src" / "agent.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("STATE = 'old'\n", encoding="utf-8")

    source_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="transfer-smoke",
        config={"benchmark_name": "transfer-smoke"},
        payload={
            "command": [sys.executable, "-c", "print('ok')"],
            "success": True,
            "metrics": {"pass_rate": 1.0},
            "edit_application": {
                "summary": "Set the transferred champion state",
                "status": "applied",
                "operations": [
                    {
                        "type": "write_file",
                        "path": "src/agent.py",
                        "content": "STATE = 'new'\n",
                    }
                ],
            },
            "edit_restore": {},
            "staging": {"status": "applied"},
        },
        dry_run=False,
        workspace_id="source",
        track_id="main",
        hypothesis="Source champion",
        notes="Initial promoted source champion",
        stage="screening",
    )
    persist_benchmark_record(root=workspaces_root, record=source_record)
    source_promotion = create_promotion_record(
        workspace_id="source",
        track_id="main",
        record=source_record,
        target_root=source_target_root,
        notes="Promote source champion",
        edit_restore={},
    )
    source_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=source_promotion,
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=source_record,
        promotion=source_promotion,
        promotion_artifacts=source_artifacts,
    )
    source_state = load_workspace_state(workspaces_root, "source")
    update_state_after_promotion(
        root=workspaces_root,
        workspace_id="source",
        state=source_state,
        record_id=source_record.record_id,
    )

    destination_target_root = tmp_path / "dest-target"
    destination_file = destination_target_root / "src" / "agent.py"
    destination_file.parent.mkdir(parents=True)
    destination_file.write_text("STATE = 'old'\n", encoding="utf-8")

    capsys.readouterr()
    assert (
        main(
            [
                "transfer-champion",
                "--source-workspace-id",
                "source",
                "--workspace-id",
                "dest",
                "--target-root",
                str(destination_target_root),
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)

    assert rendered["source"]["workspace_id"] == "source"
    assert rendered["source"]["record_id"] == source_record.record_id
    assert rendered["destination"]["workspace_id"] == "dest"
    assert rendered["destination"]["track_id"] == "main"
    assert rendered["destination"]["record_id"] != source_record.record_id
    assert destination_file.read_text(encoding="utf-8") == "STATE = 'new'\n"

    destination_state = load_workspace_state(workspaces_root, "dest")
    assert (
        destination_state.current_champion_experiment_id
        == rendered["destination"]["record_id"]
    )

    destination_manifest = load_champion_manifest(
        root=workspaces_root,
        workspace_id="dest",
        track_id="main",
    )
    assert destination_manifest.record_id == rendered["destination"]["record_id"]
    assert destination_manifest.target_root == str(destination_target_root.resolve())

    destination_record = load_benchmark_record(
        root=workspaces_root,
        workspace_id="dest",
        track_id="main",
        record_id=rendered["destination"]["record_id"],
    )
    assert destination_record.payload["transfer_source"] == {
        "workspace_id": "source",
        "track_id": "main",
        "record_id": source_record.record_id,
        "promotion_id": source_promotion.promotion_id,
        "champion_manifest_path": str(
            workspaces_root / "source" / "tracks" / "main" / "champion.json"
        ),
    }


def test_transfer_root_champions_command_fans_out_to_multiple_workspaces(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    assert main(["setup", "--output", str(settings)]) == 0
    for workspace_id in ("source", "dest_a", "dest_b"):
        assert (
            main(
                [
                    "init-workspace",
                    "--workspace-id",
                    workspace_id,
                    "--objective",
                    f"Optimize {workspace_id}",
                    "--benchmark",
                    "tau-bench-airline",
                    "--settings",
                    str(settings),
                    "--root",
                    str(workspaces_root),
                ]
            )
            == 0
        )

    source_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="transfer-smoke",
        config={"benchmark_name": "transfer-smoke"},
        payload={
            "command": [sys.executable, "-c", "print('ok')"],
            "success": True,
            "metrics": {"pass_rate": 1.0},
            "edit_application": {
                "summary": "Set the transferred champion state",
                "status": "applied",
                "operations": [
                    {
                        "type": "write_file",
                        "path": "src/agent.py",
                        "content": "STATE = 'batch'\n",
                    }
                ],
            },
            "edit_restore": {},
            "staging": {"status": "applied"},
        },
        dry_run=False,
        workspace_id="source",
        track_id="main",
        hypothesis="Source champion",
        notes="Batch promoted source champion",
        stage="screening",
    )
    persist_benchmark_record(root=workspaces_root, record=source_record)
    source_target_root = tmp_path / "source-target-batch"
    source_target_root.mkdir()
    source_promotion = create_promotion_record(
        workspace_id="source",
        track_id="main",
        record=source_record,
        target_root=source_target_root,
        notes="Promote source champion",
        edit_restore={},
    )
    source_artifacts = persist_promotion_record(
        root=workspaces_root,
        promotion=source_promotion,
    )
    persist_champion_manifest(
        root=workspaces_root,
        record=source_record,
        promotion=source_promotion,
        promotion_artifacts=source_artifacts,
    )
    source_state = load_workspace_state(workspaces_root, "source")
    update_state_after_promotion(
        root=workspaces_root,
        workspace_id="source",
        state=source_state,
        record_id=source_record.record_id,
    )

    target_root_base = tmp_path / "deployments"
    for workspace_id in ("dest_a", "dest_b"):
        target_file = target_root_base / workspace_id / "src" / "agent.py"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text("STATE = 'old'\n", encoding="utf-8")

    capsys.readouterr()
    assert (
        main(
            [
                "transfer-root-champions",
                "--source-workspace-id",
                "source",
                "--workspace-id",
                "dest_a",
                "--workspace-id",
                "dest_b",
                "--target-root-base",
                str(target_root_base),
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)

    assert rendered["status"] == "completed"
    assert rendered["workspace_total"] == 2
    assert rendered["success_workspace_total"] == 2
    assert rendered["failed_workspace_total"] == 0
    assert len(rendered["transfers"]) == 2

    for workspace_id in ("dest_a", "dest_b"):
        destination_file = target_root_base / workspace_id / "src" / "agent.py"
        assert destination_file.read_text(encoding="utf-8") == "STATE = 'batch'\n"
        destination_state = load_workspace_state(workspaces_root, workspace_id)
        assert destination_state.current_champion_experiment_id is not None
