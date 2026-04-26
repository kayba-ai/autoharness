# Autoharness Onboarding Spec

This document is the canonical onboarding spec for assistants and wrappers that help a user set up `autoharness`.

The goal is to help the user produce a safe, minimal, runnable setup for one target repo.

## Output Targets

The onboarding flow should aim to produce:

- `autoharness.yaml`
- `benchmarks/screening.yaml`
- `autoharness.onboarding.json` when an assistant handoff is needed
- optionally `benchmarks/promotion.yaml`
- optionally `autoharness.project.md`

## Assistant Behavior

The assistant should:

1. ask one or two focused questions at a time
2. keep a short running summary of what is already known
3. prefer the smallest useful setup over a theoretically complete one
4. warn about flaky or leaky benchmarks
5. avoid editing application code during onboarding unless explicitly asked
6. aim to finish by writing the starter files and validating them with a doctor-style readiness pass

## Information To Gather

The assistant should gather or infer:

- target repo root
- likely editable surfaces
- likely protected surfaces
- benchmark command candidates
- whether the benchmark is deterministic enough for optimization
- the starting autonomy mode
- a workspace id and a short optimization objective

## Benchmark Guidance

The assistant should strongly prefer benchmarks that:

- are already part of the repo or team workflow
- can be run repeatedly
- are comparable across candidates
- do not leak hidden test answers into prompts
- fail loudly when the harness is broken

The assistant should warn when:

- the benchmark command is unclear
- tests are too slow for iterative use
- metrics are not stable enough for repeated validation
- the benchmark appears to depend on mutable external state

## Minimal Good Outcome

A successful onboarding flow should leave the user able to run:

```bash
autoharness doctor
autoharness run-benchmark
autoharness optimize
autoharness report
```

without requiring a long explanation of tracks, roots, leases, bundles, or plugins.

## Wrapper Guidance

Codex, Claude Code, and similar assistants should treat this document as the source of truth for setup behavior.

Assistant-specific wrappers may add convenience, but they should not redefine the product model.

When `guide --assistant ...` is used, the generated `autoharness.onboarding.json` file should be treated as the assistant handoff packet. It contains known facts, doctor findings, open questions, and the recommended next action.

Checked-in wrapper prompts live under `contrib/agents/`.
