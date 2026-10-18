# Step 1 results: reproduce a fishery baseline with claude-haiku-5-5

## Setup
- Model `claude-haiku-5-5`, experiment `fish_baseline_concurrent`, seeds 1-5.
- `debug=true` (wandb disabled; `WANDB_MODE=disabled` crashes `wandb.init`), extended thinking disabled, no `temperature`/`top_p` sent (SDK 1.15.0 rejects them).
- Command (per seed `$S`):

```
set -a; source .env; set +a
PYTHONPATH=./ python -m simulation.main experiment=fish_baseline_concurrent \
  llm.path=claude-haiku-5-5 llm.is_api=true llm.backend=none seed=$S \
  group_name=haiku55_baseline debug=true hydra.run.dir=outputs/haiku55_s$S
```

## Setup from a fresh clone
```
git clone --recurse-submodules https://github.com/smaswin21/GovSim.git
cd GovSim && scripts/apply_patches.sh
```
Run results (`simulation/results/`) are gitignored and not in the repo.

## Results
All five seeds survived all 12 months (ceiling).

| Seed | Survival | Min pool after harvest | Wall (min) | Tokens in | Tokens out |
|---|---|---|---|---|---|
| 1 | 12/12 | 48 | 39.1 | 2,110,443 | 740,953 |
| 2 | 12/12 | 50 | 39.2 | 2,131,885 | 775,384 |
| 3 | 12/12 | 50 | 39.2 | 2,118,294 | 730,823 |
| 4 | 12/12 | 50 | 39.1 | 2,146,740 | 741,176 |
| 5 | 12/12 | 50 | 38.1 | 2,158,810 | 782,158 |

- The pool refilled to 100 every month (seed 1: 96 in month 2).
- Five runs in parallel took about 39 min wall (~4 min per round). Total about 10.6M tokens in and 3.8M out.
- Output: `simulation/results/fishing_v7.0/haiku55_baseline/dummy-*`. Each folder has `usage.json` (includes the seed), `log_env.json`, and `persona_*`.
- Comparison with the paper's Appendix D.2 has NOT been done.

## Code changes made
- `pathfinder/pathfinder/api.py`, `AnthropicAPI.request_api`: records `token_in`/`token_out` from `out.usage`, sets `thinking={"type": "disabled"}`, joins text blocks, drops `temperature`/`top_p`. This lives inside the submodule, so it is tracked as `patches/pathfinder-anthropic.patch`; run `scripts/apply_patches.sh` after cloning.
- `simulation/main.py`: writes `usage.json` (model, seed, wall time, tokens) per run.
- Environment: `.venv` (Python 3.11), numpy==1.26.4 via a uv override, `setuptools<81` for wandb.

## Caveats
- 55 swallowed `Cant find (John|Kate|Jack|Emma|Luke) in Mayor` exceptions across the 5 runs, plus one regex miss. The framework substitutes a default value. Cause not investigated.
- The environment's fish allocation is not seeded, so seeds are not exactly reproducible.

## Actions for you
- [ ] Provide the paper's Appendix D.2 / Table 1 fishery survival numbers (or ask me to fetch them), and say which Table 1 model is the right reference for a Haiku-class model.
- [x] Pathfinder patch is kept as `patches/pathfinder-anthropic.patch` (applied by `scripts/apply_patches.sh`).
- [ ] Keep `.env` private (it is gitignored and holds `ANTHROPIC_API_KEY`).
- [ ] Decide whether to investigate the "Cant find ... in Mayor" exceptions before the pilot (recommended).
- [ ] Choose an option for open models (vLLM/GPU host). The pinned vLLM 0.6.4 is likely too old.
- [ ] Approve spend for later steps: about 2.1M in / 0.75M out tokens per Haiku-class run; the pilot is models x 5 seeds.
- [ ] Expect to need harder settings (Step 4), since this model is at ceiling.

## Plan for Step 2 (prompt anatomy), not started
Goal: for each phase and round, count memory lines by type and their token length, and document the fixed prompt structure.

Relevant code:
- `retrieve()` in `simulation/persona/cognition/retrieve.py:167-180` returns `(created, description)`. Nodes also have `.type` (`NodeType`, `simulation/persona/memory/associative_memory.py:10`) and `.always_include`.
- `memory_prompt()` and `numbered_memory_prompt()` in `simulation/scenarios/fishing/agents/persona_v3/cognition/utils.py:51-74`.
- retrieve callers: `persona_v3/persona.py:83` (act, top_k 10), `cognition/converse.py:86` (discussion, top_k 5), `simulation/persona/cognition/reflect.py:23`. memory_prompt callers: `act_prompts.py:34`, `converse_prompts.py:39`, `reflect_prompts.py:25` (numbered).

Steps:
1. `retrieve()` returns 4-tuples `(created, description, type_name, always_include)`. Check each caller for tuple unpacking first.
2. `memory_prompt()`/`numbered_memory_prompt()` print a prefix such as `[event, always]` or `[thought]` when a flag is on. The flag defaults off so default prompts stay byte-identical. It is a module-level toggle set once in `main.py`.
3. Add `scripts/prompt_anatomy.py`. It reads `log_env.json` (`html_interactions`), parses the "Key memories of {name}" block, and counts lines per tag and token length per phase and round. Token length uses tiktoken as a proxy; whole-prompt tokens come from the logged `token_in`.
4. Run 1 seed for 4 rounds (`experiment.env.max_num_rounds=4`) with `claude-haiku-5-5` and the flag on. About 13 min and 0.7M input tokens.
5. Write `docs/prompt_anatomy.md` with:
   - the prompt structure: fixed rules, date line, memory block, task, plus dialogue in the discussion prompt;
   - the table of counts and tokens by phase, round and type;
   - retention settings: events expire at month end (`concurrent_env.py:20-33`), thoughts via `expiration_delta` 63 days (`fish_baseline_concurrent.yaml:58-60`);
   - the note that lake level, catches and the agreed limit reach agents only through `always_include` nodes (`concurrent_env.py:72,116`; `converse.py:137-145`), so the Step 6 minimal-memory condition must keep them.

Verification: with the flag off, prompts match the pre-change baseline; with it on, tagged lines appear and `[event, always]` lines are in every act and discussion prompt; script counts match a hand check of one prompt.
