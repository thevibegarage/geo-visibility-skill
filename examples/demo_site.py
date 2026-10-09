#!/usr/bin/env python3
"""A small, deliberately flawed fictional website ("Meridian CRM") for demoing and testing check_ai_readiness.py.

No real company is involved. Run it, then point the checker at it:

    python3 examples/demo_site.py &
    python3 geo-visibility/scripts/check_ai_readiness.py http://127.0.0.1:8765 \\
        --paths /pricing /features /blog/crm-for-agencies --issues-only

Flaws planted on purpose (the checker should report every one):
  * robots.txt disallows Claude-SearchBot (and GPTBot, which is only an "info" row: a training opt-out is a choice)
  * the "WAF" refuses PerplexityBot with HTTP 403
  * /pricing is an empty JavaScript app shell for every agent
  * /features is a shell for a default fetch but full HTML for crawlers (dynamic rendering: a pass, credited)
  * /blog/crm-for-agencies is full for Googlebot and everyone else but a shell for Bingbot
  * the homepage sets "nosnippet" (as an SEO plugin might) and carries no JSON-LD
  * every sitemap entry has the same lastmod date
  * the homepage, /features and the blog post share one meta description, and the blog post has an image with no alt text
  * no Bing Webmaster Tools verification tag and no llms.txt
Standard library only.
"""
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8765
SENTENCES = [
    "Meridian CRM keeps every client conversation, deal and invoice in one pipeline.",
    "Agencies with ten to two hundred people use it to see who owns each account and what happens next.",
    "Plans start at 29 dollars per user per month and include unlimited contacts and a REST API.",
    "Setup takes an afternoon: import contacts from a spreadsheet, connect email and invite the team.",
    "Reports show pipeline value by stage, win rate by source and the accounts that have gone quiet.",
    "Integrations cover email, calendar, invoicing and the chat tools agencies already use.",
    "Support answers within one business day and onboarding calls are included on every plan.",
    "Data lives in the EU by default and every plan includes single sign-on and audit logs.",
]
SHELL = ('<!doctype html><html lang="en"><head><title>Meridian CRM</title></head>'
         '<body><div id="root"></div><script src="/app.js"></script></body></html>')
BLOG_URLS = ["/blog/crm-for-agencies"] + [f"/blog/post-{n}" for n in range(1, 10)]
SITEMAP_URLS = ["/", "/pricing", "/features"] + BLOG_URLS


def words(n):
    """Exactly n words of plain text, deterministic."""
    out = []
    i = 0
    while len(out) < n:
        out.extend(SENTENCES[i % len(SENTENCES)].split())
        i += 1
    return " ".join(out[:n])


def page(host, path, title, h1, n_words, head="", extra=""):
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f"<title>{title}</title>"
            '<meta name="description" content="Meridian CRM is a CRM for mid-size agencies that want one pipeline, one inbox and one source of truth.">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<link rel="canonical" href="http://{host}{path}">{head}</head>'
            f"<body><h1>{h1}</h1><p>{words(n_words)}</p>{extra}</body></html>")


def respond(path, ua, host):
    """Return (status, content_type, body) for a request. Routing depends on the user agent, like many real sites."""
    path = path.split("?")[0]
    low = ua.lower()
    browser = "compatible" not in low
    if "perplexitybot" in low:  # a bot-protection rule refusing one crawler
        return 403, "text/plain", "Forbidden"
    if path == "/robots.txt":
        return 200, "text/plain", (
            "User-agent: Claude-SearchBot\nDisallow: /\n\n"
            "User-agent: GPTBot\nDisallow: /\n\n"
            "User-agent: *\nDisallow: /admin/\n\n"
            f"Sitemap: http://{host}/sitemap.xml\n")
    if path == "/sitemap.xml":
        entries = "".join(f"<url><loc>http://{host}{u}</loc><lastmod>2026-03-02</lastmod></url>" for u in SITEMAP_URLS)
        return 200, "application/xml", ("<?xml version='1.0' encoding='UTF-8'?>"
                                        f"<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>{entries}</urlset>")
    if path == "/":
        return 200, "text/html", page(host, path, "Meridian CRM: the CRM for mid-size agencies", "Meridian CRM", 400,
                                      head='<meta name="robots" content="nosnippet">')
    if path == "/pricing":
        return 200, "text/html", SHELL
    if path == "/features":
        if browser:
            return 200, "text/html", SHELL
        return 200, "text/html", page(host, path, "Meridian CRM features for agencies", "Features", 520)
    if path in BLOG_URLS:
        if "bingbot" in low:
            return 200, "text/html", SHELL
        return 200, "text/html", page(host, path, "CRM for agencies: what to look for", "CRM for agencies", 640,
                                      extra='<img src="/team.png" width="600" height="400">')
    return 404, "text/plain", "Not found"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        status, ctype, body = respond(self.path, self.headers.get("User-Agent", ""), self.headers.get("Host", f"127.0.0.1:{PORT}"))
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def make_server(port=PORT):
    """A ThreadingHTTPServer on 127.0.0.1 (port 0 picks a free port)."""
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve_in_background(port=0):
    server = make_server(port)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    return server


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    server = make_server(port)
    print(f"Meridian CRM demo site on http://127.0.0.1:{server.server_address[1]}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
