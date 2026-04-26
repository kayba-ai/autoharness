<p align="center">
  <img src="docs/images/harness_on_harness2.png" alt="autoharness banner" width="900">
</p>

# autoharness

Let autoharness run overnight and come back to an optimized agent harness, so your agents never make mistakes again.

autoharness improves agent harnesses by proposing or applying prompt, config, middleware, and source changes, running evals, and keeping or discarding candidates based on benchmark results.

It is a control plane for an existing harness repo. You point it at a target root and a benchmark command; autoharness manages proposals, iterations, campaigns, and champion state under `.autoharness/`.

## Install

```bash
pipx install "git+https://github.com/kayba-ai/autoharness.git"
autoharness --help
```

If you do not use `pipx`:

```bash
python3 -m pip install --user "git+https://github.com/kayba-ai/autoharness.git"
```

## How It Works

- `guide` inspects a repo and writes a starter `autoharness.yaml` plus benchmark config.
- `setup` and `init` remain available when you want to manage bootstrap explicitly.
- `run-benchmark` executes one benchmark directly.
- `generate-proposal` previews one candidate change without running it.
- `run-iteration` or `optimize` executes one candidate or a resumable search loop.
- `promote` or `promote-from-compare` moves a winner into champion state.

## Mental Model

- `target root`: the harness repo or deployment tree to edit
- `benchmark config`: the command or adapter config that scores candidates
- `workspace`: the long-lived optimization effort
- `track`: one comparable lane inside a workspace
- `campaign`: a resumable search run over candidate proposals
- `.autoharness/`: persisted settings, proposals, records, iterations, and champions

## Batteries Included

- Adapters: `generic_command`, `pytest`, `harbor`, `tau2_bench`, `hal`, `car_bench`
- Proposal generators: `manual`, `failure_summary`, `local_template`, `local_command`, `openai_responses`, `codex_cli`, `claude_code`
- Extension model: Python plugins can add generators, preflight checks, and search strategies from `.autoharness/plugins/` or `AUTOHARNESS_PLUGIN_PATHS`


## Quick Start

Let autoharness generate a starter project config:

```bash
autoharness guide
```

If you want Codex or Claude to help you refine the setup, generate an assistant brief too:

```bash
autoharness guide --assistant codex
# or
autoharness guide --assistant claude
```

This writes `autoharness.codex.md` or `autoharness.claude.md` next to `autoharness.yaml`. Assistant wrapper prompts live under [`contrib/agents/`](contrib/agents/README.md).

Then run the benchmark directly:

```bash
autoharness run-benchmark
```

If `autoharness.yaml` is present, autoharness will auto-bootstrap missing settings and workspace state on this common path. `setup` and `init` are still available when you want explicit control.

Generate a proposal against a target harness root:

```bash
export OPENAI_API_KEY=...
autoharness generate-proposal
```

Run the outer loop:

```bash
autoharness optimize
autoharness report
```

## Docs

- [Quickstart](docs/quickstart.md)
- [Usage](docs/usage.md)

## For Power Users

- Background campaign workers plus queue and worker-state inspection
- Root-level memory, transfer suggestions, and portfolio scheduling
- Retention policies, pruning, and portable report and bundle exports
- Event logs, inspection commands, and operational reporting surfaces
- Python plugin hooks for generators, preflight checks, and search strategies
