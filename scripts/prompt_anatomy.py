"""Count the memory lines in every prompt of a run, by phase, round and memory tag.

Usage: python -I scripts/prompt_anatomy.py <run_dir> [--out DIR]

Needs a run made with `+debug_memory_tags=true` (lines carry [event, always] /
[thought] tags). Input is <run_dir>/prompts.json written by simulation/main.py.
Token counts use tiktoken cl100k_base as a proxy (not Claude's tokenizer).
"""
import argparse
import csv
import json
import os
import re
from collections import defaultdict

import tiktoken

ENC = tiktoken.get_encoding("cl100k_base")
TAG = re.compile(r"^\[(\w+)(, always)?\] ")
DATE = re.compile(r"Date: (\d{4}-\d{2}-\d{2})")
BLOCK = re.compile(
    r"Key memories of [^(]+\(format: YYYY-MM-DD: memory\):\n(.*?)\n\n\n", re.S
)
LINE = re.compile(r"^(?:- |\d+\) )(\d{4}-\d{2}-\d{2}): (.*)$")


def ntok(text):
    return len(ENC.encode(text))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or args.run_dir

    prompts = json.load(open(os.path.join(args.run_dir, "prompts.json")))
    # (phase, round, tag) -> [lines, tokens]; plus per (phase, round) prompts
    agg = defaultdict(lambda: [0, 0])
    n_prompts = defaultdict(int)
    prompt_tokens = defaultdict(int)
    first_date = None
    for agent, entries in prompts.items():
        last_date = None
        for entry in entries:
            m = re.match(r"<h3>(.*?)</h3>", entry)
            phase = m.group(1) if m else "unknown"
            entry = entry.replace("<br/>", "\n")
            d = DATE.search(entry)
            if d:
                last_date = d.group(1)
                first_date = first_date or last_date
            block = BLOCK.search(entry)
            if not block:
                continue
            month = int(last_date[5:7]) if last_date else -1
            n_prompts[(phase, month)] += 1
            prompt_tokens[(phase, month)] += ntok(entry)
            # a memory may span several lines (even blank ones); the block ends
            # at the first triple newline. Lines that do not start a new memory
            # belong to the previous one.
            items = []
            for line in block.group(1).split("\n"):
                lm = LINE.match(line)
                if lm:
                    items.append(lm.group(2))
                elif items:
                    items[-1] += "\n" + line
            for text in items:
                t = TAG.match(text)
                tag = "untagged"
                if t:
                    tag = t.group(1) + (",always" if t.group(2) else "")
                    text = text[t.end():]
                agg[(phase, month, tag)][0] += 1
                agg[(phase, month, tag)][1] += ntok(text)

    os.makedirs(out, exist_ok=True)
    rows = sorted(agg)
    with open(os.path.join(out, "anatomy.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["phase", "month", "tag", "memory_lines", "memory_tokens",
                    "prompts_in_phase_month", "avg_lines_per_prompt"])
        for phase, month, tag in rows:
            lines, toks = agg[(phase, month, tag)]
            n = n_prompts[(phase, month)]
            w.writerow([phase, month, tag, lines, toks, n, round(lines / n, 2)])

    md = ["| phase | month | tag | prompts | lines (avg/prompt) | memory tokens |",
          "|---|---|---|---|---|---|"]
    for phase, month, tag in rows:
        lines, toks = agg[(phase, month, tag)]
        n = n_prompts[(phase, month)]
        md.append(f"| {phase} | {month} | {tag} | {n} | {lines} ({lines / n:.1f}) | {toks} |")
    md.append("")
    md.append("| phase | month | prompts | total prompt tokens (cl100k) |")
    md.append("|---|---|---|---|")
    for (phase, month) in sorted(n_prompts):
        md.append(f"| {phase} | {month} | {n_prompts[(phase, month)]} | {prompt_tokens[(phase, month)]} |")
    open(os.path.join(out, "anatomy.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
