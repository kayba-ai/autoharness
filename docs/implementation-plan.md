# Full Implementation Plan

Date: 2026-04-23

This document captures the remaining work for `autoharness` after the current control-plane, proposal, campaign, reporting, and bundle layers already in the repo.

It is intentionally biased toward concrete execution, not product copy.

## 1. Current Baseline

The repo already has:

- workspace, track, policy, promotion, and champion state
- benchmark adapters and repeated validation
- proposal artifacts, application, and proposal-backed runs
- generator catalog and multiple generator backends
- resumable campaigns with strategy, beam, retry, and budget controls
- workspace/root fan-out and reporting
- report, bundle, import, validate, and reindex surfaces
- named preflight checks and policy-aware preflight wiring
- token/cost/resource usage aggregation in campaign reporting
- generation-side failure taxonomy split across timeout, provider, transport, auth, rate-limit, and process failures
- benchmark-side timeout split from benchmark-command failure

The remaining work is no longer basic plumbing. The gaps are in optimizer quality, benchmark/runtime hardening, execution isolation, orchestration depth, and operational governance.

## 2. Remaining Gaps

### 2.1 Benchmark Runtime Taxonomy Is Still Too Coarse

Current state:

- `benchmark_timeout`
- `benchmark_command_failed`
- `benchmark_failed`
- `stage_gate_failed`
- `benchmark_regression`
- `benchmark_inconclusive`

Still missing:

- benchmark process error vs semantic benchmark failure
- signal termination / killed process classification
- artifact parse failure classification
- metrics parse failure vs task-results parse failure
- adapter validation/config failure classification separated from runtime failure
- retry budgets and policy mix reporting for the new benchmark buckets

### 2.2 Cheap Preflight Coverage Is Still Thin

Current state:

- `python_compile`
- `pytest_collect`
- `pytest_quick`

Still missing:

- `pytest_smoke`
- `ruff_check`
- `mypy_quick`
- package/build smoke checks
- stage-specific default preflight stacks
- adapter-specific recommended preflight defaults
- optional preflight caching / dedup for repeated candidates

### 2.3 Generator Quality Is Still Minimal

Current state:

- `manual`
- `failure_summary`
- `local_template`
- `local_command`
- `openai_responses`

Still missing:

- critique-and-repair generation loop
- invalid-response repair pass for provider outputs
- provider fallback chain instead of single-generator failure
- intervention-class-specific prompt templates
- benchmark/language-aware proposal scaffolds
- multi-generator routing by task type
- stronger request/response capture for deterministic replay

### 2.4 Search Is Still Heuristic, Not Strongly Adaptive

Current state:

- greedy failure focus
- regression-first
- alternating failure/regression
- beam interventions
- beam-group pruning

Still missing:

- explicit branch scoring model
- exploration vs exploitation tuning
- diversity / novelty scoring
- history-aware ranking across campaigns
- multi-objective ranking beyond “did it pass”
- better branch reuse after partial wins

### 2.5 Statistical Robustness Is Not Driving Decisions Yet

Current state:

- repeated validation
- confidence intervals
- stability summaries
- flake signal present in payloads

Still missing:

- campaign logic that reacts to instability automatically
- automatic rerun policy for noisy candidates
- stability-gated promotion
- margin + stability combined decision rules
- revalidation-after-promotion policy
- demotion or rollback markers after later regressions

### 2.6 Execution Isolation Is Functional but Not Strong Enough

Current state:

- staging
- edit transaction rollback by default
- bounded/full/proposal autonomy enforcement

Still missing:

- stronger per-candidate isolated work roots
- execution snapshots that are validated before and after runs
- file-level drift detection after failed runs
- stronger separation between generator runtime and benchmark runtime
- reproducibility manifests for run environment

### 2.7 Orchestration Is Still Foreground CLI Driven

Current state:

- resumable campaigns
- workspace/root fan-out from the CLI

Still missing:

- local worker pool
- background queue/daemon mode
- cancel / pause / resume with worker coordination
- claim/lease semantics for concurrent runners
- recovery for interrupted workers
- priority scheduling

### 2.8 Cross-Workspace Optimization Is Still Shallow

Current state:

- root-level reporting
- root-level campaign fan-out
- root bundles and root reports

Still missing:

- cross-workspace champion transfer
- root-level shared intervention memory
- workspace-to-workspace promotion suggestions
- portfolio scheduling across workspaces
- reusable winning-pattern memory across tracks/workspaces

### 2.9 Resource Governance Is Incomplete

Current state:

- generation token budgets
- benchmark cost budgets
- runtime budgets
- retry budgets
- aggregated usage reporting

Still missing:

- CPU / memory / disk budgets
- per-provider spend caps
- rate control / concurrency budgets
- wall-clock attribution by generator/provider/stage in detail views
- artifact storage quota enforcement

### 2.10 Observability Is Mostly Static

Current state:

- reports
- listing exports
- bundles
- campaign decision logs

Still missing:

- live event stream
- append-only operational event logs
- structured timeseries metrics export
- searchable campaign trace view
- root/workspace dashboard surfaces

### 2.11 Artifact Lifecycle Management Is Missing

Current state:

- export/import/validate/reindex is strong

Still missing:

- retention policy
- pruning/garbage collection
- archive tiers for old campaigns
- deduplication of copied artifact payloads
- quota-aware cleanup

### 2.12 Security and Extensibility Need Another Pass

Current state:

- autonomy modes
- provider env var support

Still missing:

- secret redaction in exported artifacts
- provider credential scoping by workspace/track
- audit markers for secret-dependent runs
- stable plugin contract for generators/search policies/preflight checks

## 3. Guiding Constraints

Whether work lands as small commits or one rolling branch, the roadmap below must preserve these invariants:

1. Full test suite stays green after each slice.
2. New taxonomy or policy fields must flow through:
   - CLI parsing
   - mutation/default resolution
   - persisted state
   - inspection/reporting
   - export/import/validation where relevant
3. Resume/replay behavior must remain deterministic wherever the code already promises it.
4. No new feature should bypass autonomy policy or staging rules.

These invariants are hard gates, not approval pauses. Work should continue automatically from one phase to the next unless a gate fails or a later phase depends on machinery that does not exist yet.

## 4. Roadmap

## Phase 1: Finish Benchmark Runtime Hardening

### Goal

Make benchmark-side failures as explicit and policy-addressable as generation-side failures.

### Deliverables

1. Split benchmark failures into:
   - `benchmark_timeout` (done)
   - `benchmark_process_error`
   - `benchmark_signal_error`
   - `benchmark_metrics_parse_error`
   - `benchmark_task_results_parse_error`
   - `benchmark_adapter_validation_error`
   - keep `benchmark_command_failed` as the generic non-timeout command failure bucket

2. Persist and report retry budgets for:
   - process failures
   - signal failures
   - parse failures
   - adapter validation failures where retry is allowed

3. Thread new buckets into:
   - campaign scheduling
   - policy mix summaries
   - root/workspace summary inspection
   - search severity weighting

### Primary files

- `src/autoharness/adapters/base.py`
- `src/autoharness/validation.py`
- `src/autoharness/campaign_handlers.py`
- `src/autoharness/campaign_runs.py`
- `src/autoharness/mutations.py`
- `src/autoharness/inspection_handlers.py`
- `src/autoharness/search.py`

### Acceptance criteria

- timeout/process/parse failures are distinguishable in persisted campaign state
- retry policy can target benchmark timeouts separately from generic command failures
- root/workspace/campaign reports include the new mix buckets
- tests cover real timeout and real parse-failure flows

## Phase 2: Expand Cheap Preflight Validation

### Goal

Reject low-quality candidates before benchmark spend.

### Deliverables

1. Add built-in checks:
   - `pytest_smoke`
   - `ruff_check`
   - `mypy_quick`
   - `python_import_smoke`
   - `package_build`

2. Add policy support for:
   - stage-specific default preflight stacks
   - adapter-scoped recommended preflight checks
   - optional preflight cache keying on target-root + changed files

3. Extend inspection:
   - effective preflight stack by stage
   - root/workspace mix for named checks, not just counts

### Primary files

- `src/autoharness/preflight.py`
- `src/autoharness/execution_handlers.py`
- `src/autoharness/proposal_handlers.py`
- `src/autoharness/campaign_handlers.py`
- `src/autoharness/mutations.py`
- `src/autoharness/inspection_handlers.py`

### Acceptance criteria

- campaigns can inherit stage-specific check stacks from policy
- repeated candidates can reuse preflight results when inputs are unchanged
- preflight failures show up as first-class decision-log events

## Phase 3: Improve Generator Quality and Reliability

### Goal

Make proposal generation more robust without breaking deterministic auditability.

### Deliverables

1. Add a critique-and-repair loop:
   - first-pass proposal
   - schema repair / edit-plan repair pass
   - optional second-pass minimal fix when apply/validation fails

2. Add generator fallback policy:
   - configurable ordered fallback list
   - fallback logging in proposal metadata and campaign decision log

3. Add intervention-aware prompt templates:
   - prompt/config/middleware/source variants

4. Add benchmark/language-aware context shaping:
   - prioritize files and examples by adapter, benchmark, and intervention class

5. Strengthen request/response capture:
   - frozen provider request payload
   - frozen raw response payload
   - redacted export mode

### Primary files

- `src/autoharness/generators/base.py`
- `src/autoharness/generators/openai_responses_generator.py`
- `src/autoharness/generators/local_command_generator.py`
- `src/autoharness/proposal_context.py`
- `src/autoharness/proposal_handlers.py`
- `src/autoharness/proposals.py`

### Acceptance criteria

- invalid provider output can be repaired without losing provenance
- fallback paths are explicit in artifact metadata
- replay can show the exact provider request that produced a proposal

## Phase 4: Strengthen Search and Branch Scoring

### Goal

Make campaign search less naive than current heuristic scheduling.

### Deliverables

1. Introduce branch scoring inputs:
   - stage reached
   - regression delta
   - failure-slice novelty
   - intervention diversity
   - stability / flake penalty
   - cost spent vs improvement

2. Add new strategies:
   - `beam_scored`
   - `diversity_first`
   - `stability_weighted`
   - `explore_then_exploit`

3. Persist branch score snapshots in campaign state.

4. Surface branch score rationale in:
   - `show-campaign`
   - campaign reports
   - root/workspace campaign listings

### Primary files

- `src/autoharness/search.py`
- `src/autoharness/campaign_handlers.py`
- `src/autoharness/campaign_runs.py`

### Acceptance criteria

- candidate ordering is explainable from persisted score/rationale data
- beam scheduling uses scoring across groups, not only simple severity/position
- tests prove deterministic scheduling from the same saved state

## Phase 5: Make Statistical Robustness Drive Decisions

### Goal

Stop treating unstable wins as equal to stable wins.

### Deliverables

1. Add policy fields for:
   - rerun-on-flake threshold
   - minimum stability for promotion
   - required revalidation runs after provisional win

2. Add campaign behavior:
   - automatic rerun for unstable success
   - promotion blocking on instability
   - explicit “provisional winner” status

3. Add follow-up commands or flags for revalidation:
   - likely as campaign policy, not separate manual CLI first

### Primary files

- `src/autoharness/validation.py`
- `src/autoharness/campaign_handlers.py`
- `src/autoharness/mutations.py`
- `src/autoharness/inspection_handlers.py`

### Acceptance criteria

- flake signal can change campaign decisions
- unstable candidates do not promote unless policy allows it
- reports explain whether a win was stable or provisional

## Phase 6: Harden Execution Isolation and Reproducibility

### Goal

Reduce ambiguity about what changed during a candidate run.

### Deliverables

1. Strengthen staging manifests:
   - staged file inventory
   - changed file inventory before/after run
   - drift detection after failed runs

2. Add run environment capture:
   - Python version
   - selected env var whitelist
   - working directory manifest

3. Add stronger cleanup validation:
   - verify rollback restored target root when keep=false

### Primary files

- `src/autoharness/staging.py`
- `src/autoharness/editing.py`
- `src/autoharness/execution_handlers.py`
- `src/autoharness/proposal_handlers.py`
- `src/autoharness/campaign_handlers.py`

### Acceptance criteria

- failed runs cannot silently leave unknown file drift behind
- reports can show whether a candidate ran in a clean isolated root

## Phase 7: Add Background and Parallel Orchestration

### Goal

Move beyond single foreground CLI execution.

### Deliverables

1. Local worker pool:
   - configurable `--workers`
   - parallel candidate execution where safe

2. Background runner mode:
   - queue-backed worker loop
   - pause/cancel/claim semantics

3. Persist worker/lease state:
   - who owns a campaign
   - stale lease recovery

### Primary files

- `src/autoharness/campaign_handlers.py`
- new worker/scheduler module
- `src/autoharness/campaign_runs.py`

### Acceptance criteria

- multiple campaigns can run concurrently without corrupting state
- interrupted workers can be recovered safely

## Phase 8: Deepen Cross-Workspace Optimization

### Goal

Make root-level orchestration do more than just fan out and report.

### Deliverables

1. Cross-workspace champion transfer suggestions
2. Shared intervention memory across workspaces
3. Root-level portfolio scheduling heuristics
4. Optional import/promotion automation from one workspace to another

### Primary files

- `src/autoharness/campaign_handlers.py`
- `src/autoharness/inspection_handlers.py`
- `src/autoharness/promotion_handlers.py`
- new root-memory/query module

### Acceptance criteria

- root orchestration can recommend or automate transfers based on proven wins
- provenance remains explicit across workspace boundaries

## Phase 9: Add Operational Observability

### Goal

Make long-running optimization inspectable without opening static files manually.

### Deliverables

1. Append-only event logs for:
   - campaign lifecycle
   - generator calls
   - benchmark runs
   - promotion events

2. Live or tail-able event inspection:
   - `show-event-log`
   - `tail-campaign-events`

3. Metrics export:
   - per-generator/provider counts
   - token/cost totals by workspace/track/campaign
   - retry counts by bucket

### Primary files

- new events module
- `src/autoharness/campaign_handlers.py`
- `src/autoharness/inspection_handlers.py`

### Acceptance criteria

- operators can inspect live progress without reading raw JSON artifacts
- event logs are exportable and bundle-safe

## Phase 10: Add Artifact Lifecycle Management

### Goal

Keep long-running repositories from accumulating unbounded artifact weight.

### Deliverables

1. Retention policies:
   - keep latest N campaigns
   - keep champions forever
   - prune failed candidate patches older than threshold

2. Commands:
   - `show-retention-policy`
   - `set-retention-policy`
   - `prune-artifacts`

3. Bundle/export coordination:
   - prevent pruning referenced active artifacts

### Primary files

- `src/autoharness/tracking.py`
- `src/autoharness/inspection_handlers.py`
- new retention module

### Acceptance criteria

- artifact cleanup is policy-driven and non-destructive to active lineage

## Phase 11: Improve Security and Extensibility

### Goal

Make the system safer to operate and easier to extend without patching core files.

### Deliverables

1. Secret redaction rules in exports/bundles/reports
2. Workspace/track-scoped provider profiles
3. Stable plugin contract for:
   - generators
   - search strategies
   - preflight checks

### Primary files

- `src/autoharness/outputs.py`
- `src/autoharness/inspection_handlers.py`
- generator registry modules
- new plugin registry module

### Acceptance criteria

- exported artifacts cannot leak known secret-bearing fields by default
- external extensions can register into the CLI/runtime without modifying core registries

## 5. Implementation Order

Recommended execution order:

1. Phase 1: benchmark runtime hardening
2. Phase 2: preflight expansion
3. Phase 3: generator quality
4. Phase 4: search and branch scoring
5. Phase 5: statistical robustness
6. Phase 6: isolation and reproducibility
7. Phase 7: background/parallel orchestration
8. Phase 8: cross-workspace optimization
9. Phase 9: observability
10. Phase 10: artifact lifecycle
11. Phase 11: security/extensibility

The order matters:

- benchmark/runtime taxonomy and preflight expansion make campaign execution safer
- better generation is lower value until runtime hardening is in place
- parallel orchestration should not land before isolation and reproducibility improve
- retention and plugin work should come after the optimizer behavior is more mature

### Continuous Remaining Track

Phases 1 through 6 are complete. The remaining phases, 7 through 11, should now be treated as one uninterrupted final execution band:

1. Do not stop for plan review between Phases 7, 8, 9, 10, and 11.
2. Advance immediately when the current slice's concurrency, persistence, inspection, export, and policy surfaces are wired through and covered by tests.
3. Only pause if one of the guiding constraints fails or if a persisted-format or safety change needs compatibility work before the next schema change lands.

Use these rolling hard gates inside that remaining band:

1. Gate D, before moving from Phase 7 to Phase 8:
   - worker ownership, lease persistence, stale-lease recovery, and concurrency-safe state updates are in place
   - multiple campaigns can run concurrently in tests without corrupting workspace or campaign state
2. Gate E, before moving from Phase 9 to Phase 10:
   - append-only events, live inspection, and metrics export are wired through bundle-safe inspection paths
   - targeted observability and export tests pass
3. Gate F, before closing Phase 11 and marking the roadmap complete:
   - retention, redaction, provider profiles, and plugin registration are wired through CLI, runtime, exports, and reports
   - `python -m compileall src` and `python -m pytest tests` pass

No manual stop is required anywhere inside Phases 7-11. The gates above are technical validation points, not roadmap handoff points.

### Remaining Gap Closure Track

Completed on April 23, 2026. The remaining Phase 7-11 closure slices were executed as one continuous stream and verified without reopening the roadmap mid-flight.

1. Phase 7 closure and concurrency proof: completed
   - multi-worker contention, pooled root execution, stale-lease recovery, and queued-before-paused recovery ordering are covered
   - workspace lease ownership remains the concurrency boundary; same-workspace candidate parallelism was intentionally not introduced
2. Phase 8 root orchestration deepening: completed
   - root memory now captures richer champion traits, generator summaries, regression patterns, transfer context, and portfolio scheduling rationale
3. Phase 9 observability completion: completed
   - generator, benchmark, promotion, transfer, and campaign lifecycle events are emitted end-to-end
   - event metrics now roll up generator/provider/adapter dimensions plus workspace, track, and campaign usage
   - event logs are first-class bundle/report/inspection artifacts
4. Phase 10 reference-aware artifact lifecycle: completed
   - pruning now respects queued/running/paused campaigns, champions, reports, and exported bundle references
   - dry-run output explains keep decisions and retained reference sources
5. Phase 11 contract hardening: completed
   - redacted provider-profile application details are surfaced in reports, inspections, and exports
   - plugins now require API versioning, explicit enablement, schema validation, and load-failure reporting
   - search, preflight, and generator extension points now use stable runtime contribution contracts
6. Final closure sweep: completed
   - docs, reports, inspection commands, export payloads, and verification were synced to the final runtime behavior

Closure outcome:

1. The closure stream ran without roadmap-review stop points between slices.
2. Targeted tests were run inline as each slice landed.
3. Final verification is green with `python -m compileall src` and `python -m pytest tests`.

## 6. Testing Requirements

Every phase must add:

- direct unit tests for new helper logic
- parser/registration tests for any new CLI flags or commands
- focused integration tests for real retry/classification behavior
- bundle/report validation tests when artifacts change

Continuous-execution rule for the remaining phases, 7-11:

- run targeted tests for the subsystem being changed before advancing to the next slice
- run `python -m compileall src` and `python -m pytest tests` at Gate D, Gate E, and Gate F
- keep the branch in a shippable state; a rolling implementation stream is allowed, but broken checkpoints are not

Closure-track rule for the remaining gaps:

- run focused concurrency tests after the Phase 7 closure slice
- run root-memory, scheduling, and transfer tests after the Phase 8 slice
- run event, metrics, bundle, and inspection tests after the Phase 9 slice
- run prune/reference-graph/export tests after the Phase 10 slice
- run plugin/profile/report/export tests after the Phase 11 slice
- run one final `python -m compileall src` and one final `python -m pytest tests` after the entire closure track, without treating the intermediate slice boundaries as stop points

Global rule:

- `python -m compileall src`
- `python -m pytest tests`

must stay green at each hard gate and before the roadmap is declared complete.

## 7. Definition of Done

The remaining roadmap is complete when:

1. benchmark-side failures are classified and policy-controlled as cleanly as generation-side failures
2. campaigns use richer search scoring and stability-aware decisions
3. proposal generation has repair/fallback depth and better context specialization
4. long-running execution can run in background/parallel with explicit leases and recovery
5. root-level orchestration can transfer learning across workspaces, not just fan out
6. operators have event-level observability and artifact lifecycle control
7. exports remain auditable, reproducible, and secret-safe

## 8. Immediate Next Workstream

No open work remains under this roadmap.

1. Treat future changes as net-new follow-on work rather than unfinished Phase 7-11 closure.
2. Preserve the current verification bar: `python -m compileall src` and `python -m pytest tests` must stay green before declaring any follow-on roadmap complete.

The intent is explicit: no manual stop is required anywhere inside this closure stream. The gates above remain validation checks, not roadmap handoff points.
