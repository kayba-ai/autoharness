# Usage

This page is the shortest path from "the CLI is installed" to "I know which command to run next."

If you want a step-by-step setup guide, start with [Quickstart](quickstart.md).

## Typical Flow

The common path looks like this:

1. run `guide` to write `autoharness.yaml` and starter benchmark config
2. configure autonomy and editable surfaces
3. initialize a workspace
4. confirm the benchmark runs directly
5. generate one proposal or run one iteration
6. run a campaign when the benchmark and proposal path are stable
7. inspect or promote the winner

## Core Commands

Guide and set up the repo once:

```bash
autoharness guide
autoharness setup
autoharness init
```

If you want a coding assistant to drive onboarding, generate a brief first:

```bash
autoharness guide --assistant codex
# or
autoharness guide --assistant claude
```

This writes an assistant-specific brief next to `autoharness.yaml`. Wrapper prompts live under [`contrib/agents/`](../contrib/agents/README.md).

Run the benchmark directly:

```bash
autoharness run-benchmark
```

Generate one proposal without executing it:

```bash
autoharness generate-proposal
```

Assistant-backed proposal generators are also available when the local CLI is installed and authenticated:

```bash
autoharness show-generator --generator codex_cli
autoharness show-generator --generator claude_code
```

Run one iteration:

```bash
autoharness run-iteration --hypothesis "candidate idea"
```

Run the outer loop:

```bash
autoharness optimize
```

## Inspect Results

Use these commands to inspect persisted state:

```bash
autoharness show-campaigns
autoharness show-campaign --campaign-id <campaign_id>
autoharness show-proposals --track-id main
autoharness compare-to-champion --track-id main --record-id <record_id>
autoharness report
```

If a campaign was interrupted, resume it:

```bash
autoharness resume-campaign --campaign-id <campaign_id>
```

## Promote a Winner

If a record beats the current champion, promote it:

```bash
autoharness promote-from-compare \
  --track-id main \
  --record-id <record_id>
```

## When To Use What

- Use `run-benchmark` first when validating the benchmark config.
- Use `generate-proposal` when you want to inspect candidate edits before execution.
- Use `run-iteration` when you want one executed candidate.
- Use `optimize` when you want a resumable search loop.
- Use `--project-config /path/to/autoharness.yaml` when you want to point commands at a config outside the current directory tree.
- Use `show-*` commands when you want to inspect persisted state instead of rerunning work.

## Advanced Features

Background workers, queue inspection, root-level coordination, retention policy, and plugin hooks exist, but they are optional. They are useful once you are already comfortable with the core local workflow.
