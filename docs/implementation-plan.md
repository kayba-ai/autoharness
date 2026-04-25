# Core Implementation Plan

Date: 2026-04-24

This is the first implementation pass for `autoharness`.

The goal is simple: turn `autoharness` from a functioning control plane into a reliable optimizer runtime. This pass is intentionally narrower than the previous roadmap. It covers the optimizer core and defers broader orchestration and operational expansion to a second pass.

## Goal

At the end of this pass, `autoharness` should be able to:

- classify runtime failures precisely enough for policy and retry logic
- reject bad candidates cheaply before benchmark spend
- generate stronger proposals and recover from weak provider output
- search and rank candidates with better scoring
- promote candidates using stability-aware rules
- run candidates in stronger isolation with reproducible state

## Scope

### Included

- richer benchmark runtime taxonomy
- broader and policy-aware preflight validation
- stronger candidate isolation and reproducibility
- stronger provider-backed proposal generation
- stronger search and candidate ranking
- stability-aware rerun and promotion logic
- enough inspection and reporting work to keep the system coherent

### Deferred to second pass

- background queue or daemon execution
- worker-pool orchestration and lease semantics
- cross-workspace memory and portfolio scheduling
- broader root-level optimization coordination
- full resource governance
- dashboard-style observability and searchable traces
- full artifact lifecycle management
- broader security and plugin-governance work

## Workstreams

### 1. Runtime, Preflight, and Isolation

This workstream makes the runtime safe enough to trust.

Deliver:

- better benchmark failure buckets:
  - `benchmark_timeout`
  - `benchmark_process_error`
  - `benchmark_signal_error`
  - `benchmark_metrics_parse_error`
  - `benchmark_task_results_parse_error`
  - `benchmark_adapter_validation_error`
  - keep `benchmark_command_failed` for generic non-timeout command failure
- thread those buckets into validation, retry, reporting, and search decisions
- broader built-in preflight checks:
  - `pytest_smoke`
  - `ruff_check`
  - `mypy_quick`
  - `python_import_smoke`
  - `package_build`
- stage-specific and adapter-specific preflight defaults
- optional preflight result caching where inputs are unchanged
- isolated work roots, drift detection, and reproducibility manifests

### 2. Proposal Generation and Search Quality

This workstream makes the optimizer better at finding worthwhile candidates.

Deliver:

- critique-and-repair generation for provider-backed generators
- deterministic repair or retry for invalid provider output
- provider fallback chains
- intervention-aware and benchmark-aware proposal prompts
- stronger request/response capture for replay
- explicit branch scoring
- exploration vs exploitation controls
- diversity and novelty scoring
- history-aware ranking

### 3. Stability-Aware Decisions

This workstream makes campaign decisions defensible under noisy benchmarks.

Deliver:

- rerun policy for noisy candidates
- stability-gated promotion
- decision rules based on both margin and stability
- revalidation after promotion
- demotion or rollback markers after later regressions

## Implementation Order

This is one branch, not a phased release plan, but the dependency order still matters.

1. Land the shared runtime and state foundations:
   benchmark failure taxonomy, retry model, preflight policy model, isolation model, reproducibility manifest schema.
2. Add cheap rejection and runtime safety:
   richer validation payloads, broader preflight coverage, preflight caching, isolated work roots, drift detection.
3. Upgrade proposal generation and search:
   critique-and-repair, fallback chains, benchmark-aware prompting, explicit ranking logic.
4. Add stability-aware decisioning:
   reruns, promotion gating, revalidation, demotion or rollback markers.

## Constraints

- no feature may bypass autonomy policy or staging rules
- persisted state, inspection output, and exports must stay aligned
- replay and resume behavior must remain deterministic where already promised
- benchmark and generation accounting must not become less precise
- new runtime distinctions must appear everywhere users inspect results

## Verification

This pass is not done until the system works end to end.

Add or expand tests for:

- benchmark failure classification
- parse-failure handling
- preflight expansion and caching
- reproducibility manifests
- critique-and-repair generation
- provider fallback selection
- branch scoring and ranking
- stability-aware promotion rules

Cover end-to-end flows for:

- `run-benchmark`
- `generate-proposal`
- `run-iteration`
- `run-campaign`
- `resume-campaign`
- promotion and revalidation
- export/import/reindex/validate where artifacts changed

Acceptance scenarios:

1. A broken candidate is rejected by preflight before benchmark spend.
2. A benchmark parse failure is classified distinctly and retried by policy.
3. A provider response is repaired or retried through fallback without corrupting persisted state.
4. A broad multi-file proposal can be generated, executed, and replayed deterministically.
5. A noisy candidate is rerun or blocked from promotion by stability-aware logic.
6. A failed candidate that mutates files unexpectedly is caught by isolation or drift checks.

## Done

This pass is complete when:

- runtime taxonomy is materially richer and visible in system outputs
- preflight blocks obviously bad candidates cheaply
- proposal generation is stronger, more repairable, and more replayable
- search and promotion logic are stability-aware
- execution isolation and reproducibility are materially better
- inspection and exports remain coherent
- the relevant test suite and end-to-end scenarios pass

## Second Pass

The deferred systems work now lives in [Second Pass Plan](./second-pass-plan.md).

That pass covers:

- background execution and worker coordination
- cross-workspace optimization and portfolio scheduling
- deeper resource governance
- better observability surfaces
- artifact retention, archival, and cleanup
- broader security and extensibility hardening
