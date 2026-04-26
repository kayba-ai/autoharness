# Assistant Wrappers

These wrappers keep Codex and Claude onboarding aligned with `docs/ONBOARDING.md`.

Typical flow:

1. run `autoharness guide --assistant codex` or `autoharness guide --assistant claude`
2. open the generated `autoharness.<assistant>.md`
3. use the matching prompt in this directory to drive the onboarding conversation
4. refine `autoharness.yaml` and `benchmarks/screening.yaml`
5. run `autoharness setup`, `autoharness init`, `autoharness run-benchmark`, and `autoharness optimize`

Files:

- `codex/PROMPT.md`: prompt text for Codex
- `claude/PROMPT.md`: prompt text for Claude Code

The wrappers are convenience only. `docs/ONBOARDING.md` remains the source of truth.
