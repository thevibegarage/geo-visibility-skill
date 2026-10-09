#!/usr/bin/env python3
"""Simulated skill-activation test: would a model pick this skill from a realistic menu of installed skills?

Claude Code decides which skill to load by reading every skill's name and description. This tool rebuilds that decision as an
experiment: it writes job files that give a fresh model the menu (our skill, a competitor's skills, and a few unrelated ones)
plus a batch of user messages, then scores the answers. It is a SIMULATION: a stand-in model doing the routing, not Claude
Code's own router, and the prompt set is small. Treat the numbers as a regression signal, not a benchmark.

Usage:
    python3 tools/trigger_sim.py prepare --competitors PATH/TO/ANY/PLUGIN/CLONE --out DIR [--label rival-seo]
        writes DIR/jobs/<order>-<n>.md; each job tells a model to write DIR/answers/<order>-<n>.jsonl
    python3 tools/trigger_sim.py score --out DIR [--split test]
        reads the answers and prints per-split results as markdown

The prompts and their dev/test split live in geo-visibility/evals/triggers.json. Tune the skill description with 'dev'
failures only; 'test' is the held-out estimate. Competitor skill text is read from a local clone and never copied into the repo.
Standard library only.
"""
import argparse
import json
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OURS = "geo-visibility:geo-visibility"
BATCH_SIZE = 10
ORDERS = ("A", "B")
# Real skills that sit alongside in many setups. Descriptions are shortened but are the vendors' own words.
DISTRACTORS = {
    "code-review": "Review the current diff, or a PR number/branch/path target, for correctness bugs at the given effort level.",
    "pdf": "Use this skill whenever the user wants to do anything with PDF files: reading or extracting text and tables, "
           "combining, splitting, rotating, watermarking, creating, filling forms, encrypting, OCR. If the user mentions a "
           ".pdf file or asks to produce one, use this skill.",
    "docx": "Use this skill whenever the user wants to create, read, edit, or manipulate Word documents (.docx) or Word "
            "templates (.dotx), including tracked changes, comments, and find-and-replace in Word files.",
}


def frontmatter(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    meta = {}
    if m:
        for line in m.group(1).splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"')
    return meta


def load_prompts(path=None):
    with open(path or os.path.join(ROOT, "geo-visibility", "evals", "triggers.json"), encoding="utf-8") as fh:
        return json.load(fh)["prompts"]


def our_entry():
    meta = frontmatter(os.path.join(ROOT, "geo-visibility", "SKILL.md"))
    return OURS, meta["description"]


def competitor_entries(directory, label=None):
    """Name/description pairs for every skill under <directory>/skills/*/SKILL.md, named <label>:<skill> like Claude Code lists
    them. The label defaults to the folder name; the saved results use the neutral label rival-seo."""
    plugin = label or os.path.basename(os.path.abspath(directory))
    out = []
    skills = os.path.join(directory, "skills")
    for name in sorted(os.listdir(skills)):
        path = os.path.join(skills, name, "SKILL.md")
        if os.path.isfile(path):
            meta = frontmatter(path)
            if meta.get("description") and meta.get("disable-model-invocation", "").lower() != "true":
                out.append((f"{plugin}:{name}", meta["description"]))
    return out


def menu(order, competitors, ours=None, seed=11):
    """The skill list as a router would see it. Order A puts ours first; B puts it last and reverses the rest."""
    ours = ours or our_entry()
    others = list(competitors) + sorted(DISTRACTORS.items())
    random.Random(seed).shuffle(others)
    if order == "A":
        entries = [ours] + others
    elif order == "B":
        entries = list(reversed(others)) + [ours]
    else:
        raise ValueError(order)
    return entries


def menu_text(entries):
    return "\n".join(f"- {name}: {desc}" for name, desc in entries)


def batches(prompts, order, size=BATCH_SIZE):
    ids = [p["id"] for p in prompts]
    random.Random(7 if order == "A" else 13).shuffle(ids)  # mixed on purpose: a batch must not reveal "half of these are about AI"
    by_id = {p["id"]: p for p in prompts}
    return [[by_id[i] for i in ids[k:k + size]] for k in range(0, len(ids), size)]


def job_text(entries, batch, answer_path):
    lines = "\n".join(f'{p["id"]}. {p["prompt"]}' for p in batch)
    return f"""You are the skill router of an AI coding assistant. The assistant has these skills installed. It loads at most one skill per
user message, chosen from the descriptions alone.

## Installed skills

{menu_text(entries)}

## User messages

{lines}

## What to do

For each message, decide independently which single installed skill the assistant should load to handle it, choosing the one whose
description best matches the request. If no installed skill fits, answer none. Judge each message on its own.

Write one JSON object per line to this file, using your file-writing tool, and use no other tool:

{answer_path}

Each line looks like {{"id": 12, "skill": "<exact skill name from the list, or none>"}}. Include every message id above exactly once.
When the file is written, reply with the single word: done
"""


def prepare(competitors_dir, out, label=None):
    prompts = load_prompts()
    comps = competitor_entries(competitors_dir, label)
    os.makedirs(os.path.join(out, "jobs"), exist_ok=True)
    os.makedirs(os.path.join(out, "answers"), exist_ok=True)
    jobs = []
    for order in ORDERS:
        entries = menu(order, comps)
        for n, batch in enumerate(batches(prompts, order), 1):
            answer = os.path.abspath(os.path.join(out, "answers", f"{order}-{n}.jsonl"))
            job = os.path.abspath(os.path.join(out, "jobs", f"{order}-{n}.md"))
            with open(job, "w", encoding="utf-8") as fh:
                fh.write(job_text(entries, batch, answer))
            jobs.append(job)
    with open(os.path.join(out, "menu-A.txt"), "w", encoding="utf-8") as fh:
        fh.write(menu_text(menu("A", comps)) + "\n")
    return jobs, [name for name, _ in comps]


def read_answers(out, prompts, valid_names=None):
    """{order: {id: skill}}; raises ValueError listing anything missing, duplicated or not on the menu.
    With valid_names=None the menu check is skipped (used to re-score saved answers without the competitor's files)."""
    result = {}
    problems = []
    valid = None if valid_names is None else dict({n.lower(): n for n in valid_names}, none="none")  # dict | dict needs Python 3.9
    for order in ORDERS:
        got = {}
        folder = os.path.join(out, "answers")
        for fname in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
            if not fname.startswith(order + "-") or not fname.endswith(".jsonl"):
                continue
            with open(os.path.join(folder, fname), encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                        pid, skill = int(obj["id"]), str(obj["skill"]).strip()
                    except (ValueError, KeyError, TypeError):
                        problems.append(f"{fname}: unreadable line {raw[:60]!r}")
                        continue
                    if pid in got:
                        problems.append(f"order {order}: id {pid} answered twice")
                    canonical = ("none" if skill.lower() == "none" else skill) if valid is None else valid.get(skill.lower())
                    if canonical is None:
                        problems.append(f"order {order}: id {pid} named {skill!r}, which is not on the menu")
                        canonical = "invalid"
                    got[pid] = canonical
        missing = [p["id"] for p in prompts if p["id"] not in got]
        if missing:
            problems.append(f"order {order}: no answer for ids {missing}")
        result[order] = got
    if problems:
        raise ValueError("\n".join(problems))
    return result


def score(prompts, answers):
    """Metrics per split ('dev', 'test', 'all'). 'fire' recall: ours chosen. 'no-fire' false positives: ours chosen."""
    out = {}
    for split in ("dev", "test", "all"):
        subset = [p for p in prompts if split == "all" or p["split"] == split]
        res = {"n": len(subset)}
        for expect in ("fire", "no-fire"):
            group = [p for p in subset if p["expect"] == expect]
            hits = {o: sum(answers[o][p["id"]] == OURS for p in group) for o in ORDERS}
            res[expect] = {"n": len(group), "ours_chosen": hits,
                           "ours_chosen_in_both_orders": sum(all(answers[o][p["id"]] == OURS for o in ORDERS) for p in group),
                           "ours_chosen_in_either_order": sum(any(answers[o][p["id"]] == OURS for o in ORDERS) for p in group)}
        stolen = {}
        for p in subset:
            if p["expect"] == "fire":
                for o in ORDERS:
                    chosen = answers[o][p["id"]]
                    if chosen != OURS:
                        stolen[chosen] = stolen.get(chosen, 0) + 1
        res["fire_missed_to"] = dict(sorted(stolen.items(), key=lambda kv: -kv[1]))
        res["agreement_between_orders"] = sum(answers["A"][p["id"]] == answers["B"][p["id"]] for p in subset)
        out[split] = res
    return out


def pct(a, b):
    return "n/a" if not b else f"{round(100 * a / b)}%"


def to_markdown(metrics, prompts, answers):
    lines = ["| Split | Prompts | Chosen when it should be (A / B / both orders) | Chosen when it should not be (A / B / either order) | Orders agree |",
             "|---|---|---|---|---|"]
    for split in ("dev", "test", "all"):
        m = metrics[split]
        f, nf = m["fire"], m["no-fire"]
        lines.append(f"| {split} | {m['n']} | {f['ours_chosen']['A']}/{f['n']} / {f['ours_chosen']['B']}/{f['n']} / "
                     f"{f['ours_chosen_in_both_orders']}/{f['n']} ({pct(f['ours_chosen_in_both_orders'], f['n'])}) | "
                     f"{nf['ours_chosen']['A']}/{nf['n']} / {nf['ours_chosen']['B']}/{nf['n']} / "
                     f"{nf['ours_chosen_in_either_order']}/{nf['n']} | {m['agreement_between_orders']}/{m['n']} |")
    missed = [(p, answers["A"][p["id"]], answers["B"][p["id"]]) for p in prompts
              if (p["expect"] == "fire" and not all(answers[o][p["id"]] == OURS for o in ORDERS))
              or (p["expect"] == "no-fire" and any(answers[o][p["id"]] == OURS for o in ORDERS))]
    if missed:
        lines += ["", "| Split | Expect | Prompt | Order A chose | Order B chose |", "|---|---|---|---|---|"]
        for p, a, b in missed:
            lines.append(f"| {p['split']} | {p['expect']} | {p['prompt']} | {a} | {b} |")
    else:
        lines += ["", "No misses."]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("prepare", help="write the job files")
    p1.add_argument("--competitors", required=True, help="a local clone of a plugin repo with skills/*/SKILL.md")
    p1.add_argument("--out", required=True)
    p1.add_argument("--label", default="rival-seo", help="name shown for the rival plugin on the menu (default: rival-seo)")
    p2 = sub.add_parser("score", help="score the answers")
    p2.add_argument("--out", required=True)
    p2.add_argument("--competitors", help="local clone used to check skill names on the menu; omit to re-score saved answers")
    p2.add_argument("--label", default="rival-seo")
    a = ap.parse_args(argv)
    if a.cmd == "prepare":
        jobs, names = prepare(a.competitors, a.out, a.label)
        print(f"wrote {len(jobs)} jobs under {a.out}/jobs; menu has {len(names)} competitor skills plus ours and {len(DISTRACTORS)} unrelated ones")
        return 0
    prompts = load_prompts()
    names = None if not a.competitors else [OURS] + [n for n, _ in competitor_entries(a.competitors, a.label)] + list(DISTRACTORS)
    try:
        answers = read_answers(a.out, prompts, names)
    except ValueError as e:
        print("cannot score:\n" + str(e), file=sys.stderr)
        return 1
    print(to_markdown(score(prompts, answers), prompts, answers))
    return 0


if __name__ == "__main__":
    sys.exit(main())
