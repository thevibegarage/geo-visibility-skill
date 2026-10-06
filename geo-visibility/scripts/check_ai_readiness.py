#!/usr/bin/env python3
"""AI-search technical readiness check (standard library only).

Usage:
    python check_ai_readiness.py example.com [--paths /pricing /about] [--json out.json]

Checks:
  * robots.txt rules for AI crawlers (search, user-fetch, training groups)
  * WAF/CDN behavior: fetches the homepage with different crawler User-Agents and compares status
  * Render-by-agent: fetches the homepage and each --paths URL as a browser, a listed crawler and
    unlisted user-fetch agents, and compares word count, title, H1 and JSON-LD. Many sites serve
    crawlers different HTML from a default fetch, so a default fetch alone can wrongly report an
    empty shell (or hide that unlisted agents get one).
  * Soft 404: nonexistent URLs must return 404/410, not 200 with the homepage
  * Sitemap lastmod honesty: warns when many entries share one date or are stamped today
  * llms.txt, sitemap(s)
  * Homepage: noindex, canonical, title, meta description, h1 count, JSON-LD types,
    visible text in the raw HTML (proxy for "readable without JavaScript")
Crawler names change. Treat the AGENTS table as a starting point and verify against vendor docs.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

def _bot_ua(name, version="1.0", url=None):
    # Realistic string: Mozilla prefix, "compatible;", version and an info URL or contact, like real bots.
    # Exact strings change; verify against each vendor's current documentation.
    return f"Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; {name}/{version}; +{url or 'https://example.com/bot'})"


AGENTS = {
    # group: {token used in robots.txt: user-agent string sent for the probes}
    "search_and_user_fetch": {
        "OAI-SearchBot": _bot_ua("OAI-SearchBot", url="https://openai.com/searchbot"),
        "ChatGPT-User": _bot_ua("ChatGPT-User", url="https://openai.com/bot"),
        "Claude-SearchBot": _bot_ua("Claude-SearchBot", url="Claude-SearchBot@anthropic.com"),
        "Claude-User": _bot_ua("Claude-User", url="Claude-User@anthropic.com"),
        "PerplexityBot": _bot_ua("PerplexityBot", url="https://perplexity.ai/perplexitybot"),
        "Perplexity-User": _bot_ua("Perplexity-User", url="https://perplexity.ai/perplexity-user"),
        "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Bingbot": "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    },
    "training": {
        "GPTBot": _bot_ua("GPTBot", "1.1", "https://openai.com/gptbot"),
        "ClaudeBot": _bot_ua("ClaudeBot", url="claudebot@anthropic.com"),
        "Google-Extended": "Google-Extended",
        "CCBot": "CCBot/2.0 (https://commoncrawl.org/faq/)",
    },
}
# Agent classes for the render-by-agent comparison. A site that detects crawlers by user agent
# may serve listed crawlers full HTML while an unlisted user-fetch agent gets the SPA shell.
RENDER_AGENTS = {
    "browser": None,  # filled below once BROWSER_UA exists
    "listed crawler (GPTBot)": AGENTS["training"]["GPTBot"],
    "user-fetch (Claude-User)": AGENTS["search_and_user_fetch"]["Claude-User"],
    "user-fetch (ChatGPT-User)": AGENTS["search_and_user_fetch"]["ChatGPT-User"],
}
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
TIMEOUT = 15
RENDER_AGENTS["browser"] = BROWSER_UA


def fetch(url, ua=BROWSER_UA, max_bytes=2_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(max_bytes)
            return r.status, dict(r.headers), body.decode("utf-8", errors="replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), "", url
    except Exception as e:  # network, DNS, TLS
        return 0, {}, f"ERROR: {e}", url


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta = {}
        self.canonical = None
        self.h1 = 0
        self.h2 = 0
        self.jsonld = []
        self._in_title = False
        self._skip = 0
        self._in_jsonld = False
        self._buf = []
        self.text = []
        self.script_count = 0
        self.h1_text = ""
        self._in_h1 = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta" and a.get("name"):
            self.meta[a["name"].lower()] = a.get("content", "")
        elif tag == "link" and (a.get("rel") or "").lower() == "canonical":
            self.canonical = a.get("href")
        elif tag == "h1":
            self.h1 += 1
            self._in_h1 = True
        elif tag == "h2":
            self.h2 += 1
        elif tag == "script":
            self.script_count += 1
            if (a.get("type") or "").lower() == "application/ld+json":
                self._in_jsonld = True
                self._buf = []
            else:
                self._skip += 1
        elif tag in ("style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag == "h1":
            self._in_h1 = False
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            if self._in_jsonld:
                self._in_jsonld = False
                self.jsonld.append("".join(self._buf))
            elif self._skip:
                self._skip -= 1
        elif tag in ("style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._in_h1 and len(self.h1_text) < 200:
            self.h1_text += data.strip() + " "
        if self._in_title:
            self.title += data
        elif self._in_jsonld:
            self._buf.append(data)
        elif not self._skip and data.strip():
            self.text.append(data.strip())


def jsonld_types(blocks):
    types, errors = set(), 0

    def walk(o):
        if isinstance(o, dict):
            t = o.get("@type")
            if isinstance(t, list):
                types.update(map(str, t))
            elif t:
                types.add(str(t))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for b in blocks:
        try:
            walk(json.loads(b))
        except Exception:
            errors += 1
    return sorted(types), errors


def profile(url, ua):
    """Fetch url as ua and summarise what an agent that does not run JavaScript would see."""
    c, h, body, final = fetch(url, ua=ua)
    pp = PageParser()
    try:
        pp.feed(body)
    except Exception:
        pass
    types, _ = jsonld_types(pp.jsonld)
    return {"code": c, "words": len(" ".join(pp.text).split()), "title": pp.title.strip(),
            "h1": pp.h1_text.strip(), "types": types, "canonical": pp.canonical}


def render_by_agent(url):
    """Return (status, detail, fix) comparing browser, listed crawler and unlisted user-fetch agents."""
    prof = {name: profile(url, ua) for name, ua in RENDER_AGENTS.items()}
    if any(p["code"] == 0 for p in prof.values()):
        return "warn", "request error for at least one agent", ""
    summary = "; ".join(f"{n}: HTTP {p['code']}, {p['words']} words, h1 {'yes' if p['h1'] else 'no'}, schema {','.join(p['types']) or 'none'}"
                        for n, p in prof.items())
    full = {n: p for n, p in prof.items() if p["words"] >= 150}
    shell = {n: p for n, p in prof.items() if p["words"] < 150}
    if not full:
        return ("fail", "every agent sees under 150 words (an empty shell for everyone). " + summary,
                "Server-render or statically render this page. Test: curl -s <url> shows its own H1 and 300+ words.")
    if not shell:
        titles = {p["title"] for p in prof.values()}
        if len(titles) > 1:
            return "warn", "enough text for all agents but titles differ by agent. " + summary, "Check what each agent is served."
        return "pass", "all agents see full content. " + summary, ""
    # mixed: some agents get content, some get a shell
    shell_user_fetch = [n for n in shell if n.startswith("user-fetch")]
    if "browser" in shell and not shell_user_fetch:
        return ("pass", "listed crawlers and user-fetch agents get full content; a default browser fetch gets the "
                "client-rendered shell (dynamic rendering by user agent). " + summary,
                "Fine for these agents. Make sure the allowlist covers every current AI search and user-fetch agent, and that Google and Bing see the same content.")
    return ("fail", "user-agent routing gap: " + ", ".join(shell) + " get a shell while " + ", ".join(full) +
            " get content. " + summary,
            "Add the missing agents to the crawler allowlist, or server-render for everyone. Test each agent with curl -A.")


def soft_404(base):
    """A nonexistent URL must return 404/410 to crawlers. Returns [(agent, url, code, words)].
    Probes as a listed crawler and as a user-fetch agent. A browser 200 is expected for single-page
    apps and is reported as info only, because what matters for citations is what agents get."""
    import random
    import string
    tag = "".join(random.choices(string.ascii_lowercase, k=10))
    pth = f"/geo-audit-missing-{tag}"
    out = []
    for name, ua in RENDER_AGENTS.items():
        c, _, body, _ = fetch(base + pth, ua=ua)
        pp = PageParser()
        try:
            pp.feed(body)
        except Exception:
            pass
        out.append((name, base + pth, c, len(" ".join(pp.text).split())))
    return out


def sitemap_lastmod(body):
    """Warn when many lastmod values are identical or stamped today (a sign they are generated, not real)."""
    import datetime
    from collections import Counter
    vals = re.findall(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", body)
    if len(vals) < 10:
        return None
    days = [v[:10] for v in vals]
    common, n = Counter(days).most_common(1)[0]
    today = datetime.date.today().isoformat()
    n_today = sum(1 for d in days if d == today)
    return {"total": len(vals), "most_common": common, "most_common_n": n, "today_n": n_today}


def check(domain, paths):
    raw = domain if domain.startswith("http") else f"https://{domain}"
    parsed = urlparse(raw)
    # Always test the site root: robots.txt, sitemap and llms.txt live there, even if the user passed a deep URL.
    base = f"{parsed.scheme}://{parsed.netloc}"
    res = {"domain": base, "findings": [], "scores": {}, "unreachable": False}

    def add(area, check_name, status, detail, fix=""):
        res["findings"].append(
            {"area": area, "check": check_name, "status": status, "detail": detail, "fix": fix}
        )

    # --- reachability gate: never report fake findings when the network call itself failed ---
    code0, hdr0, html0, final_url = fetch(base + "/")
    if code0 == 0:
        res["unreachable"] = True
        res["error"] = html0.replace("ERROR: ", "")
        return res

    # --- robots.txt ---
    code, _, robots_txt, _ = fetch(base + "/robots.txt")
    rp = urllib.robotparser.RobotFileParser()
    sitemaps = []
    if code == 200:
        rp.parse(robots_txt.splitlines())
        sitemaps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots_txt)
        add("access", "robots.txt present", "pass", f"HTTP 200, {len(robots_txt)} bytes")
    elif code == 0:
        rp.parse([])
        add("access", "robots.txt present", "info", f"could not fetch ({robots_txt[:80]}); rules below assume allow-all, unverified")
    else:
        rp.parse([])
        add("access", "robots.txt present", "warn", f"HTTP {code}; crawlers treat a 404 as allow-all",
            "Publish a robots.txt (see assets/robots-ai-template.txt) and reference your sitemap.")
    test_urls = [base + "/"] + [urljoin(base + "/", p.lstrip("/")) for p in paths]
    for group, agents in AGENTS.items():
        for token in agents:
            blocked = [u for u in test_urls if not rp.can_fetch(token, u)]
            if group == "search_and_user_fetch":
                status = "fail" if blocked else "pass"
                fix = f"Allow {token} in robots.txt if you want AI citations." if blocked else ""
            else:
                status = "info"
                fix = ""
            detail = f"blocked on {len(blocked)}/{len(test_urls)} tested URLs" if blocked else "allowed"
            add("access", f"robots: {token} ({group})", status, detail, fix)

    # --- WAF / CDN probe ---
    add("access", "homepage reachable (browser UA)", "pass" if code0 == 200 else "fail",
        f"HTTP {code0}, final URL {final_url}", "Fix server errors/redirect loops." if code0 != 200 else "")
    for token, ua in AGENTS["search_and_user_fetch"].items():
        c, _, _, _ = fetch(base + "/", ua=ua)
        if c in (401, 403, 429, 503) and code0 == 200:
            add("access", f"WAF probe: {token}", "fail",
                f"HTTP {c} vs 200 for browser UA (UA-string probe only; real bots also use IP ranges)",
                "Check CDN/WAF bot rules and allowlist verified AI agents.")
        elif c == 0:
            add("access", f"WAF probe: {token}", "warn", "request error")
        else:
            add("access", f"WAF probe: {token}", "pass", f"HTTP {c}")

    # --- llms.txt ---
    c, _, body, _ = fetch(base + "/llms.txt")
    if c == 200 and body.strip() and "<html" not in body[:300].lower():
        add("discovery", "llms.txt", "pass", f"present, {len(body.splitlines())} lines")
    else:
        add("discovery", "llms.txt", "info", f"not found (HTTP {c})",
            "Optional. Add after basics (assets/llms-txt-template.md). No proven ranking effect.")

    # --- sitemap ---
    sm_urls = sitemaps or [base + "/sitemap.xml"]
    found_sm = False
    for sm in sm_urls[:3]:
        c, _, body, _ = fetch(sm)
        if c == 200 and ("<urlset" in body or "<sitemapindex" in body):
            n = len(re.findall(r"<loc>", body))
            add("discovery", f"sitemap {sm}", "pass", f"{n} <loc> entries")
            lm = sitemap_lastmod(body)
            if lm is None:
                add("discovery", "sitemap lastmod honesty", "info", "fewer than 10 lastmod values; not assessed")
            elif lm["today_n"] / lm["total"] > 0.1 or lm["most_common_n"] / lm["total"] > 0.3:
                add("discovery", "sitemap lastmod honesty", "warn",
                    f"{lm['today_n']}/{lm['total']} stamped today; {lm['most_common_n']}/{lm['total']} share {lm['most_common']}. "
                    "Looks generated or bulk-updated rather than real edit dates.",
                    "Emit each page's real updated date, or omit lastmod.")
            else:
                add("discovery", "sitemap lastmod honesty", "pass", f"{lm['total']} values, no suspicious clustering")
            found_sm = True
            break
    if not found_sm:
        add("discovery", "sitemap", "fail", "no valid sitemap found", "Publish sitemap.xml and reference it in robots.txt.")

    # --- homepage content ---
    p = PageParser()
    try:
        p.feed(html0)
    except Exception:
        pass
    text = " ".join(p.text)
    words = len(text.split())
    add("render", "visible text in raw HTML", "pass" if words >= 150 else ("warn" if words >= 50 else "fail"),
        f"{words} words without running JavaScript, {p.script_count} script tags",
        "Server-render or statically render key copy." if words < 150 else "")
    robots_meta = p.meta.get("robots", "").lower()
    xrt = hdr0.get("X-Robots-Tag", hdr0.get("x-robots-tag", "")).lower()
    noindex = "noindex" in robots_meta or "noindex" in xrt
    add("indexing", "noindex", "fail" if noindex else "pass", robots_meta or xrt or "none",
        "Remove noindex on pages meant to rank/be cited." if noindex else "")
    add("indexing", "canonical", "pass" if p.canonical else "warn", p.canonical or "missing", "Add a canonical tag." if not p.canonical else "")
    add("onpage", "title", "pass" if 10 <= len(p.title.strip()) <= 70 else "warn", p.title.strip()[:90] or "missing")
    desc = p.meta.get("description", "")
    add("onpage", "meta description", "pass" if desc else "warn", desc[:120] or "missing")
    add("onpage", "single h1", "pass" if p.h1 == 1 else "warn", f"{p.h1} h1, {p.h2} h2")
    types, errs = jsonld_types(p.jsonld)
    add("schema", "JSON-LD present", "pass" if types else "fail", ", ".join(types) or "none",
        "Add Organization/WebSite JSON-LD (assets/schema-templates.md)." if not types else "")
    if errs:
        add("schema", "JSON-LD parse errors", "fail", f"{errs} block(s) invalid JSON", "Fix JSON syntax.")
    add("schema", "Organization schema", "pass" if "Organization" in types or "LocalBusiness" in types else "warn",
        "found" if "Organization" in types or "LocalBusiness" in types else "missing on homepage")

    # --- render by agent: homepage plus each --paths URL ---
    if not paths:
        add("render", "render by agent: detail pages", "info",
            "no --paths given, so only the homepage was compared across agents",
            "Re-run with --paths /a-product-page /a-blog-post /pricing (3-5 representative detail URLs).")
    for pth in ["/"] + list(paths):
        u = urljoin(base + "/", pth.lstrip("/"))
        st, detail, fix = render_by_agent(u)
        add("render", f"render by agent: {pth}", st, detail, fix)

    # --- soft 404 ---
    for name, u, c, w in soft_404(base):
        if c in (404, 410):
            add("indexing", f"soft 404 ({name})", "pass", f"{u} -> HTTP {c}")
        elif name == "browser":
            add("indexing", f"soft 404 ({name})", "info",
                f"{u} -> HTTP {c}. Common for single-page apps; people see the app's own not-found view.")
        elif c == 200:
            add("indexing", f"soft 404 ({name})", "fail",
                f"{u} -> HTTP 200 with {w} words (nonexistent URL served to this agent as a page)",
                "Return a real 404 (and noindex) to crawlers for unknown URLs. Test with curl -A for each agent class.")
        else:
            add("indexing", f"soft 404 ({name})", "warn", f"{u} -> HTTP {c}")

    # --- score ---
    weights = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
    scored = [f for f in res["findings"] if f["status"] in weights]
    res["scores"]["technical_readiness_pct"] = round(100 * sum(weights[f["status"]] for f in scored) / max(1, len(scored)))
    res["scores"]["fail_count"] = sum(1 for f in scored if f["status"] == "fail")
    return res


def to_markdown(res):
    if res.get("unreachable"):
        return (f"# AI readiness: {res['domain']}\n\n**UNREACHABLE from this environment**: {res.get('error')}\n\n"
                "No findings were produced and no score was computed. This is a network problem in the place the script "
                "ran (sandbox allowlist, DNS, TLS, or the site being down), not evidence about the site. "
                "Re-run from a machine with open internet, or use WebFetch on the homepage, /robots.txt, /sitemap.xml "
                "and /llms.txt and review manually.")
    out = [f"# AI readiness: {res['domain']}", "",
           f"Technical readiness: **{res['scores']['technical_readiness_pct']}%** ({res['scores']['fail_count']} failures)", "",
           "| Area | Check | Status | Detail | Fix |", "|---|---|---|---|---|"]
    for f in res["findings"]:
        out.append(f"| {f['area']} | {f['check']} | {f['status']} | {f['detail']} | {f['fix']} |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--paths", nargs="*", default=[])
    ap.add_argument("--json")
    a = ap.parse_args()
    res = check(a.domain, a.paths)
    print(to_markdown(res))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(res, fh, indent=2)
    return 2 if res.get("unreachable") else 0


if __name__ == "__main__":
    sys.exit(main())
