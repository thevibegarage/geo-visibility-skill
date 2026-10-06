#!/usr/bin/env python3
"""AI-search technical readiness check (standard library only).

Usage:
    python check_ai_readiness.py example.com [--paths /pricing /about] [--json out.json]
                                 [--indexnow-key KEY] [--fail-on {none,fail}]

Checks:
  * robots.txt rules for AI and search agents (search, user-fetch, training groups), evaluated
    with a small RFC 9309 matcher: wildcards (* and $), longest-match wins, a named group does not
    inherit the "*" group
  * WAF/CDN behavior: fetches the homepage with different crawler User-Agents and compares status
  * Render-by-agent: fetches the homepage and each --paths URL as a browser, a listed crawler,
    unlisted user-fetch agents, Googlebot and Bingbot, and compares word count, title, H1 and
    JSON-LD. Many sites serve crawlers different HTML from a default fetch, so a default fetch
    alone can wrongly report an empty shell (or hide that unlisted agents get one).
  * Soft 404: nonexistent URLs must return 404/410, not 200 with the homepage
  * Sitemap(s): gzip and sitemap indexes, lastmod honesty, --paths present in the sitemap
  * llms.txt
  * Homepage: noindex (meta robots/googlebot/bingbot and X-Robots-Tag), snippet and archive
    controls that limit AI quoting (nosnippet, max-snippet:0, noarchive, nocache), canonical,
    title, meta description, h1 count, JSON-LD types, visible text in the raw HTML (proxy for
    "readable without JavaScript")
  * Bing/Google webmaster verification hints and, with --indexnow-key, the IndexNow key file

The score weights each check once: per-agent rows (robots, WAF, soft 404) collapse to the worst
row in their group, so a wall of trivial passes cannot hide a failure.

Crawler names change. Treat the AGENTS table as a starting point and verify against vendor docs.
Exit codes: 0 ok, 1 failures found (with --fail-on fail), 2 unreachable, 3 homepage returned an
HTTP error (checks stop: there is no content to assess).
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
import zlib
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


def _bot_ua(name, version="1.0", url=None):
    # Realistic string: Mozilla prefix, "compatible;", version and an info URL or contact, like real bots.
    # Exact strings change; verify against each vendor's current documentation.
    return f"Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; {name}/{version}; +{url or 'https://example.com/bot'})"


AGENTS = {
    # group: {token used in robots.txt: user-agent string sent for the probes}
    # Blocked in robots.txt = a failure for this group: these agents decide whether you can be cited.
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
    # Other assistants and search surfaces. Reported as info: allowing or blocking them is a business choice.
    "other_ai": {
        "Applebot": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/13.1.1 Safari/605.1.15 (Applebot/0.1; +http://www.apple.com/go/applebot)",
        "Amazonbot": "Mozilla/5.0 AppleWebKit/600.2.5 (KHTML, like Gecko) Version/8.0.2 Safari/600.2.5 "
                     "(Amazonbot/0.1; +https://developer.amazon.com/support/amazonbot)",
        "meta-externalagent": "meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)",
        "meta-externalfetcher": "meta-externalfetcher/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)",
        "MistralAI-User": _bot_ua("MistralAI-User", url="https://docs.mistral.ai/robots"),
        "DuckAssistBot": _bot_ua("DuckAssistBot", "1.2", "http://duckduckgo.com/duckassistbot.html"),
    },
    "training": {
        "GPTBot": _bot_ua("GPTBot", "1.1", "https://openai.com/gptbot"),
        "ClaudeBot": _bot_ua("ClaudeBot", url="claudebot@anthropic.com"),
        "Google-Extended": "Google-Extended",  # robots.txt token only; never sent as a user agent
        "Applebot-Extended": "Applebot-Extended",  # robots.txt token only
        "CCBot": "CCBot/2.0 (https://commoncrawl.org/faq/)",
        "Bytespider": "Mozilla/5.0 (Linux; Android 5.0) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Mobile Safari/537.36 (compatible; Bytespider; spider-feedback@bytedance.com)",
    },
}
# Classic search crawlers. Verified-bot WAFs reject spoofed copies of these user agents, so a 403 from a
# UA-string probe is weak evidence. Googlebot and Bingbot also execute JavaScript, so a thin raw-HTML
# page is not by itself a rendering failure for them.
SEARCH_ENGINES = ("Googlebot", "Bingbot")

BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
# Agent classes for the render-by-agent comparison. A site that detects crawlers by user agent
# may serve listed crawlers full HTML while an unlisted user-fetch agent gets the SPA shell.
RENDER_AGENTS = {
    "browser": BROWSER_UA,
    "listed crawler (GPTBot)": AGENTS["training"]["GPTBot"],
    "user-fetch (Claude-User)": AGENTS["search_and_user_fetch"]["Claude-User"],
    "user-fetch (ChatGPT-User)": AGENTS["search_and_user_fetch"]["ChatGPT-User"],
    "search crawler (Googlebot)": AGENTS["search_and_user_fetch"]["Googlebot"],
    "search crawler (Bingbot)": AGENTS["search_and_user_fetch"]["Bingbot"],
}
TIMEOUT = 15
SHELL_WORDS = 150  # below this a page is "thin"; see render_by_agent for how short real pages are handled
SITEMAP_MAX = 50_000_000  # sitemaps may be 50 MB uncompressed
SITEMAP_SAMPLE = 5  # child sitemaps fetched from a sitemap index


def kind(agent_name):
    if agent_name.startswith("user-fetch"):
        return "user-fetch"
    if agent_name.startswith("search crawler"):
        return "search"
    if agent_name.startswith("listed crawler"):
        return "crawler"
    return "browser"


# ---------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------

def _decode(raw):
    """Decode a response body; transparently gunzip (sitemap.xml.gz), tolerating truncated streams."""
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw)
        except zlib.error:
            pass
    return raw.decode("utf-8-sig", errors="replace")  # utf-8-sig drops a byte-order mark (robots.txt files often have one)


def _headers(msg):
    out = {}
    for k, v in (msg.items() if msg else []):
        out[k] = f"{out[k]}, {v}" if k in out else v
    return out


def fetch(url, ua=BROWSER_UA, max_bytes=2_000_000):
    """Return (status, headers, body, final_url). status 0 means a network/DNS/TLS error (body is the error)."""
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = _decode(r.read(max_bytes))
            return r.status, _headers(r.headers), body, r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, _headers(e.headers), "", url
    except Exception as e:  # network, DNS, TLS
        return 0, {}, f"ERROR: {e}", url


# ---------------------------------------------------------------------------------------------
# robots.txt (RFC 9309 semantics, as implemented by Google and Bing)
# ---------------------------------------------------------------------------------------------

class Robots:
    """Minimal robots.txt evaluator.

    * Groups are keyed by user-agent product token (case-insensitive, exact). A crawler uses the groups
      naming it; only if none do does it fall back to the "*" group. A named group does NOT inherit "*".
    * Rule paths support "*" and a trailing "$". The longest matching rule wins; on a tie Allow wins.
    * An empty Disallow means allow everything.
    """

    def __init__(self, text=""):
        self.groups = []  # list of (set of lowercase agents, [(allow, pattern)])
        state = None
        for line in text.lstrip("\ufeff").splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            field, value = line.split(":", 1)
            field, value = field.strip().lower(), value.strip()
            if field == "user-agent":
                if state != "agents":
                    self.groups.append((set(), []))
                self.groups[-1][0].add(value.lower())
                state = "agents"
            elif field in ("allow", "disallow") and self.groups:
                state = "rules"
                if value:
                    self.groups[-1][1].append((field == "allow", value))

    def _rules(self, token):
        t = token.lower()
        named = [rules for agents, rules in self.groups if t in agents]
        if not named:
            named = [rules for agents, rules in self.groups if "*" in agents]
        return [r for rules in named for r in rules]

    @staticmethod
    def _matches(pattern, path):
        end = pattern.endswith("$")
        core = pattern[:-1] if end else pattern
        rx = re.escape(core).replace(r"\*", ".*") + ("$" if end else "")
        return re.match(rx, path) is not None

    def can_fetch(self, token, url):
        u = urlparse(url)
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        best = None  # (pattern length, allow)
        for allow, pattern in self._rules(token):
            if self._matches(pattern, path):
                n = len(pattern)
                if best is None or n > best[0] or (n == best[0] and allow and not best[1]):
                    best = (n, allow)
        return True if best is None else best[1]


# ---------------------------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------------------------

_CJK = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\u0e00-\u0e7f]")


def count_words(text):
    """Word count that also works for scripts written without spaces (Chinese, Japanese, Korean, Thai).

    Whitespace tokens are counted for other scripts; those scripts count roughly one word per two characters.
    """
    cjk = len(_CJK.findall(text))
    return len(_CJK.sub(" ", text).split()) + (cjk + 1) // 2


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
            self.meta[a["name"].lower()] = a.get("content") or ""
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


def parse_page(body):
    pp = PageParser()
    try:
        pp.feed(body)
    except Exception:
        pass
    return pp


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


# schema.org subtypes of Organization/LocalBusiness whose names do not end in "Organization" or "Business".
# Other LocalBusiness subtypes (Dentist, Restaurant...) are not listed: the check stays conservative and
# asks for an Organization or LocalBusiness declaration alongside them.
_ORG_TYPES = {"Organization", "LocalBusiness", "Corporation", "NGO", "Airline", "Consortium", "Library",
              "PerformingGroup", "SportsTeam", "WorkersUnion", "ProfessionalService"}


def is_organization_type(t):
    """True for Organization and its subtypes (EducationalOrganization, Corporation, NGO, LocalBusiness...)."""
    t = t.rsplit("/", 1)[-1]  # tolerate full URLs such as https://schema.org/Organization
    return t in _ORG_TYPES or t.endswith("Organization") or t.endswith("Business")


_EMPTY_MOUNT = re.compile(r"""<div[^>]+id=["'](?:root|app|__next|__nuxt)["'][^>]*>\s*</div>""", re.I)


def profile(url, ua):
    """Fetch url as ua and summarise what an agent that does not run JavaScript would see."""
    c, h, body, final = fetch(url, ua=ua)
    pp = parse_page(body)
    types, _ = jsonld_types(pp.jsonld)
    return {"code": c, "words": count_words(" ".join(pp.text)), "title": pp.title.strip(),
            "h1": pp.h1_text.strip(), "types": types, "canonical": pp.canonical,
            "mount": bool(_EMPTY_MOUNT.search(body))}


# ---------------------------------------------------------------------------------------------
# Render by agent
# ---------------------------------------------------------------------------------------------

_RANK = {"pass": 0, "warn": 1, "fail": 2}


def _worst(a, b):
    return a if _RANK[a] >= _RANK[b] else b


def render_by_agent(url):
    """Return (status, detail, fix) comparing browser, listed crawler, unlisted user-fetch agents, Googlebot, Bingbot."""
    prof = {name: profile(url, ua) for name, ua in RENDER_AGENTS.items()}
    if any(p["code"] == 0 for p in prof.values()):
        return "warn", "request error for at least one agent", ""
    summary = "; ".join(f"{n}: HTTP {p['code']}, {p['words']} words, h1 {'yes' if p['h1'] else 'no'}, schema {','.join(p['types']) or 'none'}"
                        for n, p in prof.items())
    if not 200 <= prof["browser"]["code"] < 300:
        return ("warn", f"browser fetch returned HTTP {prof['browser']['code']}, so agents cannot be compared. " + summary,
                "Fix the page, or check whether a WAF is challenging this check.")

    status, details, fixes = "pass", [], []

    def note(st, detail, fix=""):
        nonlocal status
        status = _worst(status, st)
        details.append(detail)
        if fix and fix not in fixes:
            fixes.append(fix)

    # 1. agents that were refused outright (HTTP error) are a block, not a "shell"
    blocked = {n: p for n, p in prof.items() if n != "browser" and p["code"] >= 400}
    ai_blocked = [n for n in blocked if kind(n) != "search"]
    search_blocked = [n for n in blocked if kind(n) == "search"]
    if ai_blocked:
        note("fail", "refused (HTTP " + ", ".join(str(blocked[n]["code"]) for n in ai_blocked) + ") for " + ", ".join(ai_blocked)
             + " while the browser fetch succeeded",
             "Check CDN/WAF bot rules and the crawler allowlist; see the WAF probe rows.")
    if search_blocked:
        note("warn", ", ".join(search_blocked) + " got an HTTP error. A WAF that verifies bots by IP rejects spoofed user agents, "
             "so this is weak evidence",
             "Confirm with Search Console URL Inspection (Google) and Bing Webmaster Tools URL Inspection (Bing).")

    # 2. does non-JavaScript content reach the browser, listed crawler and user-fetch agents?
    ok = {n: p for n, p in prof.items() if kind(n) != "search" and 200 <= p["code"] < 300}
    full = {n: p for n, p in ok.items() if p["words"] >= SHELL_WORDS}
    shell = {n: p for n, p in ok.items() if p["words"] < SHELL_WORDS}
    if not full:
        top = max((p["words"] for p in ok.values()), default=0)
        if top >= 40 and any(p["h1"] for p in ok.values()):
            note("warn", f"short page: at most {top} words visible without JavaScript for any agent, but it has an H1, so it may "
                 "simply be a short page",
                 "If this page should be longer, server-render the missing copy; otherwise ignore.")
        else:
            hint = " (empty app mount point such as <div id=root>)" if any(p["mount"] for p in ok.values()) else ""
            note("fail", f"every agent sees under {SHELL_WORDS} words, an empty shell for everyone{hint}",
                 "Server-render or statically render this page. Test: curl -s <url> shows its own H1 and 300+ words.")
    elif not shell:
        if len({p["title"] for p in ok.values()}) > 1:
            note("warn", "enough text for all agents but titles differ by agent", "Check what each agent is served.")
    else:
        shell_user_fetch = [n for n in shell if kind(n) == "user-fetch"]
        if "browser" in shell and not shell_user_fetch:
            note("pass", "listed crawlers and user-fetch agents get full content; a default browser fetch gets the client-rendered "
                 "shell (dynamic rendering by user agent)",
                 "Fine for these agents. Make sure the allowlist covers every current AI search and user-fetch agent, "
                 "and that Google and Bing see the same content.")
        else:
            note("fail", "user-agent routing gap: " + ", ".join(shell) + " get a shell while " + ", ".join(full) + " get content",
                 "Add the missing agents to the crawler allowlist, or server-render for everyone. Test each agent with curl -A.")

    # 3. Googlebot and Bingbot should be served the same page
    g, b = prof["search crawler (Googlebot)"], prof["search crawler (Bingbot)"]
    if 200 <= g["code"] < 300 and 200 <= b["code"] < 300:
        hi, lo = max(g["words"], b["words"]), min(g["words"], b["words"])
        if hi >= SHELL_WORDS and lo < hi / 2:
            note("warn", f"Googlebot and Bingbot receive different HTML ({g['words']} vs {b['words']} words)",
                 "Add Bingbot to any crawler allowlist or prerender rule so Bing, and the AI assistants that use its index, see the same page.")

    return status, "; ".join(details) + (". " if details else "") + summary, " ".join(fixes)


def soft_404(base):
    """A nonexistent URL must return 404/410 to crawlers. Returns [(agent, url, code, words)].
    Probes as a listed crawler, user-fetch agents, Googlebot and Bingbot. A browser 200 is expected for
    single-page apps and is reported as info only, because what matters for citations is what agents get."""
    import random
    import string
    tag = "".join(random.choices(string.ascii_lowercase, k=10))
    pth = f"/geo-audit-missing-{tag}"
    out = []
    for name, ua in RENDER_AGENTS.items():
        c, _, body, _ = fetch(base + pth, ua=ua)
        out.append((name, base + pth, c, count_words(" ".join(parse_page(body).text))))
    return out


# ---------------------------------------------------------------------------------------------
# Sitemaps
# ---------------------------------------------------------------------------------------------

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


def _locs(body):
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)


def check_sitemaps(base, from_robots, paths, add):
    """Find a valid sitemap (robots.txt entries first, then /sitemap.xml), follow a sitemap index, check lastmod and --paths."""
    candidates = list(dict.fromkeys(from_robots[:5] + [base + "/sitemap.xml"]))
    found = None
    for sm in candidates:
        c, _, body, _ = fetch(sm, max_bytes=SITEMAP_MAX)
        if c == 200 and ("<urlset" in body or "<sitemapindex" in body):
            found = (sm, body)
            break
    if not found:
        add("discovery", "sitemap", "fail", "no valid sitemap found (tried " + ", ".join(candidates) + ")",
            "Publish sitemap.xml and reference it in robots.txt.")
        return
    sm, body = found
    urls, lastmod_src, complete = _locs(body), body, True
    if "<sitemapindex" in body:
        children = urls
        bodies = []
        for ch in children[:SITEMAP_SAMPLE]:
            c, _, cb, _ = fetch(ch, max_bytes=SITEMAP_MAX)
            if c == 200 and "<urlset" in cb:
                bodies.append(cb)
        urls = [u for cb in bodies for u in _locs(cb)]
        complete = len(children) <= SITEMAP_SAMPLE and len(bodies) == len(children)
        if bodies:
            lastmod_src = "\n".join(bodies)
        add("discovery", f"sitemap {sm}", "pass",
            f"sitemap index with {len(children)} child sitemaps; sampled {len(bodies)}, {len(urls)} URLs in the sample")
    else:
        add("discovery", f"sitemap {sm}", "pass", f"{len(urls)} <loc> entries")
    lm = sitemap_lastmod(lastmod_src)
    if lm is None:
        add("discovery", "sitemap lastmod honesty", "info", "fewer than 10 lastmod values; not assessed")
    elif lm["today_n"] / lm["total"] > 0.1 or lm["most_common_n"] / lm["total"] > 0.3:
        add("discovery", "sitemap lastmod honesty", "warn",
            f"{lm['today_n']}/{lm['total']} stamped today; {lm['most_common_n']}/{lm['total']} share {lm['most_common']}. "
            "Looks generated or bulk-updated rather than real edit dates.",
            "Emit each page's real updated date, or omit lastmod.")
    else:
        add("discovery", "sitemap lastmod honesty", "pass", f"{lm['total']} values, no suspicious clustering")
    if paths:
        known = {urlparse(u).path.rstrip("/") or "/" for u in urls}
        missing = [p for p in paths if (urlparse(urljoin(base + "/", p.lstrip("/"))).path.rstrip("/") or "/") not in known]
        if not complete:
            add("discovery", "--paths listed in sitemap", "info", "sitemap index only partly sampled; not assessed")
        elif missing:
            add("discovery", "--paths listed in sitemap", "warn", "not in the sitemap: " + ", ".join(missing),
                "Add money pages to the sitemap so crawlers and IndexNow-style submissions include them.")
        else:
            add("discovery", "--paths listed in sitemap", "pass", f"all {len(paths)} paths present")


# ---------------------------------------------------------------------------------------------
# Main check
# ---------------------------------------------------------------------------------------------

def _tokens(value):
    return [t for t in re.split(r"[,\s]+", value.lower()) if t]


def check(domain, paths, indexnow_key=None):
    raw = domain if domain.startswith("http") else f"https://{domain}"
    parsed = urlparse(raw)
    # Always test the site root: robots.txt, sitemap and llms.txt live there, even if the user passed a deep URL.
    base = f"{parsed.scheme}://{parsed.netloc}"
    res = {"domain": base, "findings": [], "scores": {}, "unreachable": False}

    def add(area, check_name, status, detail, fix="", group=None):
        res["findings"].append(
            {"area": area, "check": check_name, "status": status, "detail": detail, "fix": fix, "group": group}
        )

    # --- reachability gate: never report fake findings when the fetch itself failed or was refused ---
    code0, hdr0, html0, final_url = fetch(base + "/")
    if code0 == 0:
        res["unreachable"] = True
        res["error"] = html0.replace("ERROR: ", "")
        return res
    if not 200 <= code0 < 300:
        res["homepage_error"] = code0
        add("access", "homepage reachable (browser UA)", "fail", f"HTTP {code0}, final URL {final_url}",
            "A 403/429/503 here often means a WAF or bot challenge refused this check (datacenter IP, non-browser TLS), "
            "not that real visitors are blocked. Retry from another network and confirm with server logs or "
            "Search Console. A 404/5xx is a real site problem.")
        return res

    # --- robots.txt ---
    code, _, robots_txt, _ = fetch(base + "/robots.txt")
    robots, robots_known, sitemaps = Robots(), True, []
    if code == 200 and "<html" in robots_txt[:500].lower():
        add("access", "robots.txt present", "warn",
            "HTTP 200 but the body is HTML (a catch-all route), not robots rules; crawlers treat it as no rules",
            "Serve a real text/plain robots.txt (see assets/robots-ai-template.txt) and return 404 for unknown paths.")
    elif code == 200:
        robots = Robots(robots_txt)
        sitemaps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots_txt)
        add("access", "robots.txt present", "pass", f"HTTP 200, {len(robots_txt)} bytes")
    elif code == 0:
        robots_known = False
        add("access", "robots.txt present", "info", f"could not fetch ({robots_txt[:80]}); robots rules not assessed")
    elif code == 429 or code >= 500:
        robots_known = False
        add("access", "robots.txt present", "fail",
            f"HTTP {code}: Google treats a persistent robots.txt server error as disallow-all, and other crawlers may pause too. "
            "Per-agent rules were not assessed.",
            "Make /robots.txt return 200 (or a plain 404 if you have no rules) reliably.")
    else:
        add("access", "robots.txt present", "warn", f"HTTP {code}; crawlers treat a missing robots.txt (4xx) as allow-all",
            "Publish a robots.txt (see assets/robots-ai-template.txt) and reference your sitemap.")
    test_urls = [base + "/"] + [urljoin(base + "/", p.lstrip("/")) for p in paths]
    for grp, agents in AGENTS.items():
        for token in agents:
            if not robots_known:
                add("access", f"robots: {token} ({grp})", "info", "robots.txt unavailable; not assessed")
                continue
            blocked = [u for u in test_urls if not robots.can_fetch(token, u)]
            if grp == "search_and_user_fetch":
                status = "fail" if blocked else "pass"
                fix = f"Allow {token} in robots.txt if you want AI citations or search visibility." if blocked else ""
            else:
                status, fix = "info", ""
            detail = f"blocked on {len(blocked)}/{len(test_urls)} tested URLs" if blocked else "allowed"
            add("access", f"robots: {token} ({grp})", status, detail, fix,
                group="robots-agents" if grp == "search_and_user_fetch" else None)

    # --- WAF / CDN probe ---
    add("access", "homepage reachable (browser UA)", "pass", f"HTTP {code0}, final URL {final_url}")
    for token, ua in AGENTS["search_and_user_fetch"].items():
        c, _, _, _ = fetch(base + "/", ua=ua)
        if c in (401, 403, 429, 503):
            if token in SEARCH_ENGINES:
                add("access", f"WAF probe: {token}", "warn",
                    f"HTTP {c} vs {code0} for browser UA. WAFs that verify {token} by IP reject spoofed user agents, so this "
                    "is not proof the real crawler is blocked.",
                    "Confirm with Search Console URL Inspection (Google) or Bing Webmaster Tools URL Inspection (Bing).",
                    group="waf-agents")
            else:
                add("access", f"WAF probe: {token}", "fail",
                    f"HTTP {c} vs {code0} for browser UA (UA-string probe only; real bots also use IP ranges)",
                    "Check CDN/WAF bot rules and allowlist verified AI agents.", group="waf-agents")
        elif c == 0:
            add("access", f"WAF probe: {token}", "warn", "request error", group="waf-agents")
        else:
            add("access", f"WAF probe: {token}", "pass", f"HTTP {c}", group="waf-agents")

    # --- llms.txt ---
    c, _, body, _ = fetch(base + "/llms.txt")
    if c == 200 and body.strip() and "<html" not in body[:300].lower():
        add("discovery", "llms.txt", "pass", f"present, {len(body.splitlines())} lines")
    else:
        add("discovery", "llms.txt", "info", f"not found (HTTP {c})",
            "Optional. Add after basics (assets/llms-txt-template.md). No proven ranking effect.")

    # --- sitemap ---
    check_sitemaps(base, sitemaps, paths, add)

    # --- homepage content ---
    p = parse_page(html0)
    words = count_words(" ".join(p.text))
    add("render", "visible text in raw HTML", "pass" if words >= SHELL_WORDS else ("warn" if words >= 50 else "fail"),
        f"{words} words without running JavaScript, {p.script_count} script tags",
        "Server-render or statically render key copy." if words < SHELL_WORDS else "")

    # --- indexing and quoting directives ---
    lc = {k.lower(): v for k, v in hdr0.items()}
    directives = {f"meta {n}": p.meta[n] for n in ("robots", "googlebot", "bingbot") if p.meta.get(n)}
    if lc.get("x-robots-tag"):
        directives["X-Robots-Tag"] = lc["x-robots-tag"]
    noindex = [k for k, v in directives.items() if {"noindex", "none"} & set(_tokens(v))]
    add("indexing", "noindex", "fail" if noindex else "pass",
        ("; ".join(f"{k}: {directives[k]}" for k in noindex)) if noindex else (", ".join(f"{k}: {v}" for k, v in directives.items()) or "none"),
        "Remove noindex on pages meant to rank/be cited." if noindex else "")
    limits = []
    for k, v in directives.items():
        toks = set(_tokens(v))
        if "nosnippet" in toks or "max-snippet:0" in toks:
            limits.append(f"{k}: nosnippet/max-snippet:0 (blocks quoting in Google AI Overviews and Bing/Copilot answers)")
        if "noarchive" in toks:
            limits.append(f"{k}: noarchive (Bing: page is not linked in Copilot answers, per Bing docs)")
        if "nocache" in toks:
            limits.append(f"{k}: nocache (Bing: only URL, title and snippet may be used)")
    add("indexing", "snippet and archive controls", "warn" if limits else "pass",
        "; ".join(limits) if limits else "no nosnippet, max-snippet:0, noarchive or nocache on the homepage",
        "If this is not a deliberate opt-out, remove it: these directives limit how AI answers can quote or link the page."
        if limits else "")
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
    org = [t for t in types if is_organization_type(t)]
    add("schema", "Organization schema", "pass" if org else "warn", ", ".join(org) if org else "missing on homepage")

    # --- search-engine webmaster hints (Bing feeds Copilot and, reportedly, ChatGPT search and DuckDuckGo) ---
    c, _, bx, _ = fetch(base + "/BingSiteAuth.xml")
    bing_xml = c == 200 and "<users" in bx
    if p.meta.get("msvalidate.01") or bing_xml:
        add("indexing", "Bing Webmaster Tools verification", "pass",
            "msvalidate.01 meta tag" if p.meta.get("msvalidate.01") else "BingSiteAuth.xml present")
    else:
        add("indexing", "Bing Webmaster Tools verification", "info",
            "no msvalidate.01 meta tag or BingSiteAuth.xml found (a DNS CNAME or Search Console import also verifies a site)",
            "Verify the site in Bing Webmaster Tools, submit the sitemap, enable IndexNow, and read the AI Performance report.")
    add("indexing", "Google Search Console verification", "pass" if p.meta.get("google-site-verification") else "info",
        "google-site-verification meta tag found" if p.meta.get("google-site-verification")
        else "no google-site-verification meta tag found (a DNS record or file also verifies a site)")
    if indexnow_key:
        c, _, kb, _ = fetch(f"{base}/{indexnow_key}.txt")
        if c == 200 and kb.strip() == indexnow_key:
            add("discovery", "IndexNow key file", "pass", f"/{indexnow_key}.txt matches the key")
        else:
            add("discovery", "IndexNow key file", "warn", f"/{indexnow_key}.txt returned HTTP {c} or a different value",
                "Host the key file at the site root (or the keyLocation you submit with) so Bing and other IndexNow engines accept submissions.")
    else:
        add("discovery", "IndexNow key file", "info", "not checked (pass --indexnow-key KEY to verify /KEY.txt)")

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
            add("indexing", f"soft 404 ({name})", "pass", f"{u} -> HTTP {c}", group="soft404")
        elif name == "browser":
            add("indexing", f"soft 404 ({name})", "info",
                f"{u} -> HTTP {c}. Common for single-page apps; people see the app's own not-found view.")
        elif c == 200:
            add("indexing", f"soft 404 ({name})", "fail",
                f"{u} -> HTTP 200 with {w} words (nonexistent URL served to this agent as a page)",
                "Return a real 404 (and noindex) to crawlers for unknown URLs. Test with curl -A for each agent class.",
                group="soft404")
        else:
            add("indexing", f"soft 404 ({name})", "warn", f"{u} -> HTTP {c}", group="soft404")

    # --- score: every check counts once; grouped rows collapse to the worst row in the group ---
    weights = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
    units = {}
    for i, f in enumerate(res["findings"]):
        if f["status"] in weights:
            key = f["group"] or f"row-{i}"
            units[key] = min(units.get(key, 1.0), weights[f["status"]])
    res["scores"]["technical_readiness_pct"] = round(100 * sum(units.values()) / max(1, len(units)))
    res["scores"]["fail_count"] = sum(1 for f in res["findings"] if f["status"] == "fail")
    return res


def _cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def to_markdown(res):
    if res.get("unreachable"):
        hint = ""
        if "CERTIFICATE_VERIFY_FAILED" in (res.get("error") or ""):
            hint = ("\n\n**Likely cause: Python cannot find root certificates** (common with python.org builds on macOS). "
                    "Run `/Applications/Python 3.x/Install Certificates.command`, or set `SSL_CERT_FILE` to your CA bundle "
                    "(`/etc/ssl/cert.pem` on macOS), then re-run.")
        return (f"# AI readiness: {res['domain']}\n\n**UNREACHABLE from this environment**: {res.get('error')}{hint}\n\n"
                "No findings were produced and no score was computed. This is a network problem in the place the script "
                "ran (sandbox allowlist, DNS, TLS, or the site being down), not evidence about the site. "
                "Re-run from a machine with open internet, or use WebFetch on the homepage, /robots.txt, /sitemap.xml "
                "and /llms.txt and review manually.")
    if res.get("homepage_error"):
        f = res["findings"][0]
        return (f"# AI readiness: {res['domain']}\n\n**HOMEPAGE RETURNED HTTP {res['homepage_error']}**: page-level checks were skipped "
                "and no score was computed, because there is no page content to assess.\n\n"
                f"{f['fix']}")
    out = [f"# AI readiness: {res['domain']}", "",
           f"Technical readiness: **{res['scores']['technical_readiness_pct']}%** ({res['scores']['fail_count']} failures)", "",
           "| Area | Check | Status | Detail | Fix |", "|---|---|---|---|---|"]
    for f in res["findings"]:
        out.append(f"| {_cell(f['area'])} | {_cell(f['check'])} | {f['status']} | {_cell(f['detail'])} | {_cell(f['fix'])} |")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--paths", nargs="*", default=[])
    ap.add_argument("--json")
    ap.add_argument("--indexnow-key", help="verify the IndexNow key file at /KEY.txt")
    ap.add_argument("--fail-on", choices=("none", "fail"), default="none",
                    help="exit 1 when any check fails (for CI)")
    a = ap.parse_args(argv)
    res = check(a.domain, a.paths, a.indexnow_key)
    print(to_markdown(res))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(res, fh, indent=2)
    if res.get("unreachable"):
        return 2
    if res.get("homepage_error"):
        return 3
    return 1 if a.fail_on == "fail" and res["scores"]["fail_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
