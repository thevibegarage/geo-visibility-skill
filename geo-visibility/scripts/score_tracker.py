#!/usr/bin/env python3
"""Roll up an AI-visibility tracker CSV into KPIs (standard library only).

Usage:
    python score_tracker.py tracker.csv --brand "Acme" [--domain acme.com] [--compare previous.csv] [--by-stage]
                            [--config FILE]   # brand and domain default to geo-visibility.json

CSV columns (header required; see assets/visibility-tracker.csv):
    prompt_id,stage,prompt,engine,mode,run,mentioned,cited,position,sentiment,accurate,competitors,cited_domains

Rules:
  * mentioned/cited/accurate accept 1/0, true/false, yes/no, y/n in any case (so Google Sheets and Excel
    TRUE/FALSE exports work). accurate may be blank = not assessed. Any other value is an error.
  * With --domain, a blank `cited` is derived from `cited_domains` (the brand's domain or a subdomain of it).
  * competitors and cited_domains are ';' separated
  * Multiple runs of the same prompt+engine+mode are collapsed by majority vote (ties count as 0).
    Competitors need a strict majority of runs; cited domains need at least half (a discovery list).
  * mode is normalized: blank/search/on/web = "search"; off/no-search/memory = "no-search". Search and
    no-search runs are reported separately, never blended.
  * Engine names are trimmed and case-insensitive ("chatgpt " = "ChatGPT"); Bing Chat / Microsoft Copilot
    are reported as "Copilot" and Google AI Overview(s) as "AI Overviews".
Share of voice = brand mentions / (brand mentions + competitor mentions) across all rows.
Sentiment mix is the share of rows whose (majority) sentiment is positive / neutral / negative / inaccurate.
"""
import argparse
import csv
import os
import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling module, however the script is loaded
import geo_config  # noqa: E402

REQUIRED = ("prompt_id", "engine", "mentioned", "cited")
TRUE = {"1", "true", "yes", "y", "t", "x", "✓", "✔"}
FALSE = {"0", "false", "no", "n", "f"}
ENGINE_ALIASES = {
    "copilot": "Copilot", "bing copilot": "Copilot", "microsoft copilot": "Copilot", "bing chat": "Copilot",
    "ai overview": "AI Overviews", "ai overviews": "AI Overviews", "google ai overview": "AI Overviews",
    "google ai overviews": "AI Overviews", "aio": "AI Overviews",
}
SEARCH_MODES = {"", "search", "on", "search on", "search-on", "web", "web search", "live"}
NO_SEARCH_MODES = {"off", "no-search", "no search", "nosearch", "search off", "search-off", "memory"}
SENTIMENTS = ("positive", "neutral", "negative", "inaccurate")


def load(path):
    # utf-8-sig: Excel's "CSV UTF-8" export starts with a byte-order mark that would otherwise corrupt the first header
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def flag(v):
    v = (v or "").strip().lower()
    return 1 if v in TRUE else (0 if v in FALSE else None)


def norm_engine(e):
    s = " ".join((e or "").split())
    return ENGINE_ALIASES.get(s.casefold(), s)


def norm_mode(m):
    s = " ".join((m or "").lower().replace("_", "-").split())
    if s in SEARCH_MODES:
        return "search"
    if s in NO_SEARCH_MODES:
        return "no-search"
    return s


def norm_sentiment(s):
    s = (s or "").strip().lower()
    for name, prefix in (("positive", "pos"), ("neutral", "neu"), ("negative", "neg"), ("inaccurate", "inacc")):
        if s.startswith(prefix):
            return name
    return "other" if s else None


def check_input(raw, path):
    """Fail loudly on bad input instead of printing an empty or misleading report."""
    if not raw:
        sys.exit(f"ERROR: {path} has a header but no data rows. Add at least one prompt result.")
    missing = [c for c in REQUIRED if c not in raw[0]]
    if missing:
        sys.exit(f"ERROR: {path} is missing required column(s): {', '.join(missing)}. "
                 "See assets/visibility-tracker.csv for the expected header.")
    problems = []
    for i, r in enumerate(raw, start=2):  # line 1 is the header
        if not (r.get("engine") or "").strip():
            problems.append(f"line {i}: engine is empty")
        for col in ("mentioned", "cited", "accurate"):
            v = (r.get(col) or "").strip()
            if v and flag(v) is None:
                problems.append(f"line {i}: {col}={v!r} is not 1/0, true/false or yes/no")
    if problems:
        shown = "\n  ".join(problems[:10]) + (f"\n  ... and {len(problems) - 10} more" if len(problems) > 10 else "")
        sys.exit(f"ERROR: {path} has values that cannot be scored (they would silently count as 0):\n  {shown}")
    bad_pos = sorted({(r.get("position") or "").strip() for r in raw
                      if (r.get("position") or "").strip() and not (r.get("position") or "").strip().isdigit()})
    if bad_pos:
        print(f"WARNING: non-numeric position values ignored: {bad_pos}", file=sys.stderr)


def normalize(raw):
    """Trim and canonicalize engine, mode and ids. Returns new row dicts; the first-seen spelling labels an engine."""
    labels, out = {}, []
    for r in raw:
        r = dict(r)
        eng = norm_engine(r.get("engine"))
        r["engine"] = labels.setdefault(eng.casefold(), eng)
        r["mode"] = norm_mode(r.get("mode"))
        r["prompt_id"] = (r.get("prompt_id") or "").strip()
        out.append(r)
    return out


def _is_domain(d, domain):
    d, domain = d.strip().lower(), domain.strip().lower().lstrip(".")
    return d == domain or d.endswith("." + domain)


def cited_flag(r, domain=None):
    f = flag(r.get("cited"))
    if f is None and domain:
        ds = [d for d in (r.get("cited_domains") or "").split(";") if d.strip()]
        return int(any(_is_domain(d, domain) for d in ds))
    return f


def collapse(rows, domain=None):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["prompt_id"], r["engine"].casefold(), r.get("mode", "search"))].append(r)
    out = []
    for key, rs in groups.items():
        def maj(vals):
            vals = [v for v in vals if v is not None]
            return None if not vals else int(sum(vals) * 2 > len(vals))
        positions = [int(r["position"]) for r in rs if (r.get("position") or "").strip().isdigit()]
        comps = Counter()
        domains = Counter()
        sents = Counter(s for s in (norm_sentiment(r.get("sentiment")) for r in rs) if s)
        for r in rs:
            for c in (r.get("competitors") or "").split(";"):
                if c.strip():
                    comps[c.strip()] += 1
            for d in (r.get("cited_domains") or "").split(";"):
                if d.strip():
                    domains[d.strip().lower()] += 1
        sentiment = None
        if sents:  # most common; ties go to the more negative reading
            order = ("negative", "inaccurate", "other", "neutral", "positive")
            sentiment = sorted(sents, key=lambda s: (-sents[s], order.index(s)))[0]
        out.append({
            "prompt_id": key[0], "engine": rs[0]["engine"], "mode": key[2], "stage": rs[0].get("stage", "") or "",
            "mentioned": maj([flag(r.get("mentioned")) for r in rs]) or 0,
            "cited": maj([cited_flag(r, domain) for r in rs]) or 0,
            "accurate": maj([flag(r.get("accurate")) for r in rs]),
            "position": round(statistics.median(positions)) if positions else None,
            "sentiment": sentiment,
            "competitors": [c for c, n in comps.items() if n * 2 > len(rs)],
            "domains": [d for d, n in domains.items() if n * 2 >= len(rs)],
        })
    return out


def _metrics(rs):
    n = len(rs)
    brand = sum(r["mentioned"] for r in rs)
    comp = sum(len(r["competitors"]) for r in rs)
    pos = [r["position"] for r in rs if r["position"]]
    acc = [r["accurate"] for r in rs if r["accurate"] is not None]
    sent = Counter(r["sentiment"] for r in rs if r["sentiment"])
    total_sent = sum(sent.values())
    return {
        "prompts": n,
        "mention_rate": round(100 * brand / n),
        "citation_rate": round(100 * sum(r["cited"] for r in rs) / n),
        "avg_position": round(statistics.mean(pos), 1) if pos else None,
        "share_of_voice": round(100 * brand / (brand + comp)) if brand + comp else None,
        "accuracy_rate": round(100 * sum(acc) / len(acc)) if acc else None,
        "sentiment": {s: round(100 * sent[s] / total_sent) for s in SENTIMENTS + ("other",) if sent[s]} if total_sent else None,
    }


def rollup(rows):
    """Metrics per (engine, mode) plus an ALL row per mode. Search and no-search runs are never blended."""
    groups = defaultdict(list)
    labels = {}
    for r in rows:
        k = (r["engine"].casefold(), r["mode"])
        labels[k] = r["engine"]
        groups[k].append(r)
        groups[("all", r["mode"])].append(r)
    labels.update({k: "ALL" for k in groups if k[0] == "all"})
    res = {}
    for k, rs in groups.items():
        res[k] = _metrics(rs)
        res[k]["label"], res[k]["mode"] = labels[k], k[1]
    return res


def rollup_by_stage(rows):
    groups = defaultdict(list)
    labels = {}
    for r in rows:
        stage = r["stage"] or "(none)"
        for eng_key, eng_label in ((r["engine"].casefold(), r["engine"]), ("all", "ALL")):
            k = (stage, eng_key, r["mode"])
            labels[k] = eng_label
            groups[k].append(r)
    res = {}
    for k, rs in groups.items():
        res[k] = _metrics(rs)
        res[k]["label"] = labels[k]
    return res


def top_domains(rows, n=15):
    c = Counter(d for r in rows for d in r["domains"])
    return c.most_common(n)


def lost_prompts(rows):
    return sorted({(r["prompt_id"], _label(r), ", ".join(r["competitors"])) for r in rows if not r["mentioned"] and r["competitors"]})


def _label(r_or_m):
    name = r_or_m.get("label") or r_or_m["engine"]
    mode = r_or_m["mode"]
    return name if mode == "search" else f"{name} [{mode}]"


def _order(res):
    return sorted(res, key=lambda k: (res[k]["mode"] != "search", res[k]["label"] != "ALL", res[k]["label"].casefold(), res[k]["mode"]))


def _delta(r, p, k):
    if p is None or r[k] is None or p[k] is None:
        return ""
    d = round(r[k] - p[k], 1)
    return f" ({'+' if d > 0 else ''}{d})"


def fmt(res, prev=None):
    lines = ["| Engine | Prompts | Mention % | Citation % | Avg pos | Share of voice % | Accuracy % |", "|---|---|---|---|---|---|---|"]
    for k in _order(res):
        r, p = res[k], (prev or {}).get(k)
        sov = "-" if r["share_of_voice"] is None else f"{r['share_of_voice']}{_delta(r, p, 'share_of_voice')}"
        lines.append(f"| {_label(r)} | {r['prompts']} | {r['mention_rate']}{_delta(r, p, 'mention_rate')} | "
                     f"{r['citation_rate']}{_delta(r, p, 'citation_rate')} | "
                     f"{r['avg_position'] if r['avg_position'] is not None else '-'} | {sov} | "
                     f"{r['accuracy_rate'] if r['accuracy_rate'] is not None else '-'} |")
    return "\n".join(lines)


def fmt_sentiment(res):
    rows = [k for k in _order(res) if res[k]["sentiment"]]
    if not rows:
        return None
    lines = ["| Engine | Positive % | Neutral % | Negative % | Inaccurate % |", "|---|---|---|---|---|"]
    for k in rows:
        s = res[k]["sentiment"]
        lines.append(f"| {_label(res[k])} | " + " | ".join(str(s.get(x, 0)) for x in SENTIMENTS) + " |")
    return "\n".join(lines)


def fmt_stage(res):
    keys = sorted(res, key=lambda k: (k[0], k[2] != "search", res[k]["label"] != "ALL", res[k]["label"].casefold(), k[2]))
    lines = ["| Stage | Engine | Prompts | Mention % | Citation % | Share of voice % |", "|---|---|---|---|---|---|"]
    for k in keys:
        r = res[k]
        name = r["label"] if k[2] == "search" else f"{r['label']} [{k[2]}]"
        sov = "-" if r["share_of_voice"] is None else r["share_of_voice"]
        lines.append(f"| {k[0]} | {name} | {r['prompts']} | {r['mention_rate']} | {r['citation_rate']} | {sov} |")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--brand", default=None)
    ap.add_argument("--domain", help="brand domain; derives a blank `cited` from cited_domains")
    ap.add_argument("--config", help="settings file (default: ./geo-visibility.json when present); arguments override it")
    ap.add_argument("--compare")
    ap.add_argument("--by-stage", action="store_true", help="also print mention/citation/share of voice per funnel stage")
    a = ap.parse_args(argv)
    try:
        cfg = geo_config.load(a.config)
    except geo_config.ConfigError as e:
        sys.exit(f"ERROR: {e}")
    a.brand = a.brand if a.brand is not None else cfg.get("brand", "")
    a.domain = a.domain or cfg.get("domain")
    raw = load(a.csv)
    check_input(raw, a.csv)
    rows = collapse(normalize(raw), a.domain)
    res = rollup(rows)
    prev, prev_rows = None, None
    if a.compare:
        raw_prev = load(a.compare)
        check_input(raw_prev, a.compare)
        prev_rows = collapse(normalize(raw_prev), a.domain)
        prev = rollup(prev_rows)
    print(f"# AI visibility roll-up{' for ' + a.brand if a.brand else ''}\n")
    print(fmt(res, prev))
    if prev_rows is not None:
        cur_ids, prev_ids = {r["prompt_id"] for r in rows}, {r["prompt_id"] for r in prev_rows}
        if cur_ids != prev_ids:
            print(f"\nWARNING: the prompt sets differ ({len(cur_ids - prev_ids)} new, {len(prev_ids - cur_ids)} missing), "
                  "so the deltas are not like-for-like. Freeze the core set and add new prompts as a separate cohort.")
    sent = fmt_sentiment(res)
    if sent:
        print("\n## Sentiment mix\n")
        print(sent)
    if a.by_stage:
        print("\n## By funnel stage\n")
        print(fmt_stage(rollup_by_stage(rows)))
    print("\n## Top cited domains (earn presence here first)\n")
    for dom, n in top_domains(rows):
        print(f"- {dom}: {n}")
    print("\n## Prompts lost to competitors\n")
    for pid, eng, comps in lost_prompts(rows):
        print(f"- {pid} on {eng}: {comps}")
    print("\nNote: small prompt sets are noisy; treat movement under ~10 points as unconfirmed until it repeats.")


if __name__ == "__main__":
    main()
