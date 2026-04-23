# Quickstart

This guide uses the `generic_command` adapter, which lets you wrap any stable eval command behind autoharness.

## 1. Install

Recommended:

```bash
pipx install "git+https://github.com/kayba-ai/autoharness.git"
```

Alternative:

```bash
python3 -m pip install --user "git+https://github.com/kayba-ai/autoharness.git"
```

Verify the CLI is available:

```bash
autoharness --help
```

## 2. Write a Benchmark Config

Create `benchmark.yaml`:

```yaml
benchmark_name: smoke
workdir: .
command: ["python", "-c", "print('ok')"]
```

This is the smallest useful `generic_command` benchmark. Replace the command with your real harness eval entrypoint.

## 3. Choose an Autonomy Mode

Write settings for the current repo:

```bash
autoharness setup --autonomy bounded --editable-surface src --editable-surface prompts
```

Modes:

- `proposal`: draft proposals only
- `bounded`: apply changes only inside approved editable surfaces
- `full`: edit broadly except for protected surfaces

## 4. Initialize a Workspace

```bash
autoharness init-workspace \
  --workspace-id demo \
  --objective "Improve pass rate without regressions" \
  --benchmark generic-smoke
```

This creates durable state under `.autoharness/workspaces/demo/`.

## 5. Run the Benchmark Directly

```bash
autoharness run-benchmark \
  --adapter generic_command \
  --config benchmark.yaml \
  --stage screening
```

Use this first to confirm your benchmark config is stable before you involve proposals or campaigns.

## 6. Generate a Proposal

Inspect the built-in generators:

```bash
autoharness list-generators
autoharness show-generator --generator openai_responses
```

Then generate one proposal against a target harness root:

```bash
export OPENAI_API_KEY=...
autoharness generate-proposal \
  --workspace-id demo \
  --adapter generic_command \
  --config benchmark.yaml \
  --generator openai_responses \
  --intervention-class source \
  --generator-option proposal_scope=balanced \
  --target-root /path/to/harness \
  --stage screening
```

This persists a proposal artifact without executing the benchmark.

## 7. Run a Campaign

For a generator-driven outer loop:

```bash
autoharness run-campaign \
  --workspace-id demo \
  --adapter generic_command \
  --config benchmark.yaml \
  --generator openai_responses \
  --intervention-class source \
  --target-root /path/to/harness \
  --stage screening \
  --max-iterations 10
```

This uses proposal generation plus benchmark execution to run a resumable search loop.

## 8. Know Where State Lives

The key files are:

- `.autoharness/settings.yaml`
- `.autoharness/workspaces/<workspace_id>/workspace.json`
- `.autoharness/workspaces/<workspace_id>/state.json`
- `.autoharness/workspaces/<workspace_id>/tracks/<track_id>/proposals/`
- `.autoharness/workspaces/<workspace_id>/tracks/<track_id>/registry/`
- `.autoharness/workspaces/<workspace_id>/iterations/`

## 9. Extensions

autoharness does not ship Codex-style `SKILL.md` files. The extension surface is Python plugins.

Plugin discovery looks in:

- `.autoharness/plugins/*.py`
- paths listed in `AUTOHARNESS_PLUGIN_PATHS`

Plugins can add:

- proposal generators
- preflight checks
- search strategies

Inspect the loaded plugin catalog with:

```bash
autoharness show-plugin-catalog --json
```
