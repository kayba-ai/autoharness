# Codex Wrapper

Generate a Codex-specific onboarding brief:

```bash
autoharness guide --assistant codex
```

That writes `autoharness.codex.md` next to `autoharness.yaml` unless you override `--assistant-brief-path`.

In Codex, point the agent at:

- `docs/ONBOARDING.md`
- `autoharness.codex.md`
- `autoharness.yaml`
- `benchmarks/screening.yaml`

Then use [`PROMPT.md`](PROMPT.md) as the starting instruction.
