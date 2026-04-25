# Second Pass Plan

Date: 2026-04-24

This is the second implementation pass for `autoharness`.

The first pass makes `autoharness` a reliable optimizer runtime. The second pass should add advanced operational capability without turning the repo into an overbuilt platform or making onboarding harder.

## Product Stance

`autoharness` should stay simple by default.

The common path should still feel like:

1. point at one target repo
2. point at one benchmark config
3. run one campaign
4. inspect one result

Advanced operations are still valuable, but they must be additive. A new user should not need to understand worker leases, portfolio scheduling, retention policy, or plugin catalogs before getting a useful result.

## Goal

At the end of this pass, `autoharness` should:

- keep the default single-user workflow small and understandable
- expose advanced operational features only when the user asks for them
- support background execution and multi-workspace coordination for power users
- enforce practical resource and storage policies
- expose enough operational state that long-running use is debuggable
- harden exports and extensions without making the normal path heavy

## Scope

### Core Product Behavior Must Stay Simple

These remain the primary product shape:

- local CLI first
- one workspace at a time as the default mental model
- foreground execution as a first-class path
- clear benchmark -> candidate -> campaign -> champion flow
- minimal required concepts for onboarding

### Second-Pass Features Are Optional Layers

These are in scope, but they must stay optional:

- background queue and worker execution
- root-level memory, transfer, and portfolio scheduling
- resource governance and retention policy controls
- deeper inspection, reporting, and event timelines
- plugin governance and stronger export hardening

### Not the Goal of This Pass

- making the default README or quickstart teach the full control plane
- forcing users to understand roots, tracks, worker leases, or portfolio state early
- adding a large new taxonomy of public concepts when existing ones already work
- building a full service or hosted platform abstraction

## Design Rules

1. Progressive disclosure wins.
   Advanced features may exist, but they should live behind advanced commands and docs.

2. The default path must remain local and obvious.
   If a feature mainly helps long-running or multi-workspace use, it should not dominate the top-level UX.

3. Internal complexity is acceptable only if public complexity stays low.
   The repo may have richer state and control logic than the README exposes.

4. The narrowest useful policy should win.
   When multiple scopes define a limit or rule, the effective behavior should be easy to explain.

5. Every advanced feature needs an inspection surface.
   If a background or governance feature cannot be inspected, it is not ready.

## Workstreams

### 1. Optional Background Operations

Deliver:

- background `run-campaign` execution that remains optional
- worker claim, heartbeat, stale-lease recovery, and interruption recovery
- pause, resume, cancel, and drain behavior with explicit state transitions
- queue inspection at root, workspace, and track scope
- worker-state inspection with retry, lease, and resource rollups

Success means a power user can run campaigns continuously, while a normal user can ignore this layer entirely.

### 2. Optional Root-Level Coordination

Deliver:

- richer root memory for failures, wins, generators, regressions, and transfer candidates
- transfer suggestions based on real historical outcomes
- portfolio scheduling that uses stored evidence without starving smaller workspaces
- root-level inspection that explains why work was prioritized or transferred

Success means cross-workspace optimization is useful and explainable, not magical and not required for basic use.

### 3. Governance and Lifecycle

Deliver:

- enforceable runtime and storage limits
- provider-level and generator-level rate controls where practical
- budget attribution by workspace, track, campaign, generator, and provider
- retention, pruning, and archival behavior with dry-run inspection
- reference-aware cleanup that preserves active and champion-linked artifacts

Success means long-running use is bounded and predictable.

### 4. Observability and Hardening

Deliver:

- stronger event timelines and campaign trace views
- better rollups for queue state, worker state, retries, and resource usage
- redaction that covers reports, bundles, traces, and inspection output
- tighter plugin validation and clearer plugin failure isolation
- better visibility into which external surfaces were active during a run

Success means operators can answer "what is it doing and why?" without reading raw state files.

## Operational Invariants

These invariants should be made explicit in code and tests.

- A background campaign has at most one active campaign lease owner at a time.
- A workspace has at most one active workspace worker lease owner at a time.
- `queued`, `running`, and `paused` are the only background states that remain runnable.
- `paused` with `desired_state=paused` is operator-paused and must not be auto-claimed.
- `paused` with `stop_reason=lease_lost` and `desired_state=run` is recoverable and may be reclaimed.
- `canceled` is terminal and must not be reclaimed.
- Resume, pause, cancel, and recovery actions must preserve persisted campaign history.
- Operator controls may change control state, but must not bypass autonomy or promotion policy.

## Compatibility and Migration

This pass should not assume a clean slate.

- Any new persisted artifact or state file must be versioned.
- Existing files must either remain readable or fail with a precise compatibility error.
- Resume behavior must be deterministic across supported file versions.
- State migrations should be explicit, local, and test-covered.
- Exported reports and bundles should preserve enough version metadata to explain how they were produced.

## Budget Enforcement Semantics

Governance should be simple to explain.

- The effective limit is the most restrictive applicable limit across root, workspace, and campaign scope.
- Hitting a soft limit should stop new work from being scheduled.
- Hitting a hard runtime limit should pause the campaign at the next safe checkpoint.
- Provider rate limits should prefer backoff and retry before terminal failure.
- Storage exhaustion should block new artifact creation or trigger policy-driven cleanup, not silently continue.
- Budget exhaustion and throttling decisions must appear in inspection output and event history.

## Implementation Order

This is still one pass, but the order matters.

1. Lock down invariants, compatibility rules, and budget semantics.
   The repo should define the operational model before it adds more optional features.

2. Finish the optional background-operations layer.
   Queue semantics, worker recovery, and inspection come before richer coordination.

3. Expand optional root-level coordination.
   Scheduling and transfer logic should build on durable worker state and clear inspection.

4. Enforce governance and lifecycle behavior.
   Limits and cleanup should be real controls, not passive reporting.

5. Harden observability and extension boundaries.
   Reports, traces, bundles, and plugins should become safer and easier to inspect.

## Verification

This pass is not done until both the simple path and the advanced path are proven.

Add or expand tests for:

- queue creation and claim semantics
- stale-lease recovery and worker interruption recovery
- concurrent worker contention
- pause, resume, cancel, and drain transitions
- portfolio scheduling decisions and transfer suggestion generation
- budget enforcement and budget attribution
- retention, archival, and cleanup behavior
- plugin validation and export redaction
- compatibility behavior for versioned persisted state

Cover end-to-end flows for:

- a default local foreground campaign
- optional background `run-campaign`
- worker-loop execution across multiple workspaces
- root-level orchestration with transfer suggestions
- artifact pruning and archival with reference preservation

Acceptance scenarios:

1. A new user can still run a useful local campaign without touching worker or root-level features.
2. Two workers racing for queued campaigns do not double-execute the same campaign.
3. A worker can crash mid-campaign and another worker can recover the lease safely.
4. Root-level scheduling can prioritize among multiple workspaces using stored history without starving all but one workspace.
5. Budget exhaustion stops or throttles work in the expected scope and is visible in inspection output.
6. Artifact cleanup preserves active campaigns, champions, and referenced exports.
7. Operators can inspect queue state, worker state, retries, and resource usage without reading raw JSON files.

## Done

This pass is complete when:

- the default onboarding path is still simple
- advanced operations are clearly optional rather than mandatory concepts
- background execution is reliable under contention
- portfolio scheduling and transfer logic operate on real historical state
- governance is enforceable and inspectable
- lifecycle cleanup is safe and reference-aware
- exports, traces, and plugins are materially better hardened
- the relevant operational and integration test suite passes
