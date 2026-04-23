# Design Notes

This repo is the public autoharness extraction.

## Included

- autonomy selection at setup time
- explicit campaign comparability
- workspace bootstrap files
- intervention taxonomy

## Deferred

- benchmark adapters
- registry ranking
- screening / validation / transfer orchestration
- patch proposal and patch application execution
- trace analysis and statistical comparison

## Why This Starts Small

The main risk in an open-source extraction is exposing an attractive but vague
"self-improving agent" story without enough operator control. The first public
version should make the control plane explicit before it makes the optimizer
powerful.
