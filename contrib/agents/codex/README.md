# Codex Wrapper

Generate a Codex-specific onboarding brief:

```bash
autoharness guide --assistant codex
```

That writes `autoharness.codex.md` and `autoharness.onboarding.json` next to `autoharness.yaml` unless you override the assistant output paths.

In Codex, point the agent at:

- `docs/ONBOARDING.md`
- `autoharness.codex.md`
- `autoharness.onboarding.json`
- `autoharness.yaml`
- `benchmarks/screening.yaml`

Then use [`PROMPT.md`](PROMPT.md) as the starting instruction.
