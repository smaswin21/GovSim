"""Summarize finished runs: survival months, wall time and tokens per model/experiment.

Usage: python -I scripts/aggregate_pilot.py [--results DIR] [--group NAME] [--md FILE]

Convention (same as simulation/analysis/plots.py): a run collapses in the first round
whose pool after harvesting is below 5 tons; survival = that round index + 1.
A run that never collapses survives max_num_rounds months.
Groups named <model>__<experiment> come from scripts/run_model.sh; other groups
(e.g. haiku55_baseline) are listed too, with the model read from usage.json.
"""
import argparse
import glob
import json
import os
import statistics

import yaml


def survival(run_dir, max_rounds):
    rows = json.load(open(os.path.join(run_dir, "log_env.json")))
    after = {}
    for r in rows:
        a = r.get("resource_in_pool_after_harvesting")
        if a is not None:
            after[r["round"]] = a
    for rnd in sorted(after):
        if after[rnd] < 5:
            return rnd + 1, True
    return max_rounds, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="simulation/results/fishing_v7.0")
    ap.add_argument("--group", default=None)
    ap.add_argument("--md", default=None)
    args = ap.parse_args()

    groups = sorted(
        g for g in glob.glob(os.path.join(args.results, "*"))
        if os.path.isdir(g) and (args.group is None or os.path.basename(g) == args.group)
    )
    lines = ["| group | model | runs | survival months (per seed) | mean | collapsed | wall min/run | tokens in / out per run | fallbacks/run |",
             "|---|---|---|---|---|---|---|---|---|"]
    for g in groups:
        recs = []
        for run in sorted(glob.glob(os.path.join(g, "*"))):
            uf = os.path.join(run, "usage.json")
            if not (os.path.isfile(uf) and os.path.isfile(os.path.join(run, "log_env.json"))):
                continue  # unfinished run
            u = json.load(open(uf))
            cfg = yaml.safe_load(open(os.path.join(run, ".hydra", "config.yaml")))
            max_rounds = cfg["experiment"]["env"]["max_num_rounds"]
            months, collapsed = survival(run, max_rounds)
            recs.append((u["seed"], months, collapsed, u, max_rounds))
        if not recs:
            continue
        recs.sort(key=lambda r: r[0])
        months = [r[1] for r in recs]
        per_seed = ", ".join(f"s{r[0]}:{r[1]}/{r[4]}" for r in recs)
        wall = statistics.mean(r[3]["wall_time_s"] for r in recs) / 60
        tin = statistics.mean(r[3]["token_in"] for r in recs)
        tout = statistics.mean(r[3]["token_out"] for r in recs)
        # swallowed parse failures; "n/a" for runs made before this was logged
        fb = [r[3].get("fallbacks_total") for r in recs]
        fallbacks = "n/a" if None in fb else f"{statistics.mean(fb):.1f}"
        lines.append(
            f"| {os.path.basename(g)} | {recs[0][3]['model']} | {len(recs)} | {per_seed} | "
            f"{statistics.mean(months):.1f} | {sum(r[2] for r in recs)}/{len(recs)} | "
            f"{wall:.1f} | {tin/1e6:.2f}M / {tout/1e6:.2f}M | {fallbacks} |"
        )
    out = "\n".join(lines)
    print(out)
    if args.md:
        open(args.md, "w").write(out + "\n")


if __name__ == "__main__":
    main()
