#!/usr/bin/env python3
"""Roll up an AI-visibility tracker CSV into KPIs (standard library only).

Usage:
    python score_tracker.py tracker.csv --brand "Acme" [--compare previous.csv]

CSV columns (header required; see assets/visibility-tracker.csv):
    prompt_id,stage,prompt,engine,mode,run,mentioned,cited,position,sentiment,accurate,competitors,cited_domains

Rules:
  * mentioned/cited/accurate are 0/1 (accurate may be blank = not assessed)
  * competitors and cited_domains are ';' separated
  * Multiple runs of the same prompt+engine are collapsed by majority vote (ties count as 0)
Share of voice = brand mentions / (brand mentions + competitor mentions) across all rows.
"""
import argparse
import csv
import statistics
from collections import Counter, defaultdict


def load(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


REQUIRED = ("prompt_id", "engine", "mentioned", "cited")


def check_input(raw, path):
    """Fail loudly on bad input instead of printing an empty or misleading report."""
    import sys
    if not raw:
        sys.exit(f"ERROR: {path} has a header but no data rows. Add at least one prompt result.")
    missing = [c for c in REQUIRED if c not in raw[0]]
    if missing:
        sys.exit(f"ERROR: {path} is missing required column(s): {', '.join(missing)}. "
                 "See assets/visibility-tracker.csv for the expected header.")
    bad = {(r.get(c) or "").strip() for r in raw for c in ("mentioned", "cited")
           if (r.get(c) or "").strip() not in ("0", "1", "", "true", "false", "yes", "no", "y", "n")}
    if bad:
        print(f"WARNING: unrecognized mentioned/cited values treated as 0: {sorted(bad)}. Use 0 or 1.", file=sys.stderr)


def flag(v):
    v = (v or "").strip()
    return 1 if v in ("1", "true", "yes", "y") else (0 if v in ("0", "false", "no", "n") else None)


def collapse(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["prompt_id"], r["engine"], r.get("mode", ""))].append(r)
    out = []
    for key, rs in groups.items():
        def maj(field):
            vals = [flag(r.get(field)) for r in rs if flag(r.get(field)) is not None]
            return None if not vals else int(sum(vals) * 2 > len(vals))
        positions = [int(r["position"]) for r in rs if (r.get("position") or "").strip().isdigit()]
        comps = Counter()
        domains = Counter()
        for r in rs:
            for c in (r.get("competitors") or "").split(";"):
                if c.strip():
                    comps[c.strip()] += 1
            for d in (r.get("cited_domains") or "").split(";"):
                if d.strip():
                    domains[d.strip().lower()] += 1
        out.append({
            "prompt_id": key[0], "engine": key[1], "stage": rs[0].get("stage", ""),
            "mentioned": maj("mentioned") or 0, "cited": maj("cited") or 0,
            "accurate": maj("accurate"),
            "position": round(statistics.median(positions)) if positions else None,
            "competitors": [c for c, n in comps.items() if n * 2 > len(rs)],
            "domains": [d for d, n in domains.items() if n * 2 >= len(rs)],
        })
    return out


def rollup(rows):
    res = {}
    by_engine = defaultdict(list)
    for r in rows:
        by_engine[r["engine"]].append(r)
        by_engine["ALL"].append(r)
    for eng, rs in by_engine.items():
        n = len(rs)
        brand = sum(r["mentioned"] for r in rs)
        comp = sum(len(r["competitors"]) for r in rs)
        pos = [r["position"] for r in rs if r["position"]]
        acc = [r["accurate"] for r in rs if r["accurate"] is not None]
        res[eng] = {
            "prompts": n,
            "mention_rate": round(100 * brand / n),
            "citation_rate": round(100 * sum(r["cited"] for r in rs) / n),
            "avg_position": round(statistics.mean(pos), 1) if pos else None,
            "share_of_voice": round(100 * brand / (brand + comp)) if brand + comp else 0,
            "accuracy_rate": round(100 * sum(acc) / len(acc)) if acc else None,
        }
    return res


def top_domains(rows, n=15):
    c = Counter(d for r in rows for d in r["domains"])
    return c.most_common(n)


def lost_prompts(rows):
    return sorted({(r["prompt_id"], r["engine"], ", ".join(r["competitors"])) for r in rows if not r["mentioned"] and r["competitors"]})


def fmt(res, prev=None):
    lines = ["| Engine | Prompts | Mention % | Citation % | Avg pos | Share of voice % | Accuracy % |", "|---|---|---|---|---|---|---|"]
    for eng in sorted(res, key=lambda e: (e != "ALL", e)):
        r = res[eng]

        def d(k):
            if not prev or eng not in prev or r[k] is None or prev[eng][k] is None:
                return ""
            delta = round(r[k] - prev[eng][k], 1)
            return f" ({'+' if delta > 0 else ''}{delta})"

        lines.append(f"| {eng} | {r['prompts']} | {r['mention_rate']}{d('mention_rate')} | {r['citation_rate']}{d('citation_rate')} | "
                     f"{r['avg_position'] if r['avg_position'] is not None else '-'} | {r['share_of_voice']}{d('share_of_voice')} | "
                     f"{r['accuracy_rate'] if r['accuracy_rate'] is not None else '-'} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--brand", default="")
    ap.add_argument("--compare")
    a = ap.parse_args()
    raw = load(a.csv)
    check_input(raw, a.csv)
    rows = collapse(raw)
    res = rollup(rows)
    prev = None
    if a.compare:
        raw_prev = load(a.compare)
        check_input(raw_prev, a.compare)
        prev = rollup(collapse(raw_prev))
    print(f"# AI visibility roll-up{' for ' + a.brand if a.brand else ''}\n")
    print(fmt(res, prev))
    print("\n## Top cited domains (earn presence here first)\n")
    for dom, n in top_domains(rows):
        print(f"- {dom}: {n}")
    print("\n## Prompts lost to competitors\n")
    for pid, eng, comps in lost_prompts(rows):
        print(f"- {pid} on {eng}: {comps}")
    print("\nNote: small prompt sets are noisy; treat movement under ~10 points as unconfirmed until it repeats.")


if __name__ == "__main__":
    main()
