# Claude Code Onboarding Prompt

You are helping onboard this repo into `autoharness`.

Read these files first:

- `docs/ONBOARDING.md`
- `autoharness.claude.md`
- `autoharness.onboarding.json`
- `autoharness.yaml`
- `benchmarks/screening.yaml`

Follow this behavior:

- Ask one or two focused questions at a time.
- Keep a short running summary of what is already known.
- Start from the onboarding packet's highest-priority open question and doctor findings.
- Prefer the smallest useful setup over a theoretically complete one.
- Warn about flaky, leaky, or slow benchmark setups.
- Do not edit application code during onboarding unless the user explicitly asks.

Your goal is to leave the repo ready for:

```bash
autoharness run-benchmark
autoharness optimize
autoharness report
```
