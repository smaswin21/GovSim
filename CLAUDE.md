# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

GovSim ("Cooperate or Collapse", NeurIPS 2024): LLM agents share a commons (fishery, sheep pasture, pollution) and the benchmark measures whether they cooperate or collapse the resource. This checkout is a fork on branch `research-setup` used for a research log with Claude models (see `docs/results.md` for results by step and `docs/findings_and_next_steps.md` for open work).

## Setup

- `pathfinder/` is a git submodule (LLM backend wrapper). After cloning run `scripts/apply_patches.sh`; it inits the submodule and applies `patches/pathfinder-anthropic.patch` (token accounting, thinking disabled, no `temperature`/`top_p` for Anthropic). Edits inside `pathfinder/` must be re-exported into that patch file, since the submodule itself is not committed here.
- Python 3.11 in `.venv`; API keys go in `.env` (see `.env_example`). `PYTHONPATH=./` must be set.
- `setup.sh` / `setup_vllm.sh` are the upstream conda installers for local `transformers`/vLLM models.

## Commands

```
# one simulation (Anthropic API model); source .env first
PYTHONPATH=./ python -m simulation.main experiment=fish_baseline_concurrent \
  llm.path=claude-haiku-5-5 llm.is_api=true llm.backend=none seed=1 \
  group_name=<name> debug=true hydra.run.dir=outputs/<name>_s1

# one model, several seeds in parallel, then auto-aggregate
scripts/run_model.sh <model-id> [experiment] ["1 2 3 4 5"] [extra hydra args]
python -I scripts/aggregate_pilot.py --group <group> [--md docs/pilot_summary.md]

# per-prompt memory/size breakdown of a run (needs +debug_memory_tags=true on the run)
python -I scripts/prompt_anatomy.py simulation/results/fishing_v7.0/<group>/<run>

# subskill evals
python3 -m subskills.fishing llm.path=<model>

# multi-LLM (one model per persona via mix_llm)
python3 -m simulation.main --config-name=multiple_llm experiment=<id>
```

- Always pass `debug=true` for API runs: `WANDB_MODE=disabled` crashes `wandb.init`, so `debug` is how wandb is turned off.
- Experiment ids: `{fish,sheep,pollution}_baseline_concurrent`, `*_baseline_concurrent_universalization`, `*_perturbation_no_language`, `fish_perturbation_outsider`. Configs live under each scenario's `conf/experiment/`; global config is `simulation/conf/config.yaml`.
- There is no repo-level test suite; the only tests are in `pathfinder/tests` (`pytest`). Formatting is `black`.
- A fishing run takes about 39 min and about 2.1M tokens in / 0.75M out for Haiku 5.5 (12 months, 5 agents).

## Architecture

- **Entry point** `simulation/main.py`: Hydra config, builds the model through `pathfinder.get_model`, wraps it in `ModelWandbWrapper` (logging, token counts), then dispatches to `simulation/scenarios/{fishing,sheep,pollution}/run.py`. It writes `simulation/results/<experiment>/<run>/` with `log_env.json`, `usage.json` (seed, wall time, tokens), `prompts.json` (all prompts and responses per agent, by chain name) and per-persona folders. `simulation/results/` and `outputs/` are gitignored.
- **Generic agent layer** `simulation/persona/`: `persona.py`, `memory/associative_memory.py` (event/thought/chat/action nodes with expiry and importance), and `cognition/` (perceive, retrieve, store, plan, reflect, converse, act components).
- **Scenario-specific agents** `simulation/scenarios/<scenario>/agents/persona_v3/`: `persona.py` wires the components, and `cognition/*_prompts.py` holds every LLM prompt (act, converse, reflect, store, plus `utils.py` with the system prompt and memory formatting). `environment/env.py` is the PettingZoo-style concurrent environment (fish doubling up to capacity 100, per-month harvest).
- **Month loop** (per round): agents retrieve memory, each chooses a harvest in `act`, the environment applies it, then the agents hold a group discussion (`converse`), reflect, and extract any agreed harvesting limit, which is stored as a memory thought.
- **Prompt variants are module-level globals**: `fishing/run.py` sets `cognition/utils.py` `SYS_VERSION` (from `agent.system_prompt`: v1, v3, v3_p1/p2/p3, v3_nocom) and `REASONING` (from `agent.cot_prompt`), and `main.py` calls `set_memory_tags(cfg.debug_memory_tags)`. They are not function arguments, so check there when a prompt's text surprises you.
- **Memory tags**: `+debug_memory_tags=true` prefixes memory lines with `[type, always]` for analysis; it is off by default and only implemented for fishing. Event nodes expire at the end of their month, thoughts after `expiration_delta` = 63 days, and retrieval is capped at top_k 10.
- `subskills/<scenario>/` re-implements prompts without memory for isolated skill tests (separate from the cognition prompts). `simulation/analysis/` is a Dash app for viewing results.

## Known quirks

- The framework swallows `Cant find (John|Kate|Jack|Emma|Luke) in Mayor` exceptions and substitutes a default. Cause: the model names the framework's "Mayor" as `Next speaker`, which is not among the five allowed options, so `select` fails and falls back to `options[0]` (see `docs/findings_and_next_steps.md`). For how the simulation and memory work, see `docs/architecture.md`; `+experiment.agent.memory_mode=minimal` enables the minimal-memory condition.
- Environment fish allocation is not seeded, so runs with the same seed are not exactly reproducible.
- Only the fishing scenario has been exercised with Claude models here; sheep and pollution use their own prompt files and `memory_prompt`.
