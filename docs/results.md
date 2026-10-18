# GovSim research log: results by step

One file for the results of every step. Run outputs live in `simulation/results/` (gitignored).

## Setup from a fresh clone
```
git clone --recurse-submodules https://github.com/smaswin21/GovSim.git
cd GovSim && scripts/apply_patches.sh
```
Run results (`simulation/results/`) are gitignored and not in the repo.

# Step 1 - reproduce a fishery baseline (claude-haiku-5-5)

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

# Step 2 - prompt anatomy

One run: `claude-haiku-5-5`, seed 1, 4 rounds, memory tags on (`+debug_memory_tags=true`), 12.1 min wall, 725,143 tokens in / 233,155 out. Output: `simulation/results/fishing_v7.0/haiku55_anatomy/dummy-czut34qd/` (`prompts.json`, `anatomy.csv`, `anatomy.md`). The run logged 3 swallowed "Cant find ... in Mayor" exceptions.

Reproduce:
```
PYTHONPATH=./ python -m simulation.main experiment=fish_baseline_concurrent llm.path=claude-haiku-5-5 \
  llm.is_api=true llm.backend=none seed=1 group_name=haiku55_anatomy debug=true \
  +debug_memory_tags=true experiment.env.max_num_rounds=4
python -I scripts/prompt_anatomy.py simulation/results/fishing_v7.0/haiku55_anatomy/<run>
```

## What a prompt contains
Every prompt that carries memory has the same layout:
1. Fixed rules: the v3 system prompt (fishery rules, carrying capacity 100, doubling, income goal, the five names).
2. `Location:` and `Date:` lines. The date is the day of the phase (1st of the month for harvest, around month end for discussion and reflection).
3. `Key memories of {name} (format: YYYY-MM-DD: memory):` followed by retrieved memory lines.
4. The task: a catch-size question with step-by-step reasoning (harvest), a group-chat scenario with the conversation so far (discussion), or "what high-level insights..." (reflection).

Only three phases show a memory block: harvest (`choose_act_options`), discussion (`converse_utterance`) and reflection (`prompt_insight_and_evidence`). The other prompts (importance scoring, planning, memorising a conversation, one-sentence summary, finding the agreed limit) contain no memory block. Chat nodes are never retrieved.

## Memory lines per prompt, by tag
Average memory lines in one prompt (4 rounds; harvest and reflection: 5 prompts per month, one per agent; discussion: 9 per month):

| phase | month | event,always | thought,always | thought | total lines/prompt |
|---|---|---|---|---|---|
| discussion | 1 | 2.0 | 0.0 | 0.0 | 2.0 |
| discussion | 2 | 2.0 | 1.0 | 2.6 | 5.6 |
| discussion | 3 | 2.0 | 2.0 | 1.9 | 5.9 |
| discussion | 4 | 2.0 | 2.8 | 0.4 | 5.2 |
| harvest | 1 | 1.0 | 0.0 | 0.0 | 1.0 |
| harvest | 2 | 1.0 | 1.0 | 5.0 | 7.0 |
| harvest | 3 | 1.0 | 2.0 | 7.0 | 10.0 |
| harvest | 4 | 1.0 | 3.0 | 6.0 | 10.0 |
| reflection | 1 | 0.0 | 1.0 | 2.0 | 3.0 |
| reflection | 2 | 0.0 | 2.0 | 7.0 | 9.0 |
| reflection | 3 | 0.0 | 3.0 | 7.0 | 10.0 |
| reflection | 4 | 0.0 | 3.0 | 7.0 | 10.0 |

Full table with memory tokens and whole-prompt tokens (cl100k proxy, not Claude's tokenizer): `anatomy.md` in the run folder. Examples of whole-prompt size: harvest 3.7k tokens summed over 5 prompts in month 1 and 6.3k in month 3; discussion 9.7k summed over 9 prompts in month 1 and 13.7k in month 4. Thoughts hold most memory tokens (about 50 to 70 tokens each; the agreed-limit thoughts are about 16).

## Findings
- **Where the lake level comes from.** The only memory line that tells a harvesting agent the current stock is one `[event, always]` line per prompt: "Before everyone fishes, there are N tons of fish in the lake." The discussion prompt has two `[event, always]` lines (the stock before and after harvesting, which carries the catch outcome).
- **The agreed limit** reaches agents only as a `[thought, always]` line ("The community agreed on a maximum limit of N tons ..."). These pile up: 1 per prompt in month 2, up to 3 by month 4, with the limit restated each month.
- **The rest is free-form thoughts** (reflections and conversation notes) that fill the retrieval cap: harvest and reflection prompts reach the 10-line cap (top_k 10) from month 3.
- **Retention.** Event nodes expire at the end of their month (`get_expiration_next_month`, `concurrent_env.py:20-33`), so the lake-level line is always current-month only. Thoughts expire after `expiration_delta` = 63 days (`fish_baseline_concurrent.yaml:58-60`), so by month 4 prompts still contain thoughts from months 2 and 3: the default memory spans about two months.
- **Implication for the minimal-memory condition (later step).** It must keep the current-month `always_include` nodes: the `[event, always]` stock and post-harvest lines, and the `[thought, always]` agreed-limit line. Without them agents do not know the lake level or the limit. Everything tagged plain `[thought]` is the part that can be removed.

## Code changes for Step 2
- `retrieve()` (`simulation/persona/cognition/retrieve.py`) returns `(created, description, type, always_include)`.
- `memory_prompt()`/`numbered_memory_prompt()` (`.../persona_v3/cognition/utils.py`) prefix lines with `[type, always]` when `+debug_memory_tags=true`; default off, so normal prompts are unchanged.
- `simulation/main.py` also writes `prompts.json` (all prompts/responses per agent, with chain names) next to `usage.json`; the harvest and discussion prompts are also in `log_env.json`, but reflection prompts only exist in `prompts.json`.
- `scripts/prompt_anatomy.py` produces the tables.

Limits: one seed and 4 rounds; the thought contents vary by run. Only the fishing scenario is tagged (sheep and pollution use their own `memory_prompt`).

# Step 3 - pilot model selection

_Not started._

# Step 4 - harder settings

_Not started._

# Running checklist (actions for you)
- [ ] Provide the paper's Appendix D.2 / Table 1 fishery survival numbers (or ask me to fetch them), and say which Table 1 model is the right reference for a Haiku-class model.
- [x] Pathfinder patch is kept as `patches/pathfinder-anthropic.patch` (applied by `scripts/apply_patches.sh`).
- [ ] Keep `.env` private (it is gitignored and holds `ANTHROPIC_API_KEY`).
- [ ] Decide whether to investigate the "Cant find ... in Mayor" exceptions before the pilot (recommended).
- [ ] Choose an option for open models (vLLM/GPU host). The pinned vLLM 0.6.4 is likely too old.
- [ ] Approve spend for later steps: about 2.1M in / 0.75M out tokens per Haiku-class run; the pilot is models x 5 seeds.
- [ ] Expect to need harder settings (Step 4), since this model is at ceiling.
- [ ] Step 2: review the findings above; decide if one seed / 4 rounds is enough or if you want more.
