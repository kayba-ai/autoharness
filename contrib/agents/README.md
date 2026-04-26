# Assistant Wrappers

These wrappers keep Codex and Claude onboarding aligned with `docs/ONBOARDING.md`.

Typical flow:

1. run `autoharness guide --assistant codex --print-next-prompt` or `autoharness guide --assistant claude --print-next-prompt`
2. paste the printed prompt into the assistant, or open the generated `autoharness.<assistant>.md` and `autoharness.onboarding.json`
3. use the matching prompt in this directory when you want a checked-in wrapper prompt
4. refine `autoharness.yaml` and `benchmarks/screening.yaml`
5. rerun `autoharness doctor` if needed, then `autoharness run-benchmark` and `autoharness optimize`

Files:

- `codex/PROMPT.md`: prompt text for Codex
- `claude/PROMPT.md`: prompt text for Claude Code

The wrappers are convenience only. `docs/ONBOARDING.md` remains the source of truth.
