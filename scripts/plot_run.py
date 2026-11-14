"""Plot context-window need, runtime and per-month harvest for finished runs.

Usage: python -I scripts/plot_run.py <run_dir> [--out DIR] [--bin 3]
       python -I scripts/plot_run.py --group <group> [--results DIR] [--out DIR] [--bin 3]

Reads calls.json (per-LLM-call token_in/token_out/time/round, written by
simulation/main.py), usage.json and log_env.json. Runs without calls.json (older
runs) fall back to a tiktoken estimate of each chain's text in prompts.json: that
is approximate, drops the per-call split and has no timing, so it is flagged.

Figures -> docs/figures/<readable group>/{context-tokens-per-call,
runtime-progress-and-time,harvest-per-agent-and-pool}.png
(a seed<N>_ prefix is added only when a group holds several runs)
"""
import argparse
import glob
import json
import os
import re
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

CTX_LINES = [4096, 8192, 16384, 32768, 65536]


SCENARIOS = {
    "fish_baseline_concurrent": "fishing-baseline",
    "fish_baseline_concurrent_universalization": "fishing-baseline-universalization",
    "fish_perturbation_outsider": "fishing-outsider",
    "fish_perturbation_no_language": "fishing-no-language",
}
SUFFIXES = {"minmem": "minimal-memory"}


def readable_group(group):
    """ollama-qwen3.5_9b__fish_baseline_concurrent__7mo -> qwen3.5-9b_fishing-baseline_7-months"""
    parts = group.split("__")
    if len(parts) < 2:
        return group
    model = re.sub(r"^ollama-", "", parts[0]).replace("_", "-")
    scenario = SCENARIOS.get(parts[1], parts[1].replace("_", "-"))
    extra = []
    for suffix in parts[2:]:
        m = re.fullmatch(r"(\d+)mo", suffix)
        extra.append(f"{m.group(1)}-months" if m else SUFFIXES.get(suffix, suffix))
    return "_".join([model, scenario, *extra])


def load_calls(run):
    path = os.path.join(run, "calls.json")
    if os.path.isfile(path):
        calls = json.load(open(path))
        for c in calls:
            c["phase"] = c.get("phase") or "?"
        return calls, False
    # fallback: estimate from prompts.json (one entry per chain)
    if not os.path.isfile(os.path.join(run, "prompts.json")):
        return [], True
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    prompts = json.load(open(os.path.join(run, "prompts.json")))
    date_re = re.compile(r"Date: (\d{4}-\d{2})")
    calls = []
    for agent, entries in prompts.items():
        months = {}
        for e in entries:
            m = date_re.search(e)
            phase = re.match(r"<h3>([^:<]+)", e)
            if m:
                months.setdefault(m.group(1), len(months))
            calls.append(
                {
                    "round": months.get(m.group(1)) if m else None,
                    "agent": agent,
                    "phase": phase.group(1) if phase else "?",
                    "token_in": len(enc.encode(e)),
                    "token_out": 0,
                    "start_ms": None,
                    "end_ms": None,
                }
            )
    return calls, True


def plot_context(calls, usage, estimated, out, title):
    by_phase = defaultdict(list)
    for c in calls:
        by_phase[c["phase"]].append(c["token_in"] + c["token_out"])
    rounds = sorted({c["round"] for c in calls if c["round"] is not None})
    max_by_round = [
        max((c["token_in"] + c["token_out"] for c in calls if c["round"] == r), default=0)
        for r in rounds
    ]
    need = max((c["token_in"] + c["token_out"] for c in calls), default=0)

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    phases = sorted(by_phase)
    ax[0].boxplot([by_phase[p] for p in phases], showfliers=True)
    ax[0].set_xticks(range(1, len(phases) + 1), phases)
    ax[0].set_ylabel("tokens per call (in + out)")
    ax[0].set_title("Context per call by phase")
    ax[0].tick_params(axis="x", rotation=30)
    ax[1].plot([r + 1 for r in rounds], max_by_round, marker="o")
    ax[1].set_xticks([r + 1 for r in rounds])
    ax[1].set_xlabel("month")
    ax[1].set_ylabel("max tokens in any call")
    ax[1].set_title("Largest call per month")
    ctx = usage.get("num_ctx")
    for a in ax:
        for v in CTX_LINES:
            if v <= max(need * 1.6, 4096):
                a.axhline(v, color="grey", lw=0.6, ls=":")
                a.text(a.get_xlim()[1], v, f" {v//1024}k", va="center", fontsize=7, color="grey")
        if ctx:
            a.axhline(ctx, color="crimson", lw=1.2, label=f"num_ctx={ctx}")
    if ctx:
        ax[1].legend()
    fig.suptitle(
        f"{title}: smallest window that fits every call = {need} tokens"
        + (" (tiktoken estimate)" if estimated else "")
    )
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return need


def plot_runtime(calls, usage, out, title):
    timed = [c for c in calls if c.get("start_ms") is not None]
    if not timed:
        return None
    t0 = min(c["start_ms"] for c in timed)
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
    xs = sorted(timed, key=lambda c: c["end_ms"])
    ax[0].plot([(c["end_ms"] - t0) / 60000 for c in xs], range(1, len(xs) + 1))
    ax[0].set_xlabel("minutes since first call")
    ax[0].set_ylabel("calls completed")
    ax[0].set_title("Progress")
    per_round = defaultdict(float)
    per_phase = defaultdict(float)
    for c in timed:
        d = (c["end_ms"] - c["start_ms"]) / 1000
        if c["round"] is not None:
            per_round[c["round"]] += d
        per_phase[c["phase"]] += d
    rs = sorted(per_round)
    ax[1].bar([r + 1 for r in rs], [per_round[r] / 60 for r in rs])
    ax[1].set_xticks([r + 1 for r in rs])
    ax[1].set_xlabel("month")
    ax[1].set_ylabel("LLM time (min)")
    ax[1].set_title("Time per month")
    ps = sorted(per_phase)
    ax[2].bar(ps, [per_phase[p] / 60 for p in ps])
    ax[2].set_ylabel("LLM time (min)")
    ax[2].set_title("Time per phase")
    ax[2].tick_params(axis="x", rotation=30)
    wall = usage.get("wall_time_s")
    fig.suptitle(f"{title}: wall time {wall/60:.1f} min" if wall else title)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return wall


def plot_harvest(run, out, title, bin_size):
    rows = json.load(open(os.path.join(run, "log_env.json")))
    harvest = defaultdict(dict)
    pool = {}
    for r in rows:
        if r.get("action") == "harvesting" and r.get("resource_collected") is not None:
            harvest[r["agent_id"]][r["round"]] = r["resource_collected"]
        a = r.get("resource_in_pool_after_harvesting")
        if a is not None:
            pool[r["round"]] = a
    if not harvest:
        return
    rounds = sorted(pool)
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    for agent, h in sorted(harvest.items()):
        ax[0].plot([r + 1 for r in rounds], [h.get(r) for r in rounds], marker="o", label=str(agent))
    ax[0].set_xticks([r + 1 for r in rounds])
    ax[0].set_xlabel("month")
    ax[0].set_ylabel("tons harvested")
    ax[0].set_title("Harvest per agent per month")
    ax[0].legend(fontsize=7)
    ax[1].plot([r + 1 for r in rounds], [pool[r] for r in rounds], marker="o", label="pool after harvest")
    if bin_size > 1:
        edges = range(0, len(rounds), bin_size)
        means = [
            sum(sum(h.get(r, 0) for r in rounds[i : i + bin_size]) for h in harvest.values())
            / len(harvest)
            / len(rounds[i : i + bin_size])
            for i in edges
        ]
        ax[1].bar([i + 1 + (len(rounds[i : i + bin_size]) - 1) / 2 for i in edges], means,
                  width=[0.8 * len(rounds[i : i + bin_size]) for i in edges], alpha=0.3,
                  label=f"mean harvest/agent/month, {bin_size}-month bins")
    ax[1].set_xlabel("month")
    ax[1].set_ylabel("tons")
    ax[1].set_title("Resource pool")
    ax[1].legend(fontsize=7)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def plot_run(run, outdir, bin_size, prefix=""):
    name = os.path.basename(os.path.normpath(run))
    usage = json.load(open(os.path.join(run, "usage.json")))
    title = f"{usage.get('model', '?')} seed {usage.get('seed')}"
    os.makedirs(outdir, exist_ok=True)
    calls, estimated = load_calls(run)
    need = wall = None
    if calls:
        need = plot_context(calls, usage, estimated, os.path.join(outdir, f"{prefix}context-tokens-per-call.png"), title)
        wall = plot_runtime(calls, usage, os.path.join(outdir, f"{prefix}runtime-progress-and-time.png"), title)
    else:
        wall = usage.get("wall_time_s")
        print(f"{name}: no calls.json/prompts.json, skipping context and runtime plots")
    if os.path.isfile(os.path.join(run, "log_env.json")):
        plot_harvest(run, os.path.join(outdir, f"{prefix}harvest-per-agent-and-pool.png"), title, bin_size)
    if calls:
        print(
            f"{name}: context need {need} tokens{' (estimate)' if estimated else ''}, "
            f"wall {'%.1f min' % (wall / 60) if wall else 'n/a'}, "
            f"{len(calls)} calls -> {outdir}"
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", nargs="?")
    ap.add_argument("--group")
    ap.add_argument("--results", default="simulation/results/fishing_v7.0")
    ap.add_argument("--out", default=None)
    ap.add_argument("--bin", type=int, default=3, help="months per bin for the harvest summary")
    args = ap.parse_args()
    if args.run:
        runs = [args.run]
        group = os.path.basename(os.path.dirname(os.path.normpath(args.run)))
    elif args.group:
        group = args.group
        runs = [r for r in sorted(glob.glob(os.path.join(args.results, group, "*")))
                if os.path.isfile(os.path.join(r, "usage.json"))]
    else:
        ap.error("give a run dir or --group")
    outdir = args.out or os.path.join("docs", "figures", readable_group(group))
    for r in runs:
        prefix = ""
        if len(runs) > 1:
            seed = json.load(open(os.path.join(r, "usage.json"))).get("seed")
            prefix = f"seed{seed}_"
        plot_run(r, outdir, args.bin, prefix)


if __name__ == "__main__":
    main()
