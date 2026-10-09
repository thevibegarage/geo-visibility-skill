"""On-page SEO checks computed from the HTML a crawler receives (standard library only).

Everything here is measured from the page, not estimated by a model: a title is present or it is not, an image has an alt
attribute or it does not. The thresholds that are guidelines rather than rules (title length, response time) are labelled as
such in the detail text, and advisory findings are reported as `info`, never as failures.

`check_ai_readiness.py` fetches each page it audits as Googlebot and passes the HTML here. Nothing in this module touches
the network.
"""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

GENERIC_ANCHORS = {"click here", "here", "read more", "more", "learn more", "this link", "link", "click", "details", "continue"}
LANG_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
# hreflang values Google accepts: x-default, or ISO 639-1 language with an optional ISO 15924 script and ISO 3166-1 region
HREFLANG_RE = re.compile(r"^(x-default|[a-z]{2,3}(-[a-z]{4})?(-([a-z]{2}|\d{3}))?)$", re.I)
TITLE_MIN, TITLE_MAX = 10, 70
DESC_SHORT, DESC_LONG = 50, 320
SLOW_INFO_MS, SLOW_WARN_MS = 1000, 2000
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")


class SeoParser(HTMLParser):
    """Collects the facts the checks need in one pass over the raw HTML."""

    def __init__(self):
        super().__init__()
        self.lang = None
        self.titles = []
        self.meta = {}
        self.props = {}
        self.charset = None
        self.canonicals = []
        self.hreflangs = []
        self.headings = []
        self.images = []
        self.links = []
        self.blocking_scripts = 0
        self._in_head = False
        self._title = None
        self._heading = None
        self._anchor = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v if v is not None else "") for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "head":
            self._in_head = True
        elif tag == "body":
            self._in_head = False
        elif tag == "title" and self._title is None:
            self._title = []
        elif tag == "meta":
            if "charset" in a:
                self.charset = a["charset"]
            if a.get("http-equiv", "").lower() == "content-type" and "charset" in a.get("content", "").lower():
                self.charset = a["content"]
            name, prop = a.get("name", "").lower(), a.get("property", "").lower()
            if name:
                self.meta[name] = a.get("content", "")
            if prop:
                self.props[prop] = a.get("content", "")
        elif tag == "link":
            rel = a.get("rel", "").lower().split()
            if "canonical" in rel:
                self.canonicals.append(a.get("href", ""))
            if "alternate" in rel and a.get("hreflang"):
                self.hreflangs.append((a["hreflang"], a.get("href", "")))
        elif tag in HEADING_TAGS:
            self._heading = (int(tag[1]), [])
        elif tag == "img":
            self.images.append({"src": a.get("src") or a.get("data-src") or "", "alt": a.get("alt"), "width": a.get("width"),
                                "height": a.get("height")})
            if self._anchor is not None and a.get("alt"):
                self._anchor["text"].append(a["alt"])
        elif tag == "a":
            self._anchor = {"href": a.get("href", ""), "rel": a.get("rel", "").lower(), "text": []}
        elif tag == "script" and self._in_head and a.get("src") and "async" not in a and "defer" not in a \
                and a.get("type", "").lower() != "module":
            self.blocking_scripts += 1

    def handle_endtag(self, tag):
        if tag == "head":
            self._in_head = False
        elif tag == "title" and self._title is not None:
            self.titles.append("".join(self._title).strip())
            self._title = None
        elif tag in HEADING_TAGS and self._heading is not None:
            self.headings.append((self._heading[0], " ".join("".join(self._heading[1]).split())))
            self._heading = None
        elif tag == "a" and self._anchor is not None:
            self._anchor["text"] = " ".join("".join(self._anchor["text"]).split())
            self.links.append(self._anchor)
            self._anchor = None

    def handle_data(self, data):
        if self._title is not None:
            self._title.append(data)
        if self._heading is not None:
            self._heading[1].append(data)
        if self._anchor is not None:
            self._anchor["text"].append(data)


def analyze(html):
    """Parse HTML into the facts the checks use."""
    p = SeoParser()
    try:
        p.feed(html)
    except Exception:
        pass
    h1s = [t for lvl, t in p.headings if lvl == 1]
    return {
        "title": p.titles[0] if p.titles else None, "title_count": len(p.titles),
        "description": p.meta.get("description"), "viewport": p.meta.get("viewport"), "lang": p.lang, "charset": p.charset,
        "h1_count": len(h1s), "headings": p.headings, "canonicals": p.canonicals, "hreflangs": p.hreflangs,
        "og": {k: v for k, v in p.props.items() if k.startswith("og:")},
        "twitter_card": p.meta.get("twitter:card") or p.props.get("twitter:card"),
        "images": p.images, "links": p.links, "blocking_scripts": p.blocking_scripts, "bytes": len(html.encode("utf-8")),
    }


def _norm_path(url):
    path = urlparse(url).path or "/"
    return path if path == "/" else path.rstrip("/")


def _list(items, limit=3):
    shown = ", ".join(items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def page_findings(facts, url, response_ms=None):
    """Checks for one page. Returns [(area, check, status, detail, fix)]; every warn and fail carries a fix."""
    out = []

    def add(area, check, status, detail, fix=""):
        out.append((area, check, status, detail, fix))

    # --- title
    title = facts["title"]
    if title is None or not title.strip():
        add("onpage", "title", "fail", "missing" if title is None else "empty",
            "Add a unique <title> that says what the page is and who it is for (roughly 10-70 characters).")
    elif facts["title_count"] > 1:
        add("onpage", "title", "warn", f"{facts['title_count']} <title> elements; the first is used: {title[:70]}", "Keep exactly one <title>.")
    elif len(title) < TITLE_MIN:
        add("onpage", "title", "warn", f"{len(title)} characters: {title}", "Use a descriptive title of roughly 10-70 characters.")
    elif len(title) > TITLE_MAX:
        add("onpage", "title", "warn", f"{len(title)} characters (a guideline, not a rule: results cut titles by pixel width, "
            f"roughly 60 characters): {title[:90]}", "Put the key words first and aim for roughly 60 characters.")
    else:
        add("onpage", "title", "pass", f"{len(title)} characters: {title}")

    # --- meta description
    desc = facts["description"]
    if desc is None or not desc.strip():
        add("onpage", "meta description", "warn", "missing" if desc is None else "empty",
            "Add a meta description: one or two sentences that state the offer.")
    elif len(desc) < DESC_SHORT:
        add("onpage", "meta description", "info", f"{len(desc)} characters, short: {desc}",
            "Consider one or two full sentences; search engines may write their own snippet either way.")
    elif len(desc) > DESC_LONG:
        add("onpage", "meta description", "info", f"{len(desc)} characters, long enough to be cut or rewritten",
            "Lead with the most useful sentence; search engines may write their own snippet either way.")
    else:
        add("onpage", "meta description", "pass", f"{len(desc)} characters")

    # --- headings
    n1 = facts["h1_count"]
    if n1 == 0:
        add("onpage", "single h1", "warn", "no H1", "Use one H1 that matches the page topic.")
    elif n1 > 1:
        add("onpage", "single h1", "info", f"{n1} H1 elements (HTML allows several)",
            "One clear main heading is easier for readers and for engines to summarize.")
    else:
        add("onpage", "single h1", "pass", "1 H1")
    empty = [lvl for lvl, text in facts["headings"] if not text]
    skipped = []
    prev = 0
    for lvl, _ in facts["headings"]:
        if prev and lvl > prev + 1:
            skipped.append(f"h{prev} to h{lvl}")
        prev = lvl
    if empty:
        add("onpage", "heading structure", "warn", f"{len(empty)} empty heading element(s)", "Remove empty headings or give them text.")
    elif skipped:
        add("onpage", "heading structure", "info", "skipped level(s): " + _list(skipped), "Keep heading levels in order (h1, h2, h3...).")
    elif facts["headings"]:
        add("onpage", "heading structure", "pass", f"{len(facts['headings'])} headings in order")

    # --- canonical
    page_host, page_path = urlparse(url).netloc.lower(), _norm_path(url)
    canon = [c for c in facts["canonicals"] if c.strip()]
    if not canon:
        add("indexing", "canonical", "warn", "missing", "Add a canonical tag that points at the preferred URL of this page.")
    elif len(set(canon)) > 1:
        add("indexing", "canonical", "warn", f"{len(set(canon))} different canonical URLs: {_list(sorted(set(canon)))}",
            "Declare exactly one canonical URL.")
    else:
        c = canon[0]
        cu = urlparse(c)
        if not cu.scheme or not cu.netloc:
            add("indexing", "canonical", "warn", f"relative URL: {c}", "Use an absolute canonical URL including https:// and the host.")
        elif cu.netloc.lower() != page_host:
            add("indexing", "canonical", "warn", f"points to another host: {c}",
                "If this page is the original, point the canonical at itself; otherwise confirm the other host is intended.")
        elif url.startswith("https://") and cu.scheme == "http":
            add("indexing", "canonical", "warn", f"https page canonicalises to http: {c}", "Use the https URL as the canonical.")
        elif _norm_path(c) != page_path:
            add("indexing", "canonical", "info", f"canonicalised to {urlparse(c).path or '/'} (confirm this is intended)",
                "A page that canonicalises elsewhere asks engines to index the other URL instead.")
        else:
            add("indexing", "canonical", "pass", c)

    # --- mobile and language basics
    if not facts["viewport"]:
        add("onpage", "viewport", "warn", "no viewport meta tag",
            'Add <meta name="viewport" content="width=device-width, initial-scale=1">.')
    elif re.search(r"user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(\.0)?\b", facts["viewport"], re.I):
        add("onpage", "viewport", "info", f"zoom is blocked: {facts['viewport']}", "Allow pinch-zoom; blocking it harms accessibility.")
    else:
        add("onpage", "viewport", "pass", facts["viewport"])
    lang = facts["lang"]
    if not lang:
        add("onpage", "html lang", "warn", "no lang attribute on <html>", 'Add lang to the <html> tag, for example <html lang="en">.')
    elif not LANG_RE.match(lang):
        add("onpage", "html lang", "warn", f"invalid language code: {lang}", "Use a BCP 47 code such as en, en-GB or hi-IN.")
    else:
        add("onpage", "html lang", "pass", lang)
    if not facts["charset"]:
        add("onpage", "charset", "info", "no charset declared in the HTML", '<meta charset="utf-8"> near the top of <head> avoids guessing.')

    # --- social previews
    og = facts["og"]
    missing_og = [k for k in ("og:title", "og:description", "og:image") if not og.get(k)]
    if not og:
        add("onpage", "social tags", "info", "no Open Graph tags",
            "Add og:title, og:description and og:image (and twitter:card) so shared links get a proper preview.")
    elif missing_og:
        add("onpage", "social tags", "info", "Open Graph tags present but missing " + ", ".join(missing_og),
            "Add the missing Open Graph tags so shared links get a complete preview.")
    else:
        add("onpage", "social tags", "pass", "og:title, og:description, og:image" + (", twitter:card" if facts["twitter_card"] else ""))

    # --- images
    imgs = facts["images"]
    if imgs:
        no_alt = [i["src"] or "(no src)" for i in imgs if i["alt"] is None]
        if no_alt:
            add("onpage", "image alt text", "warn", f"{len(no_alt)} of {len(imgs)} images have no alt attribute (for example {_list(no_alt, 2)})",
                'Describe each image in alt text, or use alt="" for purely decorative images.')
        else:
            add("onpage", "image alt text", "pass", f"all {len(imgs)} images have an alt attribute")
        no_dim = [i for i in imgs if not (i["width"] and i["height"])]
        if no_dim:
            add("onpage", "image dimensions", "info", f"{len(no_dim)} of {len(imgs)} images lack width and height attributes",
                "Set width and height so the page does not shift while images load.")

    # --- links
    links = [lk for lk in facts["links"] if lk["href"] and not lk["href"].startswith(("#", "javascript:", "mailto:", "tel:"))]
    if links:
        textless = [lk for lk in links if not lk["text"]]
        generic = [lk for lk in links if lk["text"].lower().strip(" .!>»") in GENERIC_ANCHORS]
        if textless:
            add("onpage", "link text", "warn", f"{len(textless)} of {len(links)} links have no text (for example {_list([lk['href'] for lk in textless], 2)})",
                "Give every link visible text or an image with alt text.")
        elif len(generic) >= 3:
            add("onpage", "link text", "info", f"{len(generic)} of {len(links)} links say things like \"read more\" or \"click here\"",
                "Descriptive link text tells readers and engines what the target is about.")
        else:
            add("onpage", "link text", "pass", f"{len(links)} links, all with text")

    # --- weight and speed proxies (a single sample, not a lab measurement)
    if response_ms is not None:
        if response_ms > SLOW_WARN_MS:
            add("onpage", "response time", "warn", f"{response_ms} ms to fetch the HTML (one request from this machine)",
                "Check server response time, caching and the CDN; re-measure from more than one location.")
        elif response_ms > SLOW_INFO_MS:
            add("onpage", "response time", "info", f"{response_ms} ms to fetch the HTML (one request from this machine)",
                "Re-measure from more than one location before acting on a single sample.")
        else:
            add("onpage", "response time", "pass", f"{response_ms} ms to fetch the HTML (one request)")
    if facts["blocking_scripts"] >= 4:
        add("onpage", "render-blocking scripts", "info", f"{facts['blocking_scripts']} external scripts in <head> without async, defer or type=module",
            "Load non-critical scripts with defer or async so the page can paint sooner.")

    # --- hreflang (only when the page declares alternates: a one-language site is not penalised)
    if facts["hreflangs"]:
        status, detail, fix = hreflang_row(facts["hreflangs"], url)
        add("indexing", "hreflang", status, detail, fix)
    return out


def same_url(a, b):
    """Whether two absolute URLs are the same page: scheme, host and query match; a trailing slash on the path does not matter."""
    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme.lower(), pa.netloc.lower(), _norm_path(a), pa.query) == (pb.scheme.lower(), pb.netloc.lower(), _norm_path(b), pb.query)


def hreflang_row(hreflangs, url):
    """Validate one page's hreflang annotations. Returns (status, detail, fix). Reciprocity needs other pages: see return_link_problem."""
    problems, advice = [], []
    codes = {}
    for code, href in hreflangs:
        codes.setdefault(code.lower(), set()).add(href.strip())
    bad = sorted({c for c, _ in hreflangs if not HREFLANG_RE.match(c.strip())})
    if bad:
        problems.append("invalid language code(s): " + _list(bad) + " (use a language such as en, optionally with a region such as en-GB, or x-default)")
    clash = sorted(c for c, hrefs in codes.items() if len(hrefs) > 1)
    if clash:
        problems.append("the same code points at different URLs: " + _list(clash))
    relative = [h for _, h in hreflangs if not (urlparse(h).scheme and urlparse(h).netloc)]
    if relative:
        problems.append(f"{len(relative)} relative URL(s), e.g. {relative[0]}")
    absolute = [h for _, h in hreflangs if urlparse(h).scheme and urlparse(h).netloc]
    if absolute and not any(same_url(h, url) for h in absolute):
        problems.append("the page does not list itself (every page in the set must include a self-referencing entry)")
    if problems:
        return ("warn", "; ".join(problems),
                "Fix the hreflang set: valid codes, absolute URLs, one URL per code, and a self-referencing entry on every page.")
    if "x-default" not in codes:
        advice.append("no x-default entry")
    if advice:
        return ("info", f"{len(codes)} language version(s) declared, valid; " + "; ".join(advice),
                "Add an x-default alternate (the fallback for visitors whose language you do not serve) if you have one.")
    return ("pass", f"{len(codes)} language version(s) declared, valid, self-referencing, with x-default", "")


def return_link_problem(source_url, alt_url, status, alt_hreflangs):
    """Why an alternate fails the return-link rule (it must link back to the page that names it), or None if it passes."""
    path = urlparse(alt_url).path or "/"
    if status == 0:
        return f"{path} could not be fetched"
    if not 200 <= status < 300:
        return f"{path} returns HTTP {status}"
    if not any(same_url(urljoin(alt_url, h), source_url) for _, h in alt_hreflangs):
        return f"{path} does not link back to {urlparse(source_url).path or '/'}"
    return None


def reciprocity_row(problems, checked, unverified=(), other_hosts=()):
    """Summarise the return-link checks. Returns (status, detail, fix). Alternates on other hosts are named, not fetched."""
    notes = []
    if unverified:
        notes.append(f"not verifiable (JavaScript shell): {_list(sorted(unverified))}")
    if other_hosts:
        notes.append(f"{len(other_hosts)} alternate host(s) not fetched (the checker contacts only the audited host): {_list(sorted(other_hosts))}")
    if problems:
        return ("warn", "; ".join(sorted(problems)[:6]) + (f"; and {len(problems) - 6} more" if len(problems) > 6 else "")
                + ("; " + "; ".join(notes) if notes else ""),
                "Every language version must link back to the page that links to it, or search engines may ignore the set. "
                "Add the missing return annotation to the alternate page.")
    if checked == 0:
        return ("info", "no same-host alternates to verify" + ("; " + "; ".join(notes) if notes else ""), "")
    return ("pass", f"{checked} alternate page(s) fetched, each links back" + ("; " + "; ".join(notes) if notes else ""), "")


def protocol_row(status, location, error, host):
    """The plain-HTTP version of the site (probe without following redirects). Returns (status, detail, fix)."""
    if error or status == 0:
        return ("info", "port 80 did not answer, so the HTTP-to-HTTPS redirect was not assessed (an HTTPS-only site is fine)", "")
    loc = (location or "").strip()
    if status in (301, 308) and loc.lower().startswith("https://"):
        return ("pass", f"http://{host}/ redirects permanently ({status}) to {loc}", "")
    if status in (302, 303, 307) and loc.lower().startswith("https://"):
        return ("warn", f"http://{host}/ redirects to HTTPS with a temporary {status}",
                "Use a permanent redirect (301 or 308) so engines consolidate on the HTTPS URL.")
    if 300 <= status < 400:
        return ("warn", f"http://{host}/ redirects ({status}) to {loc or 'an unknown location'}, which is not an HTTPS URL",
                "Redirect every http:// URL to its https:// equivalent in one permanent step.")
    if 200 <= status < 300:
        return ("warn", f"http://{host}/ answers {status} and serves the page over plain HTTP",
                "Redirect http:// to https:// with a 301 so there is one secure version, and so browsers stop warning visitors.")
    return ("info", f"http://{host}/ returned HTTP {status}", "")


def twin_host(host):
    """The www/apex counterpart of a host, or None when the idea does not apply (IPs, localhost, ports, deeper subdomains)."""
    h = host.lower()
    if not h or ":" in h or h == "localhost" or h.endswith((".localhost", ".test", ".local", ".internal")):
        return None
    labels = h.split(".")
    if labels[0] == "www" and len(labels) >= 3:
        return ".".join(labels[1:])
    second_level = len(labels) == 3 and len(labels[-1]) == 2 and labels[-2] in ("co", "com", "org", "net", "gov", "ac", "edu")
    if len(labels) == 2 or second_level:
        return "www." + h
    return None


def host_row(status, location, error, audited, twin):
    """Whether the www/apex twin of the audited host redirects to it. Returns (status, detail, fix)."""
    if error or status == 0:
        return ("info", f"{twin} did not respond, so there is no duplicate site there (or the request failed)", "")
    loc = (location or "").strip()
    if status in (301, 308) and urlparse(loc).netloc.lower() == audited.lower():
        return ("pass", f"{twin} redirects permanently ({status}) to {audited}", "")
    if status in (302, 303, 307) and urlparse(loc).netloc.lower() == audited.lower():
        return ("warn", f"{twin} redirects to {audited} with a temporary {status}",
                "Use a permanent redirect (301 or 308) so engines consolidate on one host.")
    if 300 <= status < 400:
        return ("warn", f"{twin} redirects ({status}) to {loc or 'an unknown location'}, not to {audited}",
                f"Pick one canonical host. If it is {audited}, redirect {twin} to it with a 301.")
    if 200 <= status < 300:
        return ("warn", f"both {audited} and {twin} serve the site, so every page exists at two URLs",
                f"Pick one canonical host and redirect the other to it with a 301 (and keep canonicals and the sitemap on the chosen host).")
    return ("info", f"{twin} returned HTTP {status}", "")


def duplicates(pages):
    """Cross-page checks. pages: {path: facts}. Returns [(area, check, status, detail, fix)]."""
    out = []
    for key, label, fix in (("title", "duplicate titles", "Give each page its own title."),
                            ("description", "duplicate descriptions", "Write a distinct description for each page.")):
        seen = {}
        for path, facts in pages.items():
            value = (facts.get(key) or "").strip().lower()
            if value:
                seen.setdefault(value, []).append(path)
        dup = {v: ps for v, ps in seen.items() if len(ps) > 1}
        if dup:
            detail = "; ".join(f"{_list(ps)} share \"{v[:60]}\"" for v, ps in dup.items())
            out.append(("onpage", label, "warn", detail, fix))
        elif len(pages) > 1:
            out.append(("onpage", label, "pass", f"{len(pages)} pages checked, all different", ""))
    return out
