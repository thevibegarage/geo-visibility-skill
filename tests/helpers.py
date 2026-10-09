"""Shared test helpers: load the scripts by path and run a throwaway local HTTP site."""
import contextlib
import gzip
import importlib.util
import io
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# GEO_SKILL_DIR lets the suite run against another copy of the skill (e.g. to prove a test fails on the old code)
SKILL = os.environ.get("GEO_SKILL_DIR") or os.path.join(ROOT, "geo-visibility")


def load_script(name):
    path = os.path.join(SKILL, "scripts", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ck = load_script("check_ai_readiness")
st = load_script("score_tracker")


def asset(*parts):
    with open(os.path.join(SKILL, *parts), encoding="utf-8") as fh:
        return fh.read()


def lorem(n):
    return " ".join(f"word{i % 50}" for i in range(n))


def html_page(title="Acme Widgets: invoice reconciliation", words=400, h1="Acme Widgets", head="", body_extra="", jsonld=True, path="/"):
    ld = ('<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Acme"}</script>'
          if jsonld else "")
    # {BASE} is replaced by the test server with its own address, so the canonical URL matches the host being audited
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{title}</title>"
            f"<meta name='description' content='{title}. Acme makes invoice reconciliation software for chartered accountants in India.'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<meta property='og:title' content='Acme'><meta property='og:description' content='Acme'><meta property='og:image' content='{{BASE}}/og.png'>"
            f"<link rel='canonical' href='{{BASE}}{path}'>{head}{ld}</head>"
            f"<body><h1>{h1}</h1><p>{lorem(words)}</p>{body_extra}</body></html>")


SHELL = "<!doctype html><html><head><title>Acme</title></head><body><div id=\"root\"></div><script src=\"/app.js\"></script></body></html>"
ROBOTS_OK = "User-agent: *\nDisallow: /admin/\n\nSitemap: {base}/sitemap.xml\n"


def sitemap_xml(urls, lastmods=None):
    items = []
    for i, u in enumerate(urls):
        lm = f"<lastmod>{lastmods[i]}</lastmod>" if lastmods else ""
        items.append(f"<url><loc>{u}</loc>{lm}</url>")
    return "<?xml version='1.0'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>" + "".join(items) + "</urlset>"


class Site:
    """A local HTTP site. routes: {path: body | (status, headers, body)}. handler(path, ua) may return the same to override."""

    def __init__(self, routes=None, handler=None):
        self.routes, self.handler = dict(routes or {}), handler
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                ua = self.headers.get("User-Agent", "")
                path = self.path.split("?")[0]
                r = outer.handler(self.path, ua) if outer.handler else None
                if r is None:
                    r = outer.routes.get(path)
                if r is None:
                    r = (404, {}, "not found")
                if not isinstance(r, tuple):
                    r = (200, {}, r)
                code, headers, body = r
                if isinstance(body, str):
                    body = body.replace("{BASE}", outer.base).encode("utf-8")
                self.send_response(code)
                items = headers.items() if isinstance(headers, dict) else headers
                if not any(k.lower() == "content-type" for k, _ in items):
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                for k, v in items:
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def good_routes():
    """Routes of a healthy site: every check should pass. good_site() fills in robots.txt and the sitemap."""
    return {
        "/": html_page(head="<meta name='msvalidate.01' content='ABC123'>"),
        "/pricing": html_page(title="Acme pricing and plans for teams", h1="Pricing", path="/pricing"),
        "/robots.txt": (200, {"Content-Type": "text/plain"}, ROBOTS_OK),
        "/llms.txt": (200, {"Content-Type": "text/plain"}, "# Acme\n> Widgets\n"),
    }


def good_site(extra=None, handler=None, sitemap_paths=("/", "/pricing")):
    """Return a Site whose robots/sitemap use its own base URL. extra routes override the defaults;
    a callable value is called with the site base URL."""
    site = Site(handler=handler)
    routes = good_routes()
    routes["/robots.txt"] = (200, {"Content-Type": "text/plain"}, ROBOTS_OK.format(base=site.base))
    routes["/sitemap.xml"] = (200, {"Content-Type": "application/xml"},
                              sitemap_xml([site.base + p for p in sitemap_paths]))
    for k, v in (extra or {}).items():
        routes[k] = v(site.base) if callable(v) else v
    site.routes = routes
    return site


def by_check(res, prefix):
    return [f for f in res["findings"] if f["check"].startswith(prefix)]


def one(res, name):
    rows = [f for f in res["findings"] if f["check"] == name]
    assert len(rows) == 1, f"expected exactly one finding named {name!r}, got {[f['check'] for f in res['findings']]}"
    return rows[0]


def run_main(mod, argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = mod.main(argv)
    return code, buf.getvalue()


def closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def gz(text):
    return gzip.compress(text.encode("utf-8"))
