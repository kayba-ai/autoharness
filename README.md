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

- `setup` defines autonomy plus editable and protected surfaces.
- `init` creates durable state for one optimization effort.
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
- Proposal generators: `manual`, `failure_summary`, `local_template`, `local_command`, `openai_responses`
- Extension model: Python plugins can add generators, preflight checks, and search strategies from `.autoharness/plugins/` or `AUTOHARNESS_PLUGIN_PATHS`


## Quick Start

Create a minimal benchmark config:

```yaml
benchmark_name: smoke
workdir: .
command: ["python", "-c", "print('ok')"]
```

Bootstrap a workspace and run the benchmark:

```bash
autoharness setup --autonomy bounded --editable-surface src --editable-surface prompts
autoharness init \
  --workspace-id demo \
  --objective "Improve pass rate without regressions" \
  --benchmark generic-smoke
autoharness run-benchmark \
  --adapter generic_command \
  --config benchmark.yaml \
  --stage screening
```

Generate a proposal against a target harness root:

```bash
export OPENAI_API_KEY=...
autoharness generate-proposal \
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
autoharness report --workspace-id demo
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
