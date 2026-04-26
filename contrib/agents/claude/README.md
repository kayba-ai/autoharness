# Claude Code Wrapper

Generate a Claude-specific onboarding brief:

```bash
autoharness guide --assistant claude
```

That writes `autoharness.claude.md` and `autoharness.onboarding.json` next to `autoharness.yaml` unless you override the assistant output paths.

In Claude Code, point the agent at:

- `docs/ONBOARDING.md`
- `autoharness.claude.md`
- `autoharness.onboarding.json`
- `autoharness.yaml`
- `benchmarks/screening.yaml`

Then use [`PROMPT.md`](PROMPT.md) as the starting instruction.
