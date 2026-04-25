# Usage

This page is the shortest path from "the CLI is installed" to "I know which command to run next."

If you want a step-by-step setup guide, start with [Quickstart](quickstart.md).

## Typical Flow

The common path looks like this:

1. configure autonomy and editable surfaces
2. initialize a workspace
3. confirm the benchmark runs directly
4. generate one proposal or run one iteration
5. run a campaign when the benchmark and proposal path are stable
6. inspect or promote the winner

## Core Commands

Set up the repo once:

```bash
autoharness setup --autonomy bounded --editable-surface src --editable-surface prompts
autoharness init \
  --workspace-id demo \
  --objective "Improve pass rate without regressions" \
  --benchmark generic-smoke
```

Run the benchmark directly:

```bash
autoharness run-benchmark \
  --adapter generic_command \
  --config benchmark.yaml \
  --stage screening
```

Generate one proposal without executing it:

```bash
autoharness generate-proposal \
  --workspace-id demo \
  --adapter generic_command \
  --config benchmark.yaml \
  --generator openai_responses \
  --intervention-class source \
  --target-root /path/to/harness \
  --stage screening
```

Run one iteration:

```bash
autoharness run-iteration \
  --workspace-id demo \
  --adapter generic_command \
  --config benchmark.yaml \
  --generator openai_responses \
  --intervention-class source \
  --target-root /path/to/harness \
  --stage screening
```

Run the outer loop:

```bash
autoharness optimize \
  --workspace-id demo \
  --adapter generic_command \
  --config benchmark.yaml \
  --generator openai_responses \
  --intervention-class source \
  --target-root /path/to/harness \
  --stage screening \
  --max-iterations 10
```

## Inspect Results

Use these commands to inspect persisted state:

```bash
autoharness show-campaigns --workspace-id demo
autoharness show-campaign --workspace-id demo --campaign-id <campaign_id>
autoharness show-proposals --workspace-id demo --track-id main
autoharness compare-to-champion --workspace-id demo --track-id main --record-id <record_id>
autoharness report --workspace-id demo
```

If a campaign was interrupted, resume it:

```bash
autoharness resume-campaign --workspace-id demo --campaign-id <campaign_id>
```

## Promote a Winner

If a record beats the current champion, promote it:

```bash
autoharness promote-from-compare \
  --workspace-id demo \
  --track-id main \
  --record-id <record_id>
```

## When To Use What

- Use `run-benchmark` first when validating the benchmark config.
- Use `generate-proposal` when you want to inspect candidate edits before execution.
- Use `run-iteration` when you want one executed candidate.
- Use `optimize` when you want a resumable search loop.
- Use `show-*` commands when you want to inspect persisted state instead of rerunning work.

## Advanced Features

Background workers, queue inspection, root-level coordination, retention policy, and plugin hooks exist, but they are optional. They are useful once you are already comfortable with the core local workflow.
