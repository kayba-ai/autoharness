# Product Design

Date: 2026-04-25

This document defines what `autoharness` is, what it is not, and how the product should evolve without drifting into an overbuilt control plane.

## Product Contract

`autoharness` is a local optimizer runtime for agent harnesses.

It should help a user:

1. point at one target repo
2. point at one benchmark
3. run an optimization loop
4. inspect and promote stable winners

The default experience should feel small, explicit, and local.

`autoharness` is not:

- a hosted platform
- a general multi-tenant orchestration system
- a magic autonomous coding agent
- a model-training system

## Product Layers

The repo should have three layers with clear boundaries.

### 1. Core Product

This is the main product.

It includes:

- bounded edit application
- proposal generation
- benchmark execution
- repeated validation
- stability-aware comparison and promotion
- resumable optimization campaigns
- lightweight reporting

The common path should remain:

```bash
autoharness setup
autoharness init
autoharness run-benchmark
autoharness optimize
autoharness report
```

### 2. Guide Layer

This is an optional onboarding and supervision layer.

Its job is to help the user:

- understand whether their repo is a good fit
- choose editable and protected surfaces
- pick or write the right benchmark configs
- configure campaign defaults
- avoid obviously bad evaluation setups

The guide layer should make the product easier to adopt, not make the runtime itself more magical.

### 3. Power-User Operations

This is the advanced layer.

It includes:

- background workers
- queue inspection
- root-memory and transfer suggestions
- portfolio scheduling
- retention and pruning
- plugin loading and operator inspection

These features are real and useful, but they must remain optional.

## What Is Implemented Today

The repo already has a substantial optimizer runtime.

Implemented today:

- workspace, track, campaign, proposal, record, and champion persistence
- repeated validation with failure classification and stability summaries
- stage-aware gates and baseline comparison
- proposal generators including `manual`, `local_template`, `local_command`, `failure_summary`, and `openai_responses`
- OpenAI-backed proposal generation with broader multi-file prompting, repair attempts, and replay metadata
- search strategies and branch scoring
- compare/promote flows and resumable campaigns
- CLI onboarding improvements like `init`, `optimize`, `report`, and single-workspace inference on the common path

Also already implemented, but explicitly advanced:

- background campaign workers and queue inspection
- root-memory and transfer suggestion machinery
- retention policy and artifact pruning
- plugin discovery for generators, preflight checks, and search strategies

The repo is therefore already more than a minimal local tool. The main risk is product shape and exposure, not missing infrastructure.

## How To Reduce The Control-Plane Feel

The repo should not remove advanced capabilities. It should reduce how early users need to see them.

### Design Rules

1. Progressive disclosure wins.
2. The default path must stay local and foreground-first.
3. Internal complexity is acceptable only if public complexity stays low.
4. Advanced features must be clearly optional in docs and help text.
5. The product should be config-first rather than flag-heavy for common use.

### Public Mental Model

The public mental model should be:

- `target repo`
- `benchmark`
- `candidate`
- `optimize`
- `report`
- `champion`

`workspace` and `track` are still useful internally, but they should not dominate onboarding.

### Near-Term UX Direction

The next simplification step should be a project config file, for example:

- `autoharness.yaml`

That file should hold the common path defaults:

- target root
- workspace id
- editable and protected surfaces
- benchmark adapter and config paths
- default generator
- stage defaults
- campaign defaults

Once that exists, the common path can become:

```bash
autoharness guide
autoharness optimize
autoharness report
```

without making the runtime itself hidden or stateful.

## Guide Layer Design

The guide layer should be an explicit product feature.

### Proposed Command

Add:

- `autoharness guide`

This should not run optimization directly. It should prepare the repo for optimization.

### Responsibilities

`autoharness guide` should:

- inspect the repo layout
- identify likely harness entrypoints and evaluation commands
- ask the user for the minimum missing context
- propose editable and protected surfaces
- propose one or more benchmark configs
- recommend a safe starting autonomy mode
- generate a starter project config

### Outputs

The guide should aim to produce:

- `autoharness.yaml`
- `benchmarks/screening.yaml`
- optionally `benchmarks/promotion.yaml`
- optionally `benchmarks/transfer.yaml`
- a short project summary artifact such as `autoharness.project.md`

### Guide Interaction Style

The guide should:

- ask one or two focused questions at a time
- prefer concrete examples over abstract prompts
- avoid implementation during onboarding unless explicitly requested
- warn about benchmark leakage, flaky evals, and missing comparability
- prefer a safe minimal setup over a theoretically perfect one

## Agent Integration Design

Agent integration is desirable, but the boundary should stay clean.

### Principle

`autoharness` should own:

- run state
- validation
- scoring
- campaign logic
- promotion logic

The agent should help with:

- onboarding
- benchmark and config generation
- proposal generation
- optional run supervision

### Skills vs Runtime Integrations

Skills are useful, but they should not be the primary product contract.

Use skills for:

- Codex or Claude onboarding guidance
- user-facing setup help
- wrapper workflows around `autoharness`

Do not make skills the only way to use the product.

The runtime integration point should remain proposal generators and command-level guide flows.

### Recommended Structure

1. Keep one canonical onboarding spec in this repo.
   Example:
   - `docs/ONBOARDING.md`

2. Add optional agent-specific wrappers under a non-core path.
   Example:
   - `contrib/agents/codex/`
   - `contrib/agents/claude/`

3. Add coding-agent-backed proposal generators as normal generator backends when useful.
   Examples:
   - `codex_cli`
   - `claude_code`

4. Keep the guide and generator protocols generic enough that they are not tied to one assistant vendor.

## Recommended Product Direction

The product should be described as:

`autoharness is a local optimizer runtime for agent harnesses, with optional agent-assisted onboarding and optional power-user operations.`

That is the right balance:

- simple default story
- real optimizer core
- optional advanced tooling
- room for stronger autonomy without turning the repo into a black box

## Next Implementation Moves

The highest-value next moves are:

1. add `autoharness.yaml` support so the common path stops being flag-heavy
2. design and implement `autoharness guide`
3. create a canonical onboarding spec for agent wrappers
4. keep advanced ops features intact but further de-emphasized from the default surface
5. only then consider dedicated coding-agent generator backends
