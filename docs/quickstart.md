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

## 2. Run The Guide

Ask autoharness to inspect the repo and write starter files:

```bash
autoharness guide
```

If you want Codex or Claude to help refine the setup, generate an assistant brief too:

```bash
autoharness guide --assistant codex
# or
autoharness guide --assistant claude
```

This writes:

- `autoharness.yaml`
- `benchmarks/screening.yaml`
- `autoharness.project.md`

With `--assistant`, it also writes `autoharness.codex.md` or `autoharness.claude.md` plus `autoharness.onboarding.json`. Wrapper prompts live under [`contrib/agents/`](../contrib/agents/README.md).

If you run `guide` in a TTY, it asks a few focused setup questions and finishes with a doctor pass. Inspect `benchmarks/screening.yaml` and replace the generated command if needed.

## 3. Choose an Autonomy Mode

The generated `autoharness.yaml` already carries a default autonomy mode and editable surfaces. On the common path, autoharness can bootstrap missing settings and workspace state automatically.

If you want to manage that bootstrap explicitly, run:

```bash
autoharness setup
```

Modes:

- `proposal`: draft proposals only
- `bounded`: apply changes only inside approved editable surfaces
- `full`: edit broadly except for protected surfaces

If you want to rerun the readiness checks later, use:

```bash
autoharness doctor
```

## 4. Initialize a Workspace

On the common path, `run-benchmark`, `optimize`, and `report` can auto-create the workspace described in `autoharness.yaml`.

If you want to create it explicitly, run:

```bash
autoharness init
```

This creates durable state under `.autoharness/workspaces/demo/`.

## 5. Run the Benchmark Directly

```bash
autoharness run-benchmark
```

Use this first to confirm your benchmark config is stable before you involve proposals or campaigns. If settings or workspace state are missing, autoharness will bootstrap them from `autoharness.yaml`.

## 6. Generate a Proposal

Inspect the built-in generators:

```bash
autoharness list-generators
autoharness show-generator --generator openai_responses
```

Then generate one proposal against a target harness root:

```bash
autoharness generate-proposal
```

This persists a proposal artifact without executing the benchmark.

If you want to use the OpenAI-backed generator specifically, export an API key first:

```bash
export OPENAI_API_KEY=...
```

If you want to use a local coding assistant instead of the OpenAI-backed generator, use:

```bash
autoharness show-generator --generator codex_cli
autoharness show-generator --generator claude_code
```

## 7. Run a Campaign

For a generator-driven outer loop:

```bash
autoharness optimize
```

This uses proposal generation plus benchmark execution to run a resumable search loop.

Inspect the current workspace summary at any point with:

```bash
autoharness report
```

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
