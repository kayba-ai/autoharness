# autoharness

autoharness is a standalone control plane for improving agent harnesses directly.

It does not train models or ship a built-in inner learning loop. It manages bounded or unbounded harness optimization campaigns over prompts, middleware, config, and selected source files.

## Thesis

Most harness optimizers stop at:

- edit target files
- run evals
- keep or discard

autoharness adds experiment discipline on top:

- explicit autonomy modes
- workspace / track / campaign separation
- one hypothesis per iteration
- pinned evaluator policy per campaign
- structured intervention records
- durable registry lineage instead of branch history
- room for screening, validation, and transfer gates

## Autonomy Modes

autoharness lets the operator choose how much authority the meta-agent gets.

| Mode | Meaning |
|---|---|
| `proposal` | Proposal-first. The meta-agent may analyze and draft patches, but it must not apply them. |
| `bounded` | Bounded autopatch. The meta-agent may apply changes only inside approved editable surfaces. Protected surfaces remain proposal-only. |
| `full` | Full harness optimizer. The meta-agent may edit the harness broadly, except for explicitly protected surfaces. |

The current CLI defaults to `full` during setup, because some users want the system to start in optimizer mode immediately. Teams that need tighter controls should run setup with `--autonomy bounded` or `--autonomy proposal`.

## Core Concepts

- `workspace`: the broader optimization effort
- `track`: one comparable evaluation lane inside a workspace
- `campaign`: one benchmark-scoped comparable unit with a pinned evaluator policy
- `intervention`: one explicit change hypothesis, tagged by level and target

## Quickstart

```bash
cd autoharness
python -m venv .venv
source .venv/bin/activate
pip install -e .
autoharness setup --autonomy bounded --editable-surface src/agent --editable-surface prompts
autoharness init-workspace \
  --workspace-id airline-search \
  --objective "Improve pass@1 without unacceptable latency regressions" \
  --benchmark tau-bench-airline
autoharness run-benchmark \
  --adapter generic_command \
  --config benchmark.yaml \
  --stage validation
```

This creates:

```text
.autoharness/
  settings.yaml
  workspaces/
    airline-search/
      workspace.json
      state.json
      program.md
      tracks/
        main/
          campaign.json
          registry/
```

## Design Direction

This repo is the open-source outer-loop layer only. The intended next steps are:

1. continue refining the campaign and registry model
2. add benchmark adapters and eval runners
3. add screening / validation / transfer stages
4. add proposal generation and patch application behind the selected autonomy mode

## Status

This scaffold currently includes:

- autonomy policy setup
- workspace bootstrapping
- benchmark adapter catalog
- `autoharness list-benchmarks --json` for machine-readable benchmark catalog inspection
- `autoharness show-benchmark` for adapter-specific staging, parser, native artifact, and task-identity capability inspection
- `autoharness init-benchmark-config` for adapter-owned starter config scaffolds and named presets
- `autoharness show-benchmark-config` / `autoharness validate-benchmark-config` for standalone composed-config inspection and validation before execution
- `autoharness list-generators` / `autoharness show-generator` for proposal generator catalog inspection and provider option discovery
- implemented adapter runtime for `generic_command`, `pytest`, `harbor`, `tau2_bench`, `hal`, and `car_bench`
- `autoharness run-benchmark` for direct adapter execution
- repeated validation runs via `--repeat`, with optional seed stepping via `--seed-field`
- parsed metrics via config-driven `metrics_parser`
- parsed per-task outcomes via config-driven `task_results_parser`
- adapter-declared task identity hints for stable case matching and tier-based weighting
- native artifact ingestion for `tau2_bench`, `hal`, and `harbor`
- parsed artifact provenance retained in benchmark payloads, iteration artifacts, and promotion records
- stage-aware evaluation via `--stage {screening,validation,holdout,transfer}`
- confidence-gated stage decisions for validation, holdout, and transfer
- optional baseline comparison against an explicit record or the current champion
- paired per-seed and per-task baseline comparison when the payload exposes aligned outcomes
- file-backed benchmark records per track
- `autoharness run-iteration` for one-hypothesis execution and workspace state updates
- `autoharness plan-iteration` for policy-aware run command scaffolding before execution
- `autoharness run-planned-iteration` to replay a saved plan JSON without rebuilding flags
- edit-plan application with `proposal`, `bounded`, and `full` autonomy enforcement
- transactional edit sessions that revert by default, with an explicit keep option
- per-iteration `candidate.patch` artifacts
- `autoharness promote` to replay a recorded candidate onto a target harness and mark it champion
- track-level `champion.json` manifests that point at the active champion record, promotion patch, and provenance artifacts
- track-level `promotion_policy.json` files that pin compare/promote thresholds for each track
- `autoharness show-promotion-policy` and `autoharness set-promotion-policy` for operator-facing policy inspection and updates
- track-level `track_policy.json` files that pin search, promotion, and regression benchmark targets per track
- `autoharness show-track-policy` and `autoharness set-track-policy` for operator-facing benchmark routing updates
- track and workspace policy support for `search`, `promotion`, and `regression` preset names in addition to benchmark ids
- `autoharness show-track` and `autoharness set-track` for operator-facing track metadata, evaluator updates, and per-track campaign automation overrides
- `autoharness list-preflight-checks` and `autoharness show-preflight-check` for discovering the built-in cheap preflight validation catalog
- `autoharness run-campaign`, `autoharness run-workspace-campaigns`, `autoharness export-workspace-campaign-run-report`, `autoharness run-root-campaigns`, `autoharness export-root-campaign-run-report`, `autoharness resume-campaign`, `autoharness show-campaign`, `autoharness show-campaigns`, `autoharness show-campaign-report-file`, `autoharness validate-campaign-report-file`, `autoharness export-workspace-campaign-report`, `autoharness export-workspace-campaign-bundle`, `autoharness export-root-campaign-bundle`, `autoharness show-campaign-artifacts`, `autoharness export-campaign-report`, and `autoharness export-campaign-bundle` for resumable campaign execution, workspace-level and root-level campaign fan-out, campaign-level inspection, versioned batch-run and persisted-run exports, report-file reopening/validation, and portable campaign handoff artifacts
- `autoharness show-workspace`, `autoharness set-workspace`, `autoharness archive-workspace`, and `autoharness purge-workspace` for workspace metadata, fallback benchmark routing, workspace-level campaign defaults, and lifecycle control
- `autoharness show-root-summary` and `autoharness show-workspace-summary` for aggregate inspection across selected workspaces or one workspace
- `autoharness export-root-summary`, `autoharness export-root-report`, `autoharness export-root-bundle`, `autoharness export-workspace-summary`, `autoharness export-workspace-report`, `autoharness export-workspace-bundle`, and `autoharness export-track-bundle` for versioned handoff artifacts
- `autoharness show-bundle`, `autoharness validate-bundle`, `autoharness reindex-bundle`, and `autoharness import-bundle` for manifest-only inspection, validation, manifest repair, and relocation of exported workspace, track, and champion bundles, including manifest format normalization with `reindex-bundle --format json|yaml` and `import-bundle --target-format json|yaml`, plus recursive nested champion-bundle inspection, auditing, and restamping with `--recursive`
- `autoharness show-tracks`, `autoharness create-track`, `autoharness archive-track`, `autoharness purge-track`, and `autoharness switch-track` for multi-track workspace lifecycle
- `autoharness show-track-summary` for per-track record, promotion, and champion inspection
- `autoharness show-records`, `autoharness export-records`, `autoharness show-record`, `autoharness show-promotions`, `autoharness export-promotions`, and `autoharness show-promotion` for direct record and promotion inspection
- `autoharness generate-proposal`, `autoharness show-proposal`, `autoharness show-proposals`, `autoharness export-proposals`, `autoharness apply-proposal`, and `autoharness run-proposal` for proposal-first edit-plan preview, persistence, application, proposal-backed execution, and generator-driven proposal synthesis
- `autoharness show-track-artifacts` for track-level file inspection
- `autoharness show-iteration`, `autoharness show-iterations`, and `autoharness export-iterations` for iteration-level inspection and export
- `autoharness show-champion` and `autoharness export-champion` for operator-facing champion inspection and bundle export
- `autoharness compare-to-champion` to recompute stage and baseline deltas against the active champion
- `autoharness promote-from-compare` to gate promotion on a fresh champion comparison instead of a separate manual step
- adapter-aware copy staging for isolated candidate execution, with `auto` as the default mode
- Harbor support for dataset, dataset path, task, and config entrypoints
- adapter-specific staging signals for nested benchmark config paths in HAL and Tau2
- campaign and intervention primitives
- a CLI entrypoint

It still does not manage true parallel distributed search or cross-root automation policy yet, but it now supports beam-style candidate sourcing and one level of orchestration above a single workspace.

## Stage Overrides

Benchmark configs can include optional stage-specific overlays:

```yaml
benchmark_name: search-smoke
command: ["python", "-c", "print('ok')"]

stage_overrides:
  holdout:
    benchmark_name: holdout-smoke
```

The CLI applies the selected stage overlay before execution, then records the stage gate outcome in the benchmark payload and iteration summary.

## Stage Gates

- `screening` uses direct threshold gating
- `validation`, `holdout`, and `transfer` use confidence bounds over repeated runs

Current defaults use an 85% confidence level:

- success/failure rates use a Wilson interval
- numeric metrics such as `pass_rate` use a normal-approximation interval over the repeated run means

That means stage decisions can now be:

- `passed`
- `failed`
- `inconclusive`
- `planned` for dry-runs

## Baseline Comparison

When a workspace track already has comparable records, you can tighten a stage gate with:

- `--baseline-record-id <record>`
- `--baseline-source champion`

and optionally require a positive margin with:

- `--min-improvement <float>`
- `--max-regressed-tasks <int>`
- `--max-regressed-task-fraction <float>`
- `--max-regressed-task-weight <float>`
- `--max-regressed-task-weight-fraction <float>`
- `--task-regression-margin <float>`

If a baseline is provided, the stage must still clear its absolute gate first. After that, the candidate must also improve beyond the baseline interval or point estimate. Otherwise the result becomes `failed` or `inconclusive` instead of being promoted on an absolute threshold alone.

When task results are available, those extra regression controls let you block a candidate that improves on average but still backslides on too many matched tasks or on too much weighted critical coverage.

When both candidate and baseline expose aligned outcomes, autoharness now prefers matched comparisons over aggregate interval overlap. It compares:

- per-task deltas first, when both payloads expose task ids
- per-run deltas next, when repeated runs align by `seed` or `validation_index`
- aggregate intervals only when neither of those richer comparisons is available

## Metrics Parser

Adapters backed by command execution can attach parsed metrics to their run result with a config like:

```yaml
metrics_parser:
  format: json_stdout
```

Supported formats are:

- `json_stdout`
- `json_stderr`
- `json_file`

`json_file` also accepts `path`, and all formats can use optional `key_path` and `include` fields to narrow the decoded metric mapping.

## Task Results Parser

Command-backed adapters can also attach normalized task-level outcomes:

```yaml
task_results_parser:
  format: json_stdout
  key_path: ["tasks"]
  match_key_field: case_id
  tier_field: tier
  tier_weights:
    critical: 5.0
    edge: 1.0
```

The decoded payload may be either:

- a list of task-result mappings
- or a mapping from `task_id -> score` or `task_id -> result`

The parser normalizes each item into:

```yaml
- task_id: example-task
  score: 1.0
```

The normalized result keeps the original task fields alongside the canonical `task_id` and `score`, so downstream comparison logic can surface richer per-case metadata for regressions.

`match_key_field` controls which stable task or case key is used for baseline matching. `tier_field`, `weight_field`, and `tier_weights` let holdout and transfer gates weight regressions instead of treating every task equally.

By default it looks for `task_id`, then `id`, and it resolves the score from `score`, `success`, or `passed` unless you override those field names in the parser config.

## Native Benchmark Artifacts

The benchmark-specific adapters can also ingest structured artifacts directly, without requiring `metrics_parser` or `task_results_parser`.

- `tau2_bench`
  - uses `save_to` to read `data/simulations/<save_to>/results.json`
  - or accepts `results_json_path`
- `hal`
  - accepts `summary_json_path` and `result_json_path`
- `harbor`
  - accepts `summary_json_path` and `result_json_path`

For native artifact parsing, task identity hints can also live at the top level:

```yaml
task_identity_profile:
  match_key_field: case_id
  tier_field: tier
  tier_weights:
    critical: 5.0
    edge: 1.0
```

That lets you use stable case ids and weighted regression gates even when the benchmark adapter is hydrating task results from its own artifact files.

For operator-side planning, `autoharness show-benchmark --adapter <id> --json` renders the built-in catalog metadata together with any implemented adapter capabilities, including required config fields, staging defaults, supported parser formats, native artifact fields, and default task-identity hints.

To start from a valid adapter-owned baseline instead of hand-assembling YAML, use `autoharness init-benchmark-config --adapter <id> --output <path>`. The scaffold comes from the adapter implementation itself, so it stays aligned with the same capability metadata exposed by `show-benchmark`.

Adapters can now publish named starter presets as well. `show-benchmark --preset <name>` renders the selected preset, and `init-benchmark-config --preset search|promotion|native-artifact` writes that variant directly. The default filename becomes `<adapter>.<preset>.yaml` for non-default presets, so you can keep search and promotion configs side by side without renaming them by hand.

When you want to inspect or validate one adapter config without running a benchmark, `autoharness show-benchmark-config --adapter <id> [--config path] [--preset name] [--set dotted.path=value]` composes the effective config, optionally applies one stage override, and renders the normalized invocation that adapter would execute. `autoharness validate-benchmark-config ...` runs the same composition path but returns a failing exit code with structured validation errors when the composed config cannot be translated into a valid invocation.

autoharness also records which file-backed artifacts were used to parse metrics and task results. Those paths are retained in benchmark payload metadata and surfaced in iteration summaries as `parsed_artifact_sources`, with a dedicated `parsed_artifact_sources.json` artifact for review. Promotion records retain the same provenance and persist a promotion-side `*.parsed_artifact_sources.json` artifact, and the active track champion is summarized in `champion.json`, so a champion handoff stays tied to the concrete benchmark files that justified it. When a benchmark is repeated, the provenance is aggregated with `validation_indices` and any attached seeds so the parsed metrics and task outcomes stay traceable back to concrete source files.

Operators can inspect that state directly with `autoharness show-champion`, export a portable bundle with `autoharness export-champion`, compare another recorded candidate back to the active champion with `autoharness compare-to-champion`, promote directly from that recomputed decision with `autoharness promote-from-compare`, or transfer one active champion into another workspace track with `autoharness transfer-champion --source-workspace-id source --workspace-id dest --target-root deploy_root`. The transfer flow clones the source champion record into the destination track, replays its recorded edit application onto the destination target root, persists a fresh destination promotion record, and then marks the destination record as the current champion. For root-level fanout, `autoharness transfer-root-champions --source-workspace-id source --workspace-id dest_a --workspace-id dest_b --target-root-base deployments` applies that same handoff across multiple destination workspaces and writes each target under `<target-root-base>/<workspace_id>`. `show-champion` now resolves any copied `source_plan.json` iteration artifact for the active champion, `show-track-artifacts` surfaces planned-run provenance at the track level, and the export command writes the champion manifest, source track manifest, benchmark record, promotion record, patch, provenance artifacts, and any copied `source_plan.json` iteration artifact into one directory. `autoharness show-bundle <bundle_dir>` can inspect that exported champion bundle later from the saved `champion.json` manifest without loading any workspace state, and `show-bundle --recursive` now also surfaces nested champion bundle validity and missing-artifact status inside workspace and track bundles. `autoharness validate-bundle <bundle_dir>` returns a non-zero exit code when referenced artifacts are missing, `autoharness reindex-bundle <bundle_dir>` can restamp the manifest to match the artifacts that are still present, and `autoharness import-bundle <bundle_dir> --output imported_dir` copies that saved bundle into a new location and validates it immediately. When you want repair-on-import instead of strict manifest fidelity, `import-bundle --reindex` rewrites the destination manifest to match the copied artifacts. When you want to normalize an existing saved manifest in place, use `reindex-bundle --format json|yaml`. Add `--recursive` to `show-bundle`, `validate-bundle`, `reindex-bundle`, or `import-bundle` when a workspace or track bundle should also inspect, audit, or restamp the embedded champion bundle manifests under `champions/*` or `champion/`. On import, the recursive flag applies to source preflight, dry-run prediction, destination validation, and any requested reindexing. When you want to normalize the imported manifest itself, add `--target-format json|yaml`. When you want strict preflight checks instead, `import-bundle --verify-source` validates the source bundle before copying and fails early if its manifest is already stale. When you still want the copy for forensic work, `import-bundle --verify-source --allow-invalid` keeps the preflight result in the output but proceeds with the copy anyway. When you want to inspect the import decision without writing the destination bundle yet, `import-bundle --dry-run` reports the predicted manifest path, preflight outcome, and validation result without copying files.

Each track also carries a `promotion_policy.json` file. `compare-to-champion` and `promote-from-compare` read that file first for pinned defaults such as `stage`, `min_success_rate`, `min_improvement`, and task-regression limits, and then let explicit CLI flags override those pinned values when needed. Operators can inspect or update that file without editing JSON directly by using `autoharness show-promotion-policy` and `autoharness set-promotion-policy`.

Each track also carries a `track_policy.json` file. `run-iteration`, `compare-to-champion`, and `promote-from-compare` resolve benchmark targets such as `search_benchmark`, `promotion_benchmark`, and `regression_benchmark` from that file before falling back to the workspace defaults. Operators can inspect or update that routing without editing `workspace.json` manually by using `autoharness show-track-policy` and `autoharness set-track-policy`.

Those policy files can now also pin `search_preset`, `promotion_preset`, and `regression_preset`. During `run-benchmark` and `run-iteration`, autoharness resolves config presets with this precedence: explicit `--preset`, then the effective stage preset from track policy, then the workspace fallback preset. The selected preset is composed under the provided config file, so operators can keep small override files while still centralizing stage defaults in policy.

`run-benchmark` and `run-iteration` no longer require a full config file when a preset is pinned. You can omit `--config` entirely and provide only inline overrides with repeatable `--set dotted.path=value` flags, or combine a small override file with additional `--set` entries. That makes common stage runs possible from policy plus a handful of local overrides instead of a full hand-authored config.

For inspection, `show-track-policy` now reports the effective routing together with a per-field source label such as `track_policy`, `workspace_fallback`, `track_default`, or `unset`. `show-workspace` also includes the active track's effective policy and source map, so operators can see whether a preset or benchmark target is coming from the track file or the workspace fallback without diffing JSON by hand.

For launch scaffolding, `autoharness plan-iteration` resolves the active track, stage benchmark target, preset source, effective config, and planned adapter invocation, and it emits a ready-to-run `autoharness run-iteration ...` command plus a generated hypothesis label when you do not provide one. That gives operators a reproducible preview of what the next stage run will use before they actually execute it. New saved plan files now carry `format_version: autoharness.iteration_plan.v1`, and `autoharness show-plan-file <path>` / `autoharness validate-plan-file <path>` reopen or validate those saved plan artifacts directly while still accepting older unversioned plans as legacy; `autoharness show-artifact-file <path>` / `autoharness validate-artifact-file <path>` can auto-detect the same saved plans too. When you want to turn that preview into concrete artifacts, `--write-config <path>` materializes the composed stage-ready config, `--write-hypothesis <path>` writes the planned hypothesis text, and `--write-command <path>` writes the suggested shell command as an executable script. When a materialized config is written, the suggested command is rewritten to consume that config directly. Saved plan JSON now also records the planning working directory, and `autoharness run-planned-iteration --plan <path>` replays the saved `run-iteration` command from that captured cwd so relative config paths resolve the same way they did at planning time. Replayed runs also stamp the resulting record and iteration summary with `source_plan_path`, persist a copy of the full plan as `iterations/<id>/source_plan.json`, and expose that copied payload through both `show-iteration` and `show-record`, so later inspection can recover the exact planned config and command even if the original plan file moves.

Track metadata is also pinned in both `workspace.json` and `tracks/<track>/campaign.json`. Operators can inspect or update fields such as `objective`, `kind`, `benchmark_reference_ids`, evaluator settings, and per-track `campaign_policy` overrides without hand-editing JSON by using `autoharness show-track` and `autoharness set-track`.

Workspace-level metadata stays in `workspace.json`, with the active track mirrored into `state.json`. Operators can inspect or update fields such as `objective`, `domain`, `active_track_id`, workspace notes, the fallback `benchmark_policy` routing, and workspace-level `campaign_policy` defaults without hand-editing JSON by using `autoharness show-workspace` and `autoharness set-workspace`. The campaign policy surface now covers default stage, generator, strategy, beam width, beam-group limit, intervention-class cycle, retry budgets, stop budgets, and auto-promotion switches. `show-workspace` and `show-track` both render the effective inherited campaign policy together with per-field source labels, so it is visible when a campaign setting is coming from the track override, the workspace default, or the built-in fallback. `autoharness archive-workspace` marks the workspace as archived without deleting history, and `autoharness purge-workspace` permanently removes an archived workspace after an explicit confirmation check.

For aggregate operator inspection across the full workspace, `autoharness show-workspace-summary` reads the on-disk track, registry, promotion, champion, and iteration state and reports workspace-wide counts plus per-track rollups, including how many recorded runs came from saved plans. The summary payload now also includes the active track’s effective campaign search defaults plus a compact per-track campaign-default snapshot, so workspace-level inspection can show inherited generator, strategy, beam-width, beam-group, and retry-budget choices without jumping to `show-workspace` or `show-track`. One level higher, `autoharness show-root-summary` aggregates those same counts across selected workspaces under `--root`, and it also surfaces the effective active-track campaign-default mix across those workspaces, including retry-budget defaults such as `max_generation_timeout_retries`, `max_generation_provider_retries`, `max_generation_process_retries`, and `max_benchmark_command_retries`. When you want those views as stable artifacts instead of ad hoc JSON, `autoharness export-workspace-summary --output summary.yaml|json` and `autoharness export-root-summary --output summary.yaml|json` write versioned export envelopes with `format_version`, `exported_at`, and the rendered summary payload, and `autoharness show-report-file summary.yaml` / `autoharness validate-report-file summary.yaml` can reopen or validate those exported summary artifacts later without live workspace state. For a larger handoff artifact, `autoharness export-workspace-report --output report.yaml|json` bundles the workspace view, workspace summary, track listing, and per-track summaries plus effective track-policy rollups in one export, and `autoharness export-root-report --output report.yaml|json` does the same one level higher by packaging the root summary together with nested per-workspace reports. The same `show-report-file` / `validate-report-file` commands reopen or validate those single-file report artifacts directly. When you need a portable directory bundle instead of a single report file, `autoharness export-root-bundle --output bundle_dir` writes the root report plus nested workspace bundles under `workspaces/<workspace_id>/`, and those nested workspace bundles can in turn carry listings, track reports, and champion bundles. `autoharness export-workspace-bundle --output bundle_dir` writes the workspace report, full iteration/record/promotion listing exports, per-track reports, and champion bundles for tracks that currently have champions. Both root and workspace bundle exports accept the same skip controls for the nested workspace content: `--skip-listings`, `--skip-track-reports`, and `--skip-champions`. `autoharness show-bundle bundle_dir` reopens the saved bundle manifest later to report which artifacts are present or missing, `autoharness validate-bundle bundle_dir` makes that check scriptable by returning success only when the referenced bundle artifacts are present, `autoharness reindex-bundle bundle_dir` rewrites the manifest to match the artifacts currently present in the directory, and `autoharness import-bundle bundle_dir --output imported_dir` copies the saved bundle into a new directory and validates it after import. Add `--reindex` when the copied destination should restamp its manifest to match the imported files rather than preserve the source manifest as-is. Add `--format json|yaml` when the saved bundle manifest itself should be rewritten in place to a canonical structured format. Add `--recursive` when validation, reindexing, or import should also traverse nested workspace bundles or champion bundles; on import, that same flag also drives nested source preflight and nested destination validation. Add `--target-format json|yaml` when the imported bundle manifest should be normalized to one structured format. Add `--verify-source` when import should stop before copying if the source manifest is already invalid. Add `--allow-invalid` when you want that source preflight result but still need the invalid bundle copied anyway. Add `--dry-run` when you want the import, reindex, and validation decision without writing the destination bundle yet.
For champion-focused auditing across workspaces, `autoharness show-root-champions --root <workspaces>` lists every current champion manifest across the selected workspaces and tracks, together with adapter, benchmark, stage, and transfer provenance when a champion was imported from another workspace. `autoharness export-root-champion-report --output report.yaml|json` materializes that same view as `format_version: autoharness.root_champion_report.v1`, and `show-report-file` / `validate-report-file` reopen or validate that report artifact the same way they do for the other root/workspace summary and report exports.

Multi-track workspaces can now be managed without hand-editing JSON. `autoharness show-tracks` lists all tracks, their lifecycle status, and their policy file locations, `autoharness create-track` scaffolds a new `campaign.json` plus fresh `promotion_policy.json` and `track_policy.json` files for a new track, `autoharness archive-track` retires a track without deleting its history, `autoharness purge-track` permanently removes one archived track and its recorded history after an explicit confirmation check, and `autoharness switch-track` moves the active track pointer in both `workspace.json` and `state.json`.

For per-track inspection, `autoharness show-track-summary` reads the real registry, promotion, and champion files on disk and reports record counts, stage/status breakdowns, saved-plan run counts, the latest record, the latest promotion, the active champion, and the track’s effective campaign search defaults for inherited generator/strategy/beam settings. `autoharness export-track-summary --output summary.yaml|json` writes the same view as a versioned export envelope for handoff or archival, and `autoharness show-report-file summary.yaml` / `autoharness validate-report-file summary.yaml` can reopen or validate that exported summary artifact directly. When you need the surrounding context too, `autoharness export-track-report --output report.yaml|json` bundles the track config, track summary, effective benchmark policy, promotion policy, and concrete artifact paths for that track, and the same report-file commands reopen or validate that single-file track report later. When you need a portable directory instead of a single report file, `autoharness export-track-bundle --output bundle_dir` writes the track report, track-scoped iteration/record/promotion listing exports, and the champion bundle when that track currently has one. `export-track-bundle` also accepts `--skip-listings` and `--skip-champion` for smaller track handoff bundles, `autoharness show-bundle bundle_dir` inspects the saved manifest later without resolving live workspace state, `autoharness validate-bundle bundle_dir` returns a failing exit code when required bundle artifacts have gone missing, `autoharness reindex-bundle bundle_dir` rewrites the manifest so the saved bundle metadata matches the files that are still present, and `autoharness import-bundle bundle_dir --output imported_dir` relocates the saved track or champion bundle into a new directory and validates it after copying. Add `--reindex` when import should repair the destination manifest to match the copied artifact set. Add `--format json|yaml` when the saved bundle manifest itself should be normalized in place. Add `--recursive` when validation, reindexing, or import should also traverse the embedded champion bundle under `champion/`; on import, that also enables nested source preflight and nested destination validation. Add `--target-format json|yaml` when the imported manifest should be rewritten into one canonical structured format. Add `--verify-source` when import should fail before copying if the source bundle manifest is already stale. Add `--allow-invalid` when you need to preserve that preflight result but still copy the invalid source bundle for later inspection. Add `--dry-run` when you want the predicted destination manifest path and validation result without writing the imported bundle yet.

For direct artifact inspection, `autoharness show-records` lists benchmark records across the workspace or one track with the same practical filters used by iteration inspection, including stage, status, benchmark, adapter, hypothesis text, notes text, creation-time window, sort order, and `--saved-plan-only`; `autoharness export-records --output report.yaml|json` writes that same filtered record slice as a structured artifact with `format_version` and `exported_at`; `autoharness show-record` loads one benchmark record from the track registry; `autoharness show-promotions` lists promotions across the workspace or one track with promotion-native filters such as record id, iteration id, target-root text, notes text, creation-time window, sort order, and `--parsed-artifact-sources-only`; `autoharness export-promotions --output report.yaml|json` writes that same filtered promotion slice as a structured artifact with `format_version` and `exported_at`; `autoharness show-promotion` loads one promotion record plus its resolved patch and provenance sidecar paths when they exist; `autoharness show-listing-file <path>` / `autoharness validate-listing-file <path>` reopen or validate exported iteration, record, promotion, and proposal listing files directly; and `autoharness show-artifact-file <path>` / `autoharness validate-artifact-file <path>` provide one auto-detecting entrypoint across saved plans, listing exports, workspace/track report exports, and campaign report exports.

For proposal-first workflows, `autoharness list-generators` shows the built-in generator catalog and `autoharness show-generator --generator <id>` shows one generator’s operator-facing metadata such as whether it can synthesize without `--edit-plan`, which `--generator-option` keys it understands, and which environment variables it depends on. `autoharness generate-proposal` composes the stage-ready config, previews one edit plan against a target harness root under the workspace autonomy policy, records the planned adapter invocation, and persists the result under `tracks/<track>/proposals/<proposal_id>/` without running the benchmark. The default `manual` generator still treats `--edit-plan` as the proposal source, but generators can now synthesize edit plans directly as well. The built-in `failure_summary` generator uses the latest record status, stage evaluation, failure summary, regression summary, parsed artifact provenance, and an optional `--intervention-class prompt|config|middleware|source` hint to generate one deterministic proposal without an input plan file. The built-in `local_template` generator renders one local YAML or JSON template file into a concrete edit plan by filling placeholders such as `{workspace_id}`, `{stage}`, `{candidate_index}`, `{intervention_class}`, and the focused failure/regression labels from the current generation request; pass the template with `--edit-plan` or `--generator-option template_path=path/to/template.yaml`. The built-in `local_command` generator invokes one local executable, sends it the current `request` plus full proposal-generation `context` as JSON on stdin, and expects one JSON proposal object on stdout; pass it with `--generator-option command_path=/path/to/script` and optional overrides such as `--generator-option timeout_seconds=30` or `--generator-option command_cwd=/path/to/cwd`. When the request does not pin explicit `failure_focus_task_ids` or `regressed_task_ids`, proposal generation now derives them from the latest failure/regression context so deterministic generators focus one concrete slice instead of the entire failing set. Campaign-driven proposal generation now persists those selected focus task ids into the candidate’s saved `generation_request`, so retries and resumed campaigns keep operating on the same failure slice instead of silently drifting to whatever the latest workspace state happens to be later. The built-in `openai_responses` generator uses the OpenAI Responses API plus a local target-root snapshot to synthesize one edit plan from current workspace, track, benchmark, and failure context; it reads its provider settings from `OPENAI_API_KEY` or `AUTOHARNESS_OPENAI_API_KEY`, with optional overrides such as `AUTOHARNESS_OPENAI_MODEL`, `AUTOHARNESS_OPENAI_REASONING_EFFORT`, `AUTOHARNESS_OPENAI_TIMEOUT_SECONDS`, and `AUTOHARNESS_OPENAI_BASE_URL`, and the same settings can be overridden per call with repeatable `--generator-option key=value`. Each saved proposal keeps a `proposal.json` manifest plus `edit_plan.json`, `preview_application.json`, `effective_config.json`, and `candidate.patch` when the preview diff is non-empty. `autoharness show-proposal` loads one saved proposal and resolves those sidecars directly, `autoharness show-proposals` lists proposals across the workspace or one track with practical filters for stage, adapter, hypothesis text, notes text, creation-time window, sort order, and limit, and `autoharness export-proposals --output report.yaml|json` writes that filtered proposal slice as a structured artifact with `format_version` and `exported_at`; `autoharness show-listing-file proposals.yaml` / `autoharness validate-listing-file proposals.yaml` reopen or validate that exported proposal listing later. When you want to materialize a saved proposal onto a harness root, `autoharness apply-proposal` loads the saved edit plan, applies it under the current workspace autonomy policy, and keeps the edits in place. When you want to execute a saved proposal end to end, `autoharness run-proposal` reuses the proposal’s persisted `effective_config.json` and `edit_plan.json`, routes through the existing `run-iteration` flow, and stamps the resulting record and iteration summary with `source_proposal_id` and `source_proposal_path`.

For a resumable outer loop, `autoharness run-campaign` can still execute a repeatable `--edit-plan` list, but it can also run in generator-driven mode with no input plans when the selected generator can synthesize candidates itself. Campaign state now persists the explicit `strategy` id, `beam_width`, `beam_group_limit`, `candidate_source_mode`, intervention-class cycle, generator metadata, stage progression mode, richer counters, retry budgets, per-candidate retry accounting, and a durable `decision_log` under `tracks/<track>/campaign_runs/`. The built-in generator loop uses `greedy_failure_focus` as its default strategy when there is no manual edit-plan queue. `round_robin_interventions` rotates across intervention classes and focused failure slices, `regression_first` pushes the generator toward regression recovery before new failure cleanup when regression evidence exists, `alternate_failure_regression` alternates candidate focus between the failure and regression sets instead of staying in one bucket, and `beam_interventions` pre-sources one beam group of candidates against the same focused failure slice while rotating intervention classes across the beam slots. Once one beam candidate succeeds or is promoted, autoharness now prunes the still-pending siblings in that same beam group instead of continuing to spend budget on parallel variants against an already-improved slice. `--beam-groups <n>` now lets beam-style campaigns keep multiple beam groups active at once, and the scheduler ranks the next pending candidate across those groups by current group evidence instead of blindly following raw candidate index order. `run-campaign` now resolves campaign defaults from the selected track override first, then the workspace `campaign_policy`, and only then the built-in defaults for fields such as `stage`, `stage_progression_mode`, `generator`, `strategy`, `beam_width`, `beam_group_limit`, intervention-class cycle, generator metadata, retry budgets, stop budgets, and auto-promotion switches. `--generator-option key=value` passes provider-specific generator metadata directly into proposal generation, while `--max-proposals <n>` still bounds one invocation before it pauses. `--beam-width <n>` controls how many pending candidates one beam-style sourcing step expands at once; when you choose `beam_interventions` without setting it explicitly, autoharness defaults the beam width to the number of selected intervention classes, or `2` when no class cycle is pinned. `--beam-groups <n>` follows the same policy path; if you do not set it at launch, autoharness uses the track override first, then the workspace default, and finally falls back to `1` for beam strategies. `--stage-progression fixed|advance_on_success|advance_on_promotion` lets one campaign stay pinned to its initial stage or climb the screening -> validation -> holdout -> transfer ladder automatically as candidates succeed or get promoted, and the effective current stage is persisted in the campaign record for resume. `--max-iterations <n>`, `--max-successes <n>`, `--max-promotions <n>`, `--max-failures <n>`, `--max-inconclusive <n>`, `--no-improvement-limit <n>`, and `--time-budget-seconds <n>` add campaign-wide stop conditions. `--max-generation-retries <n>`, `--max-generation-timeout-retries <n>`, `--max-generation-provider-retries <n>`, `--max-generation-provider-transport-retries <n>`, `--max-generation-provider-auth-retries <n>`, `--max-generation-provider-rate-limit-retries <n>`, `--max-generation-process-retries <n>`, `--max-execution-retries <n>`, `--max-benchmark-timeout-retries <n>`, `--max-benchmark-command-retries <n>`, and `--max-inconclusive-retries <n>` now let one candidate retry deterministic generation failures, transient generator/provider timeouts, generic provider failures, provider transport failures, provider auth failures, provider rate-limit failures, local generator-process failures, execution failures, benchmark timeouts, transient benchmark-command failures, or inconclusive outcomes before it is finalized, and the campaign decision log now records when a retry budget is exhausted rather than silently falling through to terminal failure. The timeout, provider, provider-transport, provider-auth, provider-rate-limit, process, and benchmark-timeout budgets are separate from the generic generation budget, so operators can treat transient infrastructure failures differently from repeated semantic generator failures, broken credentials, and slow benchmark executions. `--preflight-check python_compile|pytest_collect|pytest_quick` now expands cheap built-in validation commands on top of the existing repeatable `--preflight-command` surface, so campaigns, proposal-backed runs, direct iterations, and direct benchmark runs can gate on syntax or fast test collection before they spend benchmark budget. `--auto-promote` promotes winners automatically through the existing champion comparison flow, `--auto-promote-min-stage screening|validation|holdout|transfer` keeps those promotions from firing before the campaign reaches the stricter stage you want, and `--stop-on-first-promotion` terminates the run as soon as one candidate becomes champion. `autoharness run-workspace-campaigns` applies the same launch surface across every selected active track in one workspace, derives per-track target roots as `<target-root-base>/<track_id>`, returns one aggregated batch payload so you can fan out search across tracks without reassembling the same CLI call repeatedly, and now includes aggregate search-policy mix counts plus aggregate resource-usage totals for the campaigns it actually launched, including stage progression, retry budgets, and auto-promotion behavior. When you want that launched batch result as a stable artifact instead of transient `--json` output, `autoharness export-workspace-campaign-run-report --output report.yaml|json` runs the same workspace fan-out and writes the returned batch payload under `format_version: autoharness.workspace_campaign_run_report.v1` with `exported_at`. `autoharness run-root-campaigns` takes the same launch surface one level higher by scanning every selected workspace under `--root`, then running one workspace campaign fan-out per workspace with target roots under `<target-root-base>/<workspace_id>/<track_id>`; its batch result now includes the same aggregate search-policy mix counts and aggregate resource-usage totals across every launched workspace/track campaign. `autoharness export-root-campaign-run-report --output report.yaml|json` does the same for that root-wide orchestration result under `format_version: autoharness.root_campaign_run_report.v1`. `autoharness show-root-campaigns` lists the persisted campaign runs across all selected workspaces under the same root, and `autoharness export-root-campaign-report --output report.yaml|json` materializes that persisted root-wide view as one versioned artifact with aggregate counts, aggregate resource-usage totals, aggregate search-policy mix counts by generator/strategy/source mode/beam settings plus retry-budget, stage progression, and auto-promotion behavior, and per-campaign details. At the workspace level, `autoharness show-campaigns` now carries the same aggregate counts, aggregate resource-usage totals, and search-policy mix snapshot for the selected workspace or track, and `autoharness export-workspace-campaign-report --output report.yaml|json` materializes that persisted workspace-scoped campaign view as `format_version: autoharness.workspace_campaign_report.v1`. `autoharness show-campaign-report-file <path>` reopens any exported campaign report file in the current campaign family, including single-campaign, workspace, root, and batch-run report exports, and `autoharness validate-campaign-report-file <path>` checks that the required report envelope and payload fields are present for that report type; `autoharness show-artifact-file <path>` / `autoharness validate-artifact-file <path>` can auto-detect those campaign report files too. When you want those persisted campaign views as portable directories instead of one report file, `autoharness export-workspace-campaign-bundle --output bundle_dir` writes the workspace campaign report plus one nested campaign bundle per persisted campaign under that workspace, and `autoharness export-root-campaign-bundle --output bundle_dir` writes the root campaign report plus one nested workspace campaign bundle per selected workspace. Those workspace/root campaign bundles are also first-class bundle types for `show-bundle`, `validate-bundle`, `reindex-bundle`, and `import-bundle`, and `--recursive` now traverses their nested campaign bundles and any champion bundles nested inside those campaign exports. `autoharness resume-campaign --campaign-id <id>` continues a paused run from its saved `next_candidate_index`, `autoharness show-campaign` loads one persisted campaign record, and `autoharness show-campaigns` lists the saved campaign runs across a workspace or one track, including strategy, beam width, beam-group limit, source mode, success, failure, inconclusive, promotion, and pruned-candidate counts. When you want the concrete linked files instead of just state, `autoharness show-campaign-artifacts` resolves the campaign file plus the linked proposal, record, iteration, promotion, and champion artifact paths. When you need a portable structured report, `autoharness export-campaign-report --output report.yaml|json` writes the campaign state alongside the linked proposal manifests, benchmark records, iteration summaries, promotion records, and any current champion manifest as a versioned artifact. When you want the same lineage as a directory handoff instead of one report file, `autoharness export-campaign-bundle --output bundle_dir` writes the campaign payload, campaign report, copied proposal directories, copied record files, copied iteration bundles, copied promotion artifacts, and the champion bundle when the track currently has one. Campaign bundles are also first-class bundle types for `show-bundle`, `validate-bundle`, `reindex-bundle`, and `import-bundle`, including recursive champion-bundle handling.

For track-level file inspection, `autoharness show-track-artifacts` lists the concrete campaign, policy, registry, promotion, and champion files for a track, including resolved sidecar patch and provenance paths for promotions and champions when present.

For iteration-level inspection, `autoharness show-iteration` loads one iteration artifact bundle directly from `iterations/<iteration_id>/`, and `autoharness show-iterations` lists the available iteration summaries for a workspace along with the current `last_iteration_id`, saved-plan replay counts, and per-iteration saved-plan provenance fields such as `source_plan_path` and any copied `source_plan.json` artifact path. When you need that same filtered slice as a portable artifact, `autoharness export-iterations --output report.yaml|json` writes a structured export with the same listing payload plus `format_version` and `exported_at`, and `autoharness show-listing-file iterations.yaml` / `autoharness validate-listing-file iterations.yaml` can reopen or validate that exported listing later. When you only want one track, `show-iterations --track-id <track>` scopes the listing to that track, `show-iterations --stage <screening|validation|holdout|transfer>` narrows it to one evaluation stage, `show-iterations --status <success|failed|inconclusive|dry_run>` narrows it to one run outcome, `show-iterations --benchmark-name <name>` narrows it to one benchmark target, `show-iterations --adapter-id <id>` narrows it to one adapter, `show-iterations --hypothesis-contains <text>` narrows it to hypothesis labels containing a case-insensitive substring, `show-iterations --notes-contains <text>` does the same for operator notes, `show-iterations --since/--until <YYYY-MM-DD|ISO-8601>` narrows it to one creation-time window, `show-iterations --sort-by <iteration_id|created_at>` switches between lexical and timestamp ordering, `--descending` reverses that order, and `show-iterations --saved-plan-only` further limits the visible entries to saved-plan-backed iterations; `export-iterations` accepts that same filter surface.
