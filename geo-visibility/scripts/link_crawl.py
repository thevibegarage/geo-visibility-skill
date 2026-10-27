"""Bounded internal-link crawl (standard library only, no network).

`crawl()` walks the internal links of one site breadth-first. It never makes a request itself: the caller passes a `get`
function that performs exactly one request and does not follow redirects. That keeps the request budget, the same-host rule and
the robots.txt rule in this file, where tests can drive them with a fake site.

Everything reported is measured from what the crawl saw: a link target answered or it did not, a page is N clicks from the
start or it is not. Where the crawl cannot know (it ran out of budget, or a page needs JavaScript to show its links), the
affected check says "not assessed" instead of guessing.

`check_ai_readiness.py` supplies the network function and turns `findings()` into report rows.
"""
import re
import time
from collections import deque
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit

DEFAULT_BUDGET = 50  # requests, when --crawl is given without a number
MAX_BUDGET = 500
MAX_SECONDS = 300  # wall-clock limit as well, so a server that stalls on every request cannot hold a run for hours
MAX_REDIRECTS = 5  # a link whose target needs more redirects than this is a failure
SHELL_WORDS = 50  # a page showing fewer words than this without JavaScript may add its links with JavaScript
DEPTH_GUIDELINE = 3  # a common rule of thumb for how many clicks important pages should take, not a search-engine rule
REDIRECT_CODES = (301, 302, 303, 307, 308)
PERMANENT_CODES = (301, 308)
UNVERIFIABLE_CODES = (401, 403, 429)  # usually bot protection or rate limiting rather than a missing page
LIST_LIMIT = 3

AREA = "links"
SUMMARY, BROKEN, CHAINS, SINGLE_REDIRECTS, DEPTH, ORPHANS = (
    "internal link crawl", "broken internal links", "redirect chains", "internal links to redirecting URLs", "click depth",
    "orphan pages")

_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")
_SAFE_PATH = "/%:@!$&'()*+,;=-._~"
_SAFE_QUERY = _SAFE_PATH + "?"


# ---------------------------------------------------------------------------------------------
# URLs and links
# ---------------------------------------------------------------------------------------------

def normalize(url):
    """One spelling per URL, or None when it is not a plain http(s) URL.

    The fragment is dropped, scheme and host are lowercased, a default port is dropped, an empty path becomes "/", and characters
    that cannot appear in a request line (spaces, non-ASCII) are percent-encoded. Existing %XX escapes are kept.
    """
    try:
        parts = urlsplit(url.strip())
        host, port = parts.hostname, parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not host or parts.username or parts.password:
        return None
    if ":" in host:
        host = f"[{host}]"
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    query = "?" + quote(parts.query, safe=_SAFE_QUERY) if parts.query else ""
    return f"{scheme}://{host}{quote(parts.path or '/', safe=_SAFE_PATH)}{query}"


def _join(base, href):
    """href resolved against base and normalized, or None. A scheme other than http(s) is rejected before joining: Python 3.8's
    urljoin reads "tel:5551234" as a relative path (digits after a colon look like a port), which would become a request."""
    href = href.strip()
    scheme = _SCHEME.match(href)
    if scheme and scheme.group(1).lower() not in ("http", "https"):
        return None
    try:
        return normalize(urljoin(base, href))
    except ValueError:
        return None


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.base = None
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        href = next((v for k, v in attrs if k == "href" and v), None)
        if href is None:
            return
        if tag == "base" and self.base is None:
            self.base = href
        elif tag in ("a", "area"):
            self.hrefs.append(href)


def extract_links(html, page_url):
    """The distinct http(s) URLs a page links to, in document order. A <base href> is honoured; mailto:, tel:, javascript:,
    fragment-only links and links back to the page itself are not links for this purpose."""
    parser = _Links()
    try:
        parser.feed(html)
    except Exception:  # malformed markup: keep what was parsed before it
        pass
    page = normalize(page_url)
    base = (_join(page_url, parser.base) if parser.base else None) or page_url
    out, seen = [], {page}
    for href in parser.hrefs:
        target = _join(base, href)
        if target and target not in seen:
            seen.add(target)
            out.append(target)
    return out


def _host(url):
    return urlsplit(url).netloc


def _label(res, url):
    """How a URL is shown: path and query for the audited host, the full URL for anything else."""
    parts = urlsplit(url)
    if parts.netloc == res["host"] and parts.scheme == urlsplit(res["start"]).scheme:
        return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return url


# ---------------------------------------------------------------------------------------------
# The crawl
# ---------------------------------------------------------------------------------------------

def _node(depth, status=None, error="", blocked=False):
    return {"depth": depth, "status": status, "error": error, "blocked": blocked, "html": False, "shell": False,
            "location": "", "target": None, "links": []}


def crawl(start, get, allowed, is_shell, budget, pause=None, max_seconds=MAX_SECONDS, clock=time.monotonic):
    """Breadth-first crawl of the start URL's host. Returns a result dict that the other functions here read.

    get(url) -> (status, location, html, error): ONE request, redirects not followed. `html` is the page text for a 200 HTML
        response and None for anything else (the body of other responses is never needed). Status 0 is a network error.
    allowed(url) -> bool: whether robots.txt lets the crawler fetch the URL. A URL that is not allowed is never requested.
    is_shell(html) -> bool: whether a page shows so little text without JavaScript that it may add its links with JavaScript.
    budget: the most requests the crawl may make, redirects included. max_seconds: the most time it may take (checked before each
        request; a request already under way finishes). clock: a monotonic clock, replaceable in tests.
    pause(): called before every request after the first.

    Only URLs on the start URL's host are requested; a link or redirect to another host is recorded and left alone.
    Click depth counts links followed from the start; a redirect adds no click. A 429 response ends the crawl.
    """
    start = normalize(start)
    host = _host(start)
    nodes, external = {}, set()
    best = {start: 0}
    queue = deque([(start, 0)])
    requests, stopped, started = 0, None, clock()

    def reach(url, depth, front=False):
        if url in nodes or best.get(url, depth + 1) <= depth:
            return
        best[url] = depth
        if front:  # a redirect costs no click, so its target is as shallow as the URL that redirected (0-1 breadth-first search)
            queue.appendleft((url, depth))
        else:
            queue.append((url, depth))

    while queue:
        url, depth = queue.popleft()
        if url in nodes or depth > best[url]:
            continue
        if not allowed(url):
            nodes[url] = _node(depth, blocked=True)
            continue
        if requests >= budget:
            queue.appendleft((url, depth))
            break
        if clock() - started >= max_seconds:
            queue.appendleft((url, depth))
            stopped = f"time limit of {max_seconds} seconds reached"
            break
        if requests and pause:
            pause()
        requests += 1
        status, location, html, error = get(url)
        node = nodes[url] = _node(depth, status=status, error=error)
        if status == 429:
            stopped = "HTTP 429: the server asked for fewer requests"
            break
        if status in REDIRECT_CODES and location:
            node["location"] = location
            node["target"] = _join(url, location)
            if node["target"] is None:
                continue
            if _host(node["target"]) == host:
                reach(node["target"], depth, front=True)
            else:
                external.add(_host(node["target"]))
        elif html is not None:
            node["html"] = True
            node["shell"] = bool(is_shell(html))
            for link in extract_links(html, url):
                if _host(link) == host:
                    node["links"].append(link)
                    reach(link, depth + 1)
                else:
                    external.add(_host(link))
    unfetched = sorted({u for u, _ in queue if u not in nodes})
    return {"start": start, "host": host, "budget": budget, "requests": requests, "stopped": stopped,
            "complete": not unfetched and stopped is None, "nodes": nodes, "unfetched": unfetched,
            "external_hosts": sorted(external)}


def follow(res, url):
    """Follow the redirects the crawl recorded for url.

    Returns {"hops": [(from, status, to)], "final": last URL reached, "status": its status, "problem": ...} where problem is
    None, "loop", "off-site" (the chain leaves the host), "blocked" (robots.txt), "not-fetched" (budget) or "bad-location".
    """
    nodes = res["nodes"]
    seen, hops, cur = {url}, [], url

    def out(status, problem=None):
        return {"hops": hops, "final": cur, "status": status, "problem": problem}

    while True:
        node = nodes.get(cur)
        if node is None:
            return out(None, "not-fetched")
        if node["blocked"]:
            return out(None, "blocked")
        if not (node["status"] in REDIRECT_CODES and node["location"]):
            return out(node["status"])
        target = node["target"]
        hops.append((cur, node["status"], target or node["location"]))
        if target is None:
            return out(node["status"], "bad-location")
        if _host(target) != res["host"]:
            return out(node["status"], "off-site")
        if target in seen:
            return out(node["status"], "loop")
        seen.add(target)
        cur = target


def inbound(res):
    """{url: [pages that link to it]} from the links between crawled pages. Redirects are not links."""
    out = {}
    for page, node in res["nodes"].items():
        for target in node["links"]:
            out.setdefault(target, []).append(page)
    return out


def _verdict(outcome):
    """What following a link target came to: ok, broken, unverified, loop or skip (not assessable here)."""
    problem, status = outcome["problem"], outcome["status"]
    if problem == "loop":
        return "loop"
    if problem in ("off-site", "blocked", "not-fetched"):
        return "skip"
    if problem == "bad-location":
        return "unverified"
    if 200 <= status < 300:
        return "ok"
    if status in UNVERIFIABLE_CODES or status >= 500 or status < 400:  # 0 is a network error; 3xx here has no Location
        return "unverified"
    return "broken"


def find_orphans(res, sitemap):
    """Same-host sitemap URLs that no crawled page links to. Returns (urls, reason): urls is None when this cannot be assessed.

    A link counts when it points at the sitemap URL or at a URL that redirects to it; a trailing slash and http versus https are
    ignored. It is only reliable when the crawl saw every link, so an incomplete crawl, or a page whose links need JavaScript,
    makes the answer "not assessed".
    """
    if sitemap is None:
        return None, "no sitemap was found to compare with"
    if not res["complete"]:
        return None, "the crawl stopped before it had followed every link, so an unlinked page might simply not have been reached"
    shells = [u for u, n in res["nodes"].items() if n["shell"]]
    if shells:
        return None, (f"{len(shells)} crawled page(s) show under {SHELL_WORDS} words without JavaScript (for example "
                      f"{_label(res, shells[0])}), so a page that only their JavaScript links to would look unlinked")

    def key(u):
        p = urlsplit(u)
        return (p.netloc, p.path.rstrip("/") or "/", p.query)

    reached = {key(u) for u in res["nodes"]}
    orphans, seen = [], set()
    for raw in sitemap["urls"]:
        u = normalize(raw)
        if u and _host(u) == res["host"] and key(u) not in reached and key(u) not in seen:
            seen.add(key(u))
            orphans.append(u)
    return orphans, ""


# ---------------------------------------------------------------------------------------------
# Report rows
# ---------------------------------------------------------------------------------------------

def _more(items, limit=LIST_LIMIT):
    return "; ".join(items[:limit]) + (f"; and {len(items) - limit} more" if len(items) > limit else "")


def _from(res, sources):
    names = [_label(res, s) for s in sources]
    return "from " + ", ".join(names[:2]) + (f" and {len(names) - 2} more" if len(names) > 2 else "")


def _chain(res, outcome):
    steps = [f"{_label(res, a)} ({code})" for a, code, _ in outcome["hops"]]
    return " -> ".join(steps + [_label(res, outcome["hops"][-1][2])])


def findings(res, sitemap=None):
    """Report rows [(area, check, status, detail, fix)] for a finished crawl.

    sitemap: None when no sitemap was found, else {"urls": [...], "complete": bool} (complete is False when a sitemap index
    was only partly read).
    """
    nodes = res["nodes"]
    pages = [u for u, n in nodes.items() if n["html"]]
    inb = inbound(res)
    outcomes = {t: follow(res, t) for t in inb}
    out = []

    def add(check, status, detail, fix=""):
        out.append((AREA, check, status, detail, fix))

    # --- what the crawl covered, and what it could not see
    blocked = [u for u, n in nodes.items() if n["blocked"]]
    shells = [u for u in pages if nodes[u]["shell"]]
    parts = [f"{len(pages)} HTML page(s) read in {res['requests']} request(s) (limit {res['budget']})",
             f"{sum(len(nodes[u]['links']) for u in pages)} internal links"]
    if pages:
        parts.append(f"the deepest page is {max(nodes[u]['depth'] for u in pages)} click(s) from the start")
    if blocked:
        parts.append(f"{len(blocked)} URL(s) not requested because robots.txt disallows Googlebot")
    if res["external_hosts"]:
        parts.append(f"{len(res['external_hosts'])} other host(s) linked, not requested")
    if shells:
        parts.append(f"{len(shells)} page(s) show under {SHELL_WORDS} words without JavaScript, so links they add with JavaScript are invisible here")
    if res["stopped"]:
        parts.append(f"stopped: {res['stopped']}")
    if res["unfetched"]:
        parts.append(f"{len(res['unfetched'])} linked URL(s) not requested because the limit was reached")
    incomplete_fix = ("" if res["complete"] else
                      "Run again with a larger --crawl (up to " + str(MAX_BUDGET) + "); the checks below describe only the part crawled.")
    if not inb:
        start = nodes.get(res["start"])
        if start is None:
            why = "the crawl stopped before it requested the start page"
        elif start["blocked"]:
            why = "robots.txt disallows Googlebot from the start page, so nothing was crawled"
        elif not start["html"]:
            why = "the start page answered " + (f"HTTP {start['status']}" if start["status"] else "with a network error") + " to Googlebot"
        else:
            why = "no internal links were found in the HTML Googlebot receives (a page that builds its links with JavaScript shows none)"
        add(SUMMARY, "info", "; ".join([parts[0], why] + parts[2:]), incomplete_fix)
        return out
    add(SUMMARY, "info", "; ".join(parts), incomplete_fix)

    # --- link targets: broken, or needing more than one redirect
    verdicts = {t: _verdict(o) for t, o in outcomes.items()}
    checked = sum(1 for v in verdicts.values() if v != "skip")
    skipped = len(verdicts) - checked
    broken = [t for t, v in verdicts.items() if v == "broken"]
    unverified = [t for t, v in verdicts.items() if v == "unverified"]

    def target_text(t):
        o = outcomes[t]
        what = f"HTTP {o['status']}" if o["status"] else (nodes[o["final"]]["error"] or "network error")[:60]
        via = f" -> {_label(res, o['final'])}" if o["hops"] else ""
        return f"{_label(res, t)}{via} ({what}, {_from(res, inb[t])})"

    if broken:
        extra = f"; {len(unverified)} more could not be verified" if unverified else ""
        add(BROKEN, "fail", f"{len(broken)} internal link target(s) are broken: " + _more([target_text(t) for t in broken]) + extra,
            "Fix or remove each link, or restore the page. If the page moved, link to its new URL and add a 301 from the old one.")
    elif unverified:
        add(BROKEN, "warn", f"{len(unverified)} internal link target(s) could not be verified: " +
            _more([target_text(t) for t in unverified]),
            "Open each URL in a browser. HTTP 401, 403 and 429 usually mean bot protection or rate limiting refused this check, "
            "not that the page is missing; a 5xx is a server error worth fixing.")
    else:
        add(BROKEN, "pass", f"{checked} internal link target(s) checked, none broken" +
            (f"; {skipped} not checked (robots.txt, left the site, or the crawl limit)" if skipped else ""))

    loops = [t for t, o in outcomes.items() if o["problem"] == "loop"]
    long_ = [t for t, o in outcomes.items() if o["problem"] != "loop" and len(o["hops"]) > MAX_REDIRECTS]
    chains = [t for t, o in outcomes.items() if o["problem"] != "loop" and 2 <= len(o["hops"]) <= MAX_REDIRECTS]
    if loops or long_:
        bad = [f"loop {_chain(res, outcomes[t])} ({_from(res, inb[t])})" for t in loops] + \
              [f"{len(outcomes[t]['hops'])} redirects {_chain(res, outcomes[t])} ({_from(res, inb[t])})" for t in long_]
        add(CHAINS, "fail", _more(bad), "Link straight to the final URL and remove the loop or the extra hops: crawlers give up on "
            "long chains, and a loop is a page nobody can reach.")
    elif chains:
        add(CHAINS, "warn", f"{len(chains)} internal link target(s) need two or more redirects: " +
            _more([f"{_chain(res, outcomes[t])} ({_from(res, inb[t])})" for t in chains]),
            "Link straight to the final URL, and point each redirect at the final URL instead of at the next redirect.")
    else:
        add(CHAINS, "pass", "no internal link target needs more than one redirect")
    single = [t for t, o in outcomes.items() if len(o["hops"]) == 1 and o["problem"] is None]
    if single:
        permanent = sum(1 for t in single if outcomes[t]["hops"][0][1] in PERMANENT_CODES)
        add(SINGLE_REDIRECTS, "info", f"{len(single)} internal link target(s) redirect once ({permanent} permanently, "
            f"{len(single) - permanent} temporarily): " + _more([f"{_chain(res, outcomes[t])} ({_from(res, inb[t])})" for t in single]),
            "Update these links to point at the final URL, and make internal redirects permanent (301 or 308) unless they are meant to change.")

    # --- click depth
    depths = sorted(((nodes[u]["depth"], u) for u in pages), key=lambda d: (-d[0], d[1]))
    deep = [(d, u) for d, u in depths if d > DEPTH_GUIDELINE]
    if deep:
        add(DEPTH, "info", f"{len(deep)} page(s) are more than {DEPTH_GUIDELINE} clicks from the start ({DEPTH_GUIDELINE} is a rule of "
            f"thumb, not a search-engine rule): " + _more([f"{_label(res, u)} ({d})" for d, u in deep]),
            "Link important pages from the homepage or from a hub page so they are reachable in fewer clicks.")
    else:
        add(DEPTH, "pass", f"the deepest page is {depths[0][0]} click(s) from the start (rule of thumb: at most {DEPTH_GUIDELINE})")

    # --- orphans
    orphans, reason = find_orphans(res, sitemap)
    if orphans is None:
        add(ORPHANS, "info", f"not assessed: {reason}",
            "Re-run with a larger --crawl so the crawl can finish." if not res["complete"] else "")
    elif orphans:
        add(ORPHANS, "warn", f"{len(orphans)} sitemap URL(s) have no internal link pointing at them: " +
            _more([_label(res, u) for u in orphans]) + ("" if sitemap["complete"] else " (the sitemap index was only partly read)"),
            "Link each page from a relevant page (navigation, a hub page, related-article links), or remove it from the sitemap "
            "if it should not be indexed.")
    else:
        add(ORPHANS, "pass", "every same-host sitemap URL is linked from a crawled page" +
            ("" if sitemap["complete"] else " (the sitemap index was only partly read)"))
    return out


def report_data(res, sitemap=None):
    """The crawl as plain data for the JSON output (the input a later HTML report can draw the link graph from)."""
    inb = inbound(res)
    orphans, _ = find_orphans(res, sitemap)
    return {"start": res["start"], "budget": res["budget"], "requests": res["requests"], "complete": res["complete"],
            "stopped": res["stopped"], "unfetched": len(res["unfetched"]), "external_hosts": res["external_hosts"],
            "orphans": orphans,
            "pages": [{"url": u, "depth": n["depth"], "status": n["status"], "inbound": len(inb.get(u, [])),
                       "outlinks": len(n["links"]), "redirects_to": n["target"], "shell": n["shell"], "blocked": n["blocked"]}
                      for u, n in res["nodes"].items()]}
