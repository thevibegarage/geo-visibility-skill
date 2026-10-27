"""Tests for the bounded crawl (geo-visibility/scripts/link_crawl.py).

The first half drives the crawl with a fake site, so budgets, hosts, robots rules and redirects are checked exactly. The second
half runs the checker end to end against a local HTTP site. Security claims about the crawl live in test_security.py.
"""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlsplit

from helpers import SKILL, Site, ck, good_site, html_page, run_main

sys.path.insert(0, os.path.join(SKILL, "scripts"))
import link_crawl as lc  # noqa: E402

BASE = "https://example.com"


# ---------------------------------------------------------------------------------------------
# A fake site and small builders
# ---------------------------------------------------------------------------------------------

def html(*hrefs, text=""):
    return "<html><body><p>" + text + "</p>" + "".join(f'<a href="{h}">link</a>' for h in hrefs) + "</body></html>"


def redirect(code, location):
    return ("redirect", code, location)


def neterr(message):
    return ("neterr", message)


class FakeSite:
    """Stands in for the network: pages is {"/path": html text | status code | redirect(...) | neterr(...)}; unknown paths are 404.

    It refuses a request to any other host, so a test that passes proves the crawl never asked for one.
    """

    def __init__(self, pages):
        self.pages, self.requests = pages, []

    def get(self, url):
        parts = urlsplit(url)
        assert parts.netloc == "example.com", f"requested another host: {url}"
        self.requests.append(url)
        entry = self.pages.get(parts.path + (f"?{parts.query}" if parts.query else ""), 404)
        if isinstance(entry, str):
            return 200, "", entry, ""
        if isinstance(entry, int):
            return entry, "", None, ""
        if entry[0] == "neterr":
            return 0, "", None, entry[1]
        return entry[1], entry[2], None, ""


def run(pages, budget=50, blocked=(), pause=None):
    """Crawl a fake site. blocked: path prefixes robots.txt disallows. A page containing SHELL counts as a JavaScript shell."""
    fake = FakeSite(pages)
    res = lc.crawl(BASE + "/", fake.get, lambda u: not any(urlsplit(u).path.startswith(b) for b in blocked),
                   lambda h: "SHELL" in h, budget, pause)
    return res, fake


def node(res, path):
    return res["nodes"][BASE + path]


def rows(res, sitemap=None):
    """{check name: (status, detail, fix)} for the crawl's report rows."""
    return {check: (status, detail, fix) for _, check, status, detail, fix in lc.findings(res, sitemap)}


def sitemap_of(*paths, complete=True):
    return {"urls": [BASE + p for p in paths], "complete": complete}


# ---------------------------------------------------------------------------------------------
# URLs and links
# ---------------------------------------------------------------------------------------------

class Normalize(unittest.TestCase):
    def test_one_spelling_per_url(self):
        self.assertEqual(lc.normalize("HTTPS://Example.COM:443/a/b#frag"), "https://example.com/a/b")
        self.assertEqual(lc.normalize("http://example.com:80"), "http://example.com/")
        self.assertEqual(lc.normalize("http://example.com:8080/x?a=1&b=2"), "http://example.com:8080/x?a=1&b=2")
        self.assertEqual(lc.normalize("http://[::1]:8080/x"), "http://[::1]:8080/x")

    def test_a_trailing_slash_is_a_different_url(self):
        self.assertNotEqual(lc.normalize("https://example.com/a/"), lc.normalize("https://example.com/a"))

    def test_characters_a_request_cannot_carry_are_encoded(self):
        self.assertEqual(lc.normalize("https://example.com/a b/café?q=a b"), "https://example.com/a%20b/caf%C3%A9?q=a%20b")
        once = lc.normalize("https://example.com/a b/%2F?x=%7E")
        self.assertEqual(lc.normalize(once), once)  # idempotent, and existing escapes survive
        self.assertIn("%2F", once)

    def test_only_plain_http_urls_are_links(self):
        for bad in ("mailto:a@example.com", "tel:+911234", "javascript:void(0)", "data:text/html,x", "ftp://example.com/x", "",
                    "//cdn.example.com/x", "/relative", "http://user:pw@example.com/", "http://[bad", "http://example.com:99999/"):
            self.assertIsNone(lc.normalize(bad), bad)


class ExtractLinks(unittest.TestCase):
    PAGE = "https://example.com/a/b"

    def test_relative_links_resolve_in_document_order_without_duplicates(self):
        got = lc.extract_links(html("c", "../d", "/e", "https://other.com/f", "c", "/e#top"), self.PAGE)
        self.assertEqual(got, ["https://example.com/a/c", "https://example.com/d", "https://example.com/e", "https://other.com/f"])

    def test_things_that_are_not_links_are_ignored(self):
        got = lc.extract_links(html("mailto:a@b.com", "tel:1", "javascript:go()", "#top", "", "b", self.PAGE, self.PAGE + "#x", "/real"), self.PAGE)
        self.assertEqual(got, ["https://example.com/real"])  # also not the page itself, with or without a fragment

    def test_a_scheme_is_judged_before_the_link_is_joined_to_the_page(self):
        """Python 3.8's urljoin reads "tel:5551234" as a relative path, because digits after a colon look like a port. CI found that
        on 3.8; this simulates it on any version, so the crawler cannot turn a phone link into a request for /a/tel:5551234."""
        real = lc.urljoin

        def py38_urljoin(base, href):
            return real(base, "./" + href) if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:\d+$", href) else real(base, href)

        with mock.patch.object(lc, "urljoin", py38_urljoin):
            got = lc.extract_links(html("tel:5551234567", "sms:12345", "whatsapp:1", "mailto:a@b.com", "javascript:void(0)", "/real"), self.PAGE)
        self.assertEqual(got, ["https://example.com/real"])

    def test_base_href_is_honoured(self):
        page = '<html><head><base href="/docs/"></head><body><a href="intro">x</a><a href="/top">y</a></body></html>'
        self.assertEqual(lc.extract_links(page, self.PAGE), ["https://example.com/docs/intro", "https://example.com/top"])

    def test_area_links_count_and_link_tags_do_not(self):
        page = '<link rel="next" href="/next"><map><area href="/zone"></map><a name="anchor">no href</a>'
        self.assertEqual(lc.extract_links(page, self.PAGE), ["https://example.com/zone"])

    def test_broken_markup_and_hostile_hrefs_do_not_raise(self):
        self.assertEqual(lc.extract_links('<a href="/ok">x</a><a href="http://[bad">y</a><a href="/x', self.PAGE),
                         ["https://example.com/ok"])


# ---------------------------------------------------------------------------------------------
# The crawl itself
# ---------------------------------------------------------------------------------------------

class Engine(unittest.TestCase):
    def test_click_depth_is_the_shortest_route(self):
        res, _ = run({"/": html("/x", "/z"), "/x": html("/y"), "/y": html("/z"), "/z": html("/w"), "/w": html()})
        self.assertEqual({p: node(res, p)["depth"] for p in ("/", "/x", "/y", "/z", "/w")},
                         {"/": 0, "/x": 1, "/y": 2, "/z": 1, "/w": 2})  # /z is one click away, not three

    def test_a_redirect_costs_no_click(self):
        res, _ = run({"/": html("/old"), "/old": redirect(301, "/new"), "/new": html("/deeper"), "/deeper": html()})
        self.assertEqual((node(res, "/old")["depth"], node(res, "/new")["depth"], node(res, "/deeper")["depth"]), (1, 1, 2))

    def test_a_redirect_target_that_is_also_linked_directly_is_fetched_once(self):
        res, fake = run({"/": html("/old", "/new"), "/old": redirect(301, "/new"), "/new": html()})
        self.assertEqual(sorted(fake.requests), sorted({BASE + "/", BASE + "/old", BASE + "/new"}))
        self.assertEqual(node(res, "/new")["depth"], 1)

    def test_every_url_is_requested_once_even_in_a_link_loop(self):
        res, fake = run({"/": html("/a", "/b"), "/a": html("/b", "/", "/a"), "/b": html("/a", "/")})
        self.assertEqual(len(fake.requests), len(set(fake.requests)))
        self.assertEqual(res["requests"], 3)
        self.assertTrue(res["complete"])

    def test_the_budget_is_a_hard_limit(self):
        chain = {"/": html("/p1")}
        chain.update({f"/p{i}": html(f"/p{i + 1}") for i in range(1, 10)})
        res, fake = run(chain, budget=4)
        self.assertEqual((len(fake.requests), res["requests"]), (4, 4))
        self.assertFalse(res["complete"])
        self.assertEqual(res["unfetched"], [BASE + "/p4"])

    def test_a_crawl_that_fits_the_budget_exactly_is_complete(self):
        pages = {"/": html("/a", "/b"), "/a": html(), "/b": html()}
        self.assertTrue(run(pages, budget=3)[0]["complete"])
        self.assertFalse(run(pages, budget=2)[0]["complete"])

    def test_the_crawl_has_a_time_limit_as_well(self):
        ticks = iter(range(100))
        fake = FakeSite({"/": html("/a", "/b", "/c"), "/a": html(), "/b": html(), "/c": html()})
        res = lc.crawl(BASE + "/", fake.get, lambda u: True, lambda h: False, 50, max_seconds=3, clock=lambda: next(ticks))
        self.assertEqual(res["requests"], 2)  # the clock reads 0 at the start, 1 and 2 before the requests, 3 before the third
        self.assertEqual(res["stopped"], "time limit of 3 seconds reached")
        self.assertFalse(res["complete"])
        self.assertEqual(res["unfetched"], [BASE + "/b", BASE + "/c"])

    def test_the_default_time_limit_is_five_minutes(self):
        self.assertEqual(lc.MAX_SECONDS, 300)

    def test_redirect_hops_use_the_budget(self):
        res, fake = run({"/": html("/a"), "/a": redirect(301, "/b"), "/b": redirect(301, "/c"), "/c": html()}, budget=3)
        self.assertEqual(len(fake.requests), 3)
        self.assertEqual(res["unfetched"], [BASE + "/c"])

    def test_urls_robots_txt_disallows_are_never_requested_and_cost_nothing(self):
        res, fake = run({"/": html("/admin/x", "/ok"), "/ok": html(), "/admin/x": html()}, blocked=("/admin/",), budget=2)
        self.assertNotIn(BASE + "/admin/x", fake.requests)
        self.assertTrue(node(res, "/admin/x")["blocked"])
        self.assertEqual(res["requests"], 2)  # the blocked URL did not take a request from the budget
        self.assertTrue(res["complete"])

    def test_another_host_is_never_requested(self):
        res, fake = run({"/": html("https://other.com/x", "https://www.example.com/y", "/out"),
                         "/out": redirect(302, "https://elsewhere.net/landing")})
        self.assertEqual(res["external_hosts"], ["elsewhere.net", "other.com", "www.example.com"])
        self.assertEqual(len(fake.requests), 2)  # FakeSite would have raised on any other host

    def test_the_insecure_version_of_the_same_host_is_followed_to_its_redirect(self):
        res, _ = run({"/": html("http://example.com/x"), "/x": redirect(301, "https://example.com/x/")})
        self.assertEqual(res["nodes"]["http://example.com/x"]["target"], "https://example.com/x/")
        self.assertIn("https://example.com/x/", res["nodes"])  # the redirect was followed to the secure URL

    def test_a_429_ends_the_crawl_at_once(self):
        res, fake = run({"/": html("/a", "/b", "/c"), "/a": html(), "/b": 429, "/c": html()})
        self.assertEqual(fake.requests, [BASE + "/", BASE + "/a", BASE + "/b"])
        self.assertIn("429", res["stopped"])
        self.assertFalse(res["complete"])
        self.assertEqual(res["unfetched"], [BASE + "/c"])

    def test_only_html_pages_are_read_for_links(self):
        res, _ = run({"/": html("/file.pdf"), "/file.pdf": 200})
        self.assertFalse(node(res, "/file.pdf")["html"])
        self.assertEqual(node(res, "/file.pdf")["links"], [])

    def test_javascript_shells_are_flagged(self):
        res, _ = run({"/": html("/app"), "/app": html("/hidden", text="SHELL")})
        self.assertEqual((node(res, "/")["shell"], node(res, "/app")["shell"]), (False, True))

    def test_the_crawler_pauses_between_requests_but_not_before_the_first(self):
        calls = []
        res, _ = run({"/": html("/a", "/b"), "/a": html(), "/b": html()}, pause=lambda: calls.append(1))
        self.assertEqual(len(calls), res["requests"] - 1)

    def test_network_errors_are_recorded(self):
        res, _ = run({"/": html("/slow"), "/slow": neterr("timed out")})
        self.assertEqual((node(res, "/slow")["status"], node(res, "/slow")["error"]), (0, "timed out"))

    def test_an_unusable_redirect_target_is_kept_but_not_followed(self):
        res, fake = run({"/": html("/a"), "/a": redirect(301, "mailto:x@example.com")})
        self.assertIsNone(node(res, "/a")["target"])
        self.assertEqual(len(fake.requests), 2)

    def test_a_blocked_start_page_is_recorded_not_requested(self):
        res, fake = run({"/": html("/a")}, blocked=("/",))
        self.assertEqual((fake.requests, res["requests"], res["complete"]), ([], 0, True))
        self.assertTrue(node(res, "/")["blocked"])


class Follow(unittest.TestCase):
    def outcome(self, pages, path="/a", **kw):
        res, _ = run(pages, **kw)
        return lc.follow(res, BASE + path)

    def test_a_chain_lists_every_hop_and_where_it_ends(self):
        o = self.outcome({"/": html("/a"), "/a": redirect(301, "/b"), "/b": redirect(302, "/c"), "/c": html()})
        self.assertEqual([(h[1]) for h in o["hops"]], [301, 302])
        self.assertEqual((o["final"], o["status"], o["problem"]), (BASE + "/c", 200, None))

    def test_a_loop_is_detected_including_a_self_redirect(self):
        o = self.outcome({"/": html("/a"), "/a": redirect(301, "/b"), "/b": redirect(301, "/a")})
        self.assertEqual(o["problem"], "loop")
        self.assertEqual(self.outcome({"/": html("/a"), "/a": redirect(301, "/a")})["problem"], "loop")

    def test_leaving_the_site_ends_the_chain(self):
        o = self.outcome({"/": html("/a"), "/a": redirect(301, "https://other.com/x")})
        self.assertEqual((o["problem"], len(o["hops"])), ("off-site", 1))

    def test_robots_and_the_budget_leave_a_chain_unfinished(self):
        pages = {"/": html("/a"), "/a": redirect(301, "/private/x"), "/private/x": html()}
        self.assertEqual(self.outcome(pages, blocked=("/private/",))["problem"], "blocked")
        self.assertEqual(self.outcome(pages, budget=2)["problem"], "not-fetched")

    def test_a_redirect_without_a_location_is_a_plain_error(self):
        o = self.outcome({"/": html("/a"), "/a": redirect(301, "")})
        self.assertEqual((o["problem"], o["status"], o["hops"]), (None, 301, []))


# ---------------------------------------------------------------------------------------------
# Report rows
# ---------------------------------------------------------------------------------------------

class BrokenLinks(unittest.TestCase):
    def test_a_missing_page_is_a_failure_that_names_the_target_and_where_it_is_linked(self):
        res, _ = run({"/": html("/pricing", "/gone"), "/pricing": html("/gone", "/"), "/gone": 404})
        status, detail, fix = rows(res)[lc.BROKEN]
        self.assertEqual(status, "fail")
        self.assertIn("/gone (HTTP 404, from /, /pricing)", detail)
        self.assertTrue(fix)

    def test_410_and_other_client_errors_are_broken_too(self):
        for code in (400, 404, 410, 451):
            res, _ = run({"/": html("/x"), "/x": code})
            self.assertEqual(rows(res)[lc.BROKEN][0], "fail", code)

    def test_bot_protection_rate_limits_and_server_errors_are_unverified_not_broken(self):
        for code in (401, 403, 500, 503):
            res, _ = run({"/": html("/x"), "/x": code})
            status, detail, fix = rows(res)[lc.BROKEN]
            self.assertEqual(status, "warn", code)
            self.assertIn("could not be verified", detail)
            self.assertIn("bot protection", fix)

    def test_a_network_error_is_unverified_and_says_why(self):
        res, _ = run({"/": html("/x"), "/x": neterr("timed out")})
        status, detail, _ = rows(res)[lc.BROKEN]
        self.assertEqual(status, "warn")
        self.assertIn("timed out", detail)

    def test_a_link_that_redirects_to_a_missing_page_is_broken(self):
        res, _ = run({"/": html("/moved"), "/moved": redirect(301, "/gone"), "/gone": 404})
        status, detail, _ = rows(res)[lc.BROKEN]
        self.assertEqual(status, "fail")
        self.assertIn("/moved -> /gone (HTTP 404", detail)

    def test_broken_links_outrank_unverified_ones_and_the_row_still_mentions_both(self):
        res, _ = run({"/": html("/gone", "/blocked"), "/gone": 404, "/blocked": 403})
        status, detail, _ = rows(res)[lc.BROKEN]
        self.assertEqual(status, "fail")
        self.assertIn("1 more could not be verified", detail)

    def test_healthy_links_pass_and_the_count_is_honest(self):
        res, _ = run({"/": html("/a", "/b"), "/a": html(), "/b": html()})
        status, detail, _ = rows(res)[lc.BROKEN]
        self.assertEqual((status, detail), ("pass", "2 internal link target(s) checked, none broken"))

    def test_targets_that_were_not_checked_are_counted_separately(self):
        res, _ = run({"/": html("/a", "/admin/x", "/c", "/d"), "/a": html(), "/c": html(), "/d": html()}, blocked=("/admin/",), budget=3)
        detail = rows(res)[lc.BROKEN][1]
        self.assertIn("none broken", detail)
        self.assertIn("2 not checked", detail)  # one blocked by robots.txt, one beyond the limit

    def test_a_long_list_is_shortened(self):
        res, _ = run({"/": html(*[f"/g{i}" for i in range(7)])})
        detail = rows(res)[lc.BROKEN][1]
        self.assertTrue(detail.startswith("7 internal link target(s) are broken"))
        self.assertIn("and 4 more", detail)


class Redirects(unittest.TestCase):
    def chain(self, hops):
        """A page that links to /r0, which redirects through `hops` redirects to a real page."""
        pages = {"/": html("/r0"), "/end": html()}
        for i in range(hops):
            pages[f"/r{i}"] = redirect(301, f"/r{i + 1}" if i + 1 < hops else "/end")
        return pages

    def test_two_redirects_are_a_warning_that_shows_the_chain(self):
        res, _ = run({"/": html("/product"), "/product": redirect(301, "/products"), "/products": redirect(302, "/features"),
                      "/features": html()})
        status, detail, fix = rows(res)[lc.CHAINS]
        self.assertEqual(status, "warn")
        self.assertIn("/product (301) -> /products (302) -> /features (from /)", detail)
        self.assertTrue(fix)

    def test_five_redirects_warn_and_six_fail(self):
        self.assertEqual(rows(run(self.chain(lc.MAX_REDIRECTS))[0])[lc.CHAINS][0], "warn")
        status, detail, _ = rows(run(self.chain(lc.MAX_REDIRECTS + 1))[0])[lc.CHAINS]
        self.assertEqual(status, "fail")
        self.assertIn(f"{lc.MAX_REDIRECTS + 1} redirects", detail)

    def test_a_redirect_loop_is_a_failure(self):
        res, _ = run({"/": html("/a"), "/a": redirect(301, "/b"), "/b": redirect(301, "/a")})
        status, detail, _ = rows(res)[lc.CHAINS]
        self.assertEqual(status, "fail")
        self.assertIn("loop", detail)

    def test_one_redirect_is_information_with_a_fix_not_a_warning(self):
        res, _ = run({"/": html("/a", "/b"), "/a": redirect(301, "/a/"), "/a/": html(), "/b": redirect(302, "/b/"), "/b/": html()})
        r = rows(res)
        self.assertEqual(r[lc.CHAINS][0], "pass")
        status, detail, fix = r[lc.SINGLE_REDIRECTS]
        self.assertEqual(status, "info")
        self.assertIn("2 internal link target(s) redirect once (1 permanently, 1 temporarily)", detail)
        self.assertTrue(fix)

    def test_no_redirects_means_no_redirect_rows_beyond_the_pass(self):
        r = rows(run({"/": html("/a"), "/a": html()})[0])
        self.assertEqual(r[lc.CHAINS][0], "pass")
        self.assertNotIn(lc.SINGLE_REDIRECTS, r)

    def test_a_redirect_to_another_site_is_not_a_chain_or_a_single_redirect_finding(self):
        r = rows(run({"/": html("/out"), "/out": redirect(301, "https://other.com/x")})[0])
        self.assertEqual(r[lc.CHAINS][0], "pass")
        self.assertNotIn(lc.SINGLE_REDIRECTS, r)


class ClickDepth(unittest.TestCase):
    def depth_chain(self, n):
        pages = {"/": html("/d1")}
        pages.update({f"/d{i}": html(f"/d{i + 1}") for i in range(1, n)})
        pages[f"/d{n}"] = html()
        return pages

    def test_three_clicks_is_fine(self):
        status, detail, _ = rows(run(self.depth_chain(3))[0])[lc.DEPTH]
        self.assertEqual(status, "pass")
        self.assertIn("3 click(s)", detail)

    def test_four_clicks_is_reported_as_information_labelled_a_rule_of_thumb(self):
        status, detail, fix = rows(run(self.depth_chain(4))[0])[lc.DEPTH]
        self.assertEqual(status, "info")
        self.assertIn("/d4 (4)", detail)
        self.assertIn("rule of thumb, not a search-engine rule", detail)
        self.assertTrue(fix)

    def test_only_pages_that_could_be_read_count(self):
        status, _, _ = rows(run({"/": html("/a"), "/a": html("/b"), "/b": html("/c"), "/c": 404})[0])[lc.DEPTH]
        self.assertEqual(status, "pass")  # the broken link at depth 3 is not a page


class Orphans(unittest.TestCase):
    SITE = {"/": html("/a", "/b"), "/a": html(), "/b": html()}

    def test_a_sitemap_url_nothing_links_to_is_reported(self):
        res, _ = run(self.SITE)
        status, detail, fix = rows(res, sitemap_of("/", "/a", "/b", "/lonely", "/also-lonely"))[lc.ORPHANS]
        self.assertEqual(status, "warn")
        self.assertIn("2 sitemap URL(s) have no internal link pointing at them: /lonely; /also-lonely", detail)
        self.assertTrue(fix)

    def test_when_everything_is_linked_it_passes(self):
        res, _ = run(self.SITE)
        self.assertEqual(rows(res, sitemap_of("/", "/a", "/b"))[lc.ORPHANS][0], "pass")

    def test_a_trailing_slash_or_the_other_scheme_does_not_make_a_page_an_orphan(self):
        res, _ = run({"/": html("/about/"), "/about/": html()})
        sm = {"urls": [BASE + "/about", "http://example.com/about/"], "complete": True}
        self.assertEqual(rows(res, sm)[lc.ORPHANS][0], "pass")

    def test_a_page_reached_only_through_a_redirect_is_not_an_orphan(self):
        res, _ = run({"/": html("/old"), "/old": redirect(301, "/new"), "/new": html()})
        self.assertEqual(rows(res, sitemap_of("/new"))[lc.ORPHANS][0], "pass")

    def test_sitemap_urls_on_other_hosts_are_ignored(self):
        res, _ = run(self.SITE)
        sm = {"urls": ["https://blog.example.com/post", "https://other.com/", BASE + "/a"], "complete": True}
        self.assertEqual(rows(res, sm)[lc.ORPHANS][0], "pass")

    def test_not_assessed_when_the_crawl_stopped_early(self):
        res, _ = run(self.SITE, budget=2)
        status, detail, fix = rows(res, sitemap_of("/", "/a", "/b", "/lonely"))[lc.ORPHANS]
        self.assertEqual(status, "info")
        self.assertIn("not assessed", detail)
        self.assertIn("--crawl", fix)

    def test_not_assessed_when_a_page_builds_its_links_with_javascript(self):
        res, _ = run({"/": html("/app"), "/app": html(text="SHELL")})
        status, detail, _ = rows(res, sitemap_of("/", "/app", "/lonely"))[lc.ORPHANS]
        self.assertEqual(status, "info")
        self.assertIn("show under 50 words without JavaScript", detail)
        self.assertIn("/app", detail)

    def test_not_assessed_without_a_sitemap(self):
        status, detail, _ = rows(run(self.SITE)[0], None)[lc.ORPHANS]
        self.assertEqual(status, "info")
        self.assertIn("no sitemap", detail)

    def test_a_partly_read_sitemap_index_is_disclosed(self):
        res, _ = run(self.SITE)
        self.assertIn("only partly read", rows(res, sitemap_of("/", "/lonely", complete=False))[lc.ORPHANS][1])
        self.assertIn("only partly read", rows(res, sitemap_of("/", "/a", complete=False))[lc.ORPHANS][1])


class Summary(unittest.TestCase):
    def test_it_states_what_was_covered(self):
        res, _ = run({"/": html("/a", "/admin/x", "https://other.com/"), "/a": html("/b"), "/b": html()}, blocked=("/admin/",))
        status, detail, fix = rows(res)[lc.SUMMARY]
        self.assertEqual((status, fix), ("info", ""))
        for text in ("3 HTML page(s) read in 3 request(s) (limit 50)", "3 internal links", "2 click(s) from the start",
                     "1 URL(s) not requested because robots.txt disallows Googlebot", "1 other host(s) linked"):
            self.assertIn(text, detail)

    def test_an_incomplete_crawl_says_so_and_suggests_a_larger_limit(self):
        res, _ = run({"/": html("/a", "/b", "/c"), "/a": html(), "/b": html(), "/c": html()}, budget=2)
        status, detail, fix = rows(res)[lc.SUMMARY]
        self.assertIn("not requested because the limit was reached", detail)
        self.assertIn("larger --crawl", fix)

    def test_the_time_limit_is_reported(self):
        ticks = iter(range(100))
        fake = FakeSite({"/": html("/a"), "/a": html()})
        res = lc.crawl(BASE + "/", fake.get, lambda u: True, lambda h: False, 50, max_seconds=2, clock=lambda: next(ticks))
        self.assertEqual(res["requests"], 1)
        self.assertIn("stopped: time limit of 2 seconds reached", rows(res)[lc.SUMMARY][1])

    def test_a_crawl_that_never_got_to_request_the_start_page_still_reports(self):
        res = lc.crawl(BASE + "/", FakeSite({}).get, lambda u: True, lambda h: False, 0)
        r = rows(res)
        self.assertEqual(list(r), [lc.SUMMARY])
        self.assertIn("stopped before it requested the start page", r[lc.SUMMARY][1])
        self.assertEqual(lc.report_data(res)["pages"], [])

    def test_a_429_is_reported(self):
        res, _ = run({"/": html("/a"), "/a": 429})
        self.assertIn("stopped: HTTP 429", rows(res)[lc.SUMMARY][1])

    def test_a_site_whose_links_need_javascript_gets_only_the_summary_and_an_explanation(self):
        res, _ = run({"/": html(text="SHELL")})
        r = rows(res)
        self.assertEqual(list(r), [lc.SUMMARY])
        self.assertIn("no internal links were found", r[lc.SUMMARY][1])

    def test_a_start_page_googlebot_cannot_read_is_explained(self):
        self.assertIn("HTTP 403", rows(run({"/": 403})[0])[lc.SUMMARY][1])
        self.assertIn("network error", rows(run({"/": neterr("refused")})[0])[lc.SUMMARY][1])
        self.assertIn("robots.txt disallows Googlebot from the start page", rows(run({"/": html("/a")}, blocked=("/",))[0])[lc.SUMMARY][1])


class RowContract(unittest.TestCase):
    PAGES = {"/": html("/gone", "/blocked", "/product", "/moved", "/admin/x", "/d1"), "/gone": 404, "/blocked": 403,
             "/product": redirect(301, "/products"), "/products": redirect(301, "/features"), "/features": html(),
             "/moved": redirect(301, "/features"),
             "/d1": html("/d2"), "/d2": html("/d3"), "/d3": html("/d4"), "/d4": html()}

    def test_every_warning_and_failure_carries_a_fix_and_every_row_is_in_the_links_area(self):
        res, _ = run(self.PAGES, blocked=("/admin/",))
        found = lc.findings(res, sitemap_of("/", "/lonely"))
        self.assertGreaterEqual(len(found), 6)
        for area, check, status, detail, fix in found:
            self.assertEqual(area, lc.AREA)
            self.assertIn(status, ("pass", "info", "warn", "fail"), check)
            if status in ("warn", "fail"):
                self.assertTrue(fix, f"{check} has no fix")
            self.assertTrue(detail, check)

    def test_the_json_data_is_plain_data_with_the_link_graph(self):
        res, _ = run(self.PAGES, blocked=("/admin/",))
        data = json.loads(json.dumps(lc.report_data(res, sitemap_of("/", "/lonely"))))
        by_url = {p["url"]: p for p in data["pages"]}
        self.assertEqual(by_url[BASE + "/d4"]["depth"], 4)
        self.assertEqual(by_url[BASE + "/features"]["inbound"], 0)  # reached by redirect only, no page links to it
        self.assertEqual(by_url[BASE + "/product"]["redirects_to"], BASE + "/products")
        self.assertTrue(by_url[BASE + "/admin/x"]["blocked"])
        self.assertEqual(data["orphans"], [BASE + "/lonely"])
        self.assertEqual((data["budget"], data["requests"], data["complete"]), (50, res["requests"], True))


# ---------------------------------------------------------------------------------------------
# The checker, end to end against a local HTTP site
# ---------------------------------------------------------------------------------------------

def page(title, *links, path="/"):
    return html_page(title=title, body_extra="".join(f'<a href="{h}">{t}</a> ' for h, t in links), path=path)


def flawed_routes():
    """A site with one of each crawl problem. Titles differ, so no on-page duplicate rows."""
    return {
        "/": page("Acme home page for invoice teams", ("/pricing", "Pricing"), ("/blog/", "Blog"), ("/old-pricing", "Old pricing"),
                  ("/product", "Product"), ("https://other.example/x", "Partner"), ("/admin/panel", "Admin")),
        "/pricing": page("Acme pricing and plans for teams", ("/", "Home"), path="/pricing"),
        "/blog/": page("Acme blog about reconciliation", ("/blog/a", "Post A"), path="/blog/"),
        "/blog/a": page("Acme post A about matching", ("/blog/a/deep1", "Deeper"), path="/blog/a"),
        "/blog/a/deep1": page("Acme deep page number one", ("/blog/a/deep2", "Deeper"), path="/blog/a/deep1"),
        "/blog/a/deep2": page("Acme deep page number two", path="/blog/a/deep2"),
        "/lonely": page("Acme page nobody links to", path="/lonely"),
        "/product": (301, {"Location": "/products"}, ""),
        "/products": (302, {"Location": "/features"}, ""),
        "/features": page("Acme features for finance teams", path="/features"),
        "/old-pricing": (404, {}, "gone"),
    }


class CrawlCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(ck, "CRAWL_DELAY", 0)
        patcher.start()
        self.addCleanup(patcher.stop)


class CheckerEndToEnd(CrawlCase):
    SITEMAP = ("/", "/pricing", "/blog/a", "/lonely")

    def crawl(self, budget=40, **kw):
        with good_site(extra=flawed_routes(), sitemap_paths=self.SITEMAP, **kw) as s:
            return ck.check(s.base, [], crawl=budget), s.base

    def by_name(self, res):
        return {f["check"]: f for f in res["findings"] if f["area"] == "links"}

    def test_a_default_run_does_not_crawl(self):
        with good_site(extra=flawed_routes()) as s:
            res = ck.check(s.base, [])
        self.assertEqual([f for f in res["findings"] if f["area"] == "links"], [])
        self.assertNotIn("crawl", res)

    def test_every_planted_problem_is_found(self):
        res, base = self.crawl()
        rows_ = self.by_name(res)
        self.assertEqual({k: rows_[k]["status"] for k in (lc.BROKEN, lc.CHAINS, lc.DEPTH, lc.ORPHANS)},
                         {lc.BROKEN: "fail", lc.CHAINS: "warn", lc.DEPTH: "info", lc.ORPHANS: "warn"})
        self.assertEqual(rows_[lc.BROKEN]["status"], "fail")
        self.assertIn("/old-pricing (HTTP 404, from /)", rows_[lc.BROKEN]["detail"])
        self.assertEqual(rows_[lc.CHAINS]["status"], "warn")
        self.assertIn("/product (301) -> /products (302) -> /features", rows_[lc.CHAINS]["detail"])
        self.assertEqual(rows_[lc.DEPTH]["status"], "info")
        self.assertIn("/blog/a/deep2 (4)", rows_[lc.DEPTH]["detail"])
        self.assertEqual(rows_[lc.ORPHANS]["status"], "warn")
        self.assertIn("/lonely", rows_[lc.ORPHANS]["detail"])
        self.assertNotIn("/features", rows_[lc.ORPHANS]["detail"])

    def test_the_crawl_rows_reach_must_fix_and_worth_checking(self):
        res, _ = self.crawl()
        must = {e["check"]: e for e in res["must_fix"] if e["area"] == "links"}
        self.assertEqual({k: v["status"] for k, v in must.items()}, {lc.BROKEN: "fail", lc.CHAINS: "warn", lc.ORPHANS: "warn"})
        self.assertEqual(res["must_fix"][0]["check"], lc.BROKEN)  # failures first
        self.assertIn(lc.DEPTH, [e["check"] for e in res["worth_checking"]])

    def test_crawl_findings_are_scored_once_each(self):
        with good_site(extra=flawed_routes(), sitemap_paths=self.SITEMAP) as s:
            plain = ck.check(s.base, [])
            crawled = ck.check(s.base, [], crawl=40)
        self.assertEqual(crawled["scores"]["fail_count"], plain["scores"]["fail_count"] + 1)
        self.assertEqual(crawled["scores"]["warn_count"], plain["scores"]["warn_count"] + 2)
        self.assertLess(crawled["scores"]["technical_readiness_pct"], plain["scores"]["technical_readiness_pct"])

    def test_the_json_carries_the_link_graph(self):
        res, base = self.crawl()
        data = res["crawl"]
        self.assertEqual((data["budget"], data["complete"], data["stopped"]), (40, True, None))
        self.assertEqual(data["external_hosts"], ["other.example"])
        self.assertEqual(data["orphans"], [base + "/lonely"])
        depths = {p["url"].replace(base, ""): p["depth"] for p in data["pages"]}
        self.assertEqual((depths["/"], depths["/pricing"], depths["/blog/a/deep2"], depths["/features"]), (0, 1, 4, 1))
        self.assertTrue(next(p for p in data["pages"] if p["url"].endswith("/admin/panel"))["blocked"])  # robots.txt disallows /admin/

    def test_a_healthy_site_passes_every_crawl_check(self):
        with good_site(extra={"/": page("Acme home page for invoice teams", ("/pricing", "Pricing")),
                              "/pricing": page("Acme pricing and plans for teams", ("/", "Home"), path="/pricing")}) as s:
            res = ck.check(s.base, [], crawl=20)
        rows_ = self.by_name(res)
        self.assertEqual({k: v["status"] for k, v in rows_.items()},
                         {lc.SUMMARY: "info", lc.BROKEN: "pass", lc.CHAINS: "pass", lc.DEPTH: "pass", lc.ORPHANS: "pass"})

    def test_a_small_limit_gives_a_partial_result_that_says_so(self):
        res, _ = self.crawl(budget=4)
        rows_ = self.by_name(res)
        self.assertFalse(res["crawl"]["complete"])
        self.assertEqual(res["crawl"]["requests"], 4)
        self.assertIn("not requested because the limit was reached", rows_[lc.SUMMARY]["detail"])
        self.assertEqual(rows_[lc.ORPHANS]["status"], "info")
        self.assertIn("not assessed", rows_[lc.ORPHANS]["detail"])

    def test_requests_are_spaced_by_the_crawl_delay(self):
        with good_site(extra=flawed_routes(), sitemap_paths=self.SITEMAP) as s, \
                mock.patch.object(ck, "CRAWL_DELAY", 0.25), mock.patch.object(ck.time, "sleep") as sleep:
            res = ck.check(s.base, [], crawl=40)
        self.assertEqual(sleep.call_args_list, [mock.call(0.25)] * (res["crawl"]["requests"] - 1))

    def test_an_unreadable_robots_txt_means_no_crawl_rather_than_a_guess(self):
        with good_site(extra={"/robots.txt": (503, {}, "down")}, sitemap_paths=("/",)) as s:
            res = ck.check(s.base, [], crawl=10)
        rows_ = self.by_name(res)
        self.assertEqual(list(rows_), [lc.SUMMARY])
        self.assertIn("not run", rows_[lc.SUMMARY]["detail"])
        self.assertNotIn("crawl", res)

    def test_a_server_that_says_429_ends_the_crawl_and_the_report_says_so(self):
        routes = flawed_routes()
        routes["/blog/"] = (429, {}, "slow down")
        with good_site(extra=routes, sitemap_paths=self.SITEMAP) as s:
            res = ck.check(s.base, [], crawl=40)
        self.assertIn("429", res["crawl"]["stopped"])
        self.assertIn("stopped: HTTP 429", self.by_name(res)[lc.SUMMARY]["detail"])
        self.assertEqual(self.by_name(res)[lc.ORPHANS]["status"], "info")

    def test_the_homepage_is_crawled_as_googlebot(self):
        agents = []

        def handler(path, ua):
            if path == "/":
                agents.append(ua)

        with good_site(handler=handler) as s:
            ck.check(s.base, [], crawl=5)
        self.assertGreaterEqual(sum(1 for ua in agents if "Googlebot" in ua), 3)  # the on-page check, render check and the crawl


class CrawlGet(unittest.TestCase):
    def test_it_does_not_follow_redirects_and_reads_only_html(self):
        routes = {"/redir": (301, {"Location": "/target"}, ""), "/target": "<html>hi</html>", "/missing": (404, {}, "no"),
                  "/doc.pdf": (200, {"Content-Type": "application/pdf"}, "%PDF-1.4 " + "x" * 5000)}
        with Site(routes) as s:
            self.assertEqual(ck.crawl_get(s.base + "/redir"), (301, "/target", None, ""))
            self.assertEqual(ck.crawl_get(s.base + "/target"), (200, "", "<html>hi</html>", ""))
            self.assertEqual(ck.crawl_get(s.base + "/missing"), (404, "", None, ""))
            self.assertEqual(ck.crawl_get(s.base + "/doc.pdf"), (200, "", None, ""))  # the PDF body is never read
            base = s.base
        status, _, html_, error = ck.crawl_get(base + "/target")  # the server is gone now
        self.assertEqual((status, html_), (0, None))
        self.assertTrue(error)

    def test_it_asks_as_googlebot_by_default(self):
        seen = []
        with Site(handler=lambda p, ua: seen.append(ua)) as s:
            ck.crawl_get(s.base + "/x")
        self.assertIn("Googlebot", seen[0])


# ---------------------------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------------------------

class CommandLine(CrawlCase):
    def run_cli(self, argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, out = run_main(ck, argv)
        return code, out, err.getvalue()

    def json_of(self, site, *flags):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "r.json")
            code, out, _ = self.run_cli([site.base, "--json", path, *flags])
            with open(path, encoding="utf-8") as fh:
                return code, out, json.load(fh)

    def test_a_bare_crawl_flag_uses_the_default_budget(self):
        with good_site(extra=flawed_routes()) as s:
            _, _, data = self.json_of(s, "--crawl")
        self.assertEqual(data["crawl"]["budget"], lc.DEFAULT_BUDGET)

    def test_a_number_sets_the_budget_and_the_flag_may_precede_other_flags(self):
        with good_site(extra=flawed_routes()) as s:
            _, _, data = self.json_of(s, "--crawl", "6", "--issues-only")
            _, _, data2 = self.json_of(s, "--crawl", "--issues-only")
        self.assertEqual((data["crawl"]["budget"], data["crawl"]["requests"]), (6, 6))
        self.assertEqual(data2["crawl"]["budget"], lc.DEFAULT_BUDGET)

    def test_without_the_flag_there_is_no_crawl_section(self):
        with good_site(extra=flawed_routes()) as s:
            _, out, data = self.json_of(s)
        self.assertNotIn("crawl", data)
        self.assertNotIn("internal link crawl", out)

    def test_unusable_budgets_are_a_usage_error_before_any_request(self):
        for bad in ("0", "-5", str(lc.MAX_BUDGET + 1), "abc", "1.5", "\u00b2", "\u0663", "", " 5", "5 "):
            with mock.patch.object(ck, "check", side_effect=AssertionError("must not run")):
                code, out, err = self.run_cli(["example.com", "--crawl", bad])
            self.assertEqual((code, out), (4, ""), bad)
            self.assertIn("--crawl takes a number", err)

    def test_the_maximum_budget_is_accepted(self):
        with mock.patch.object(ck, "check") as check, mock.patch.object(ck, "to_markdown", return_value=""):
            check.return_value = {"scores": {"fail_count": 0}}
            code, _, _ = self.run_cli(["example.com", "--crawl", str(lc.MAX_BUDGET)])
        self.assertEqual(code, 0)
        self.assertEqual(check.call_args.kwargs["crawl"], lc.MAX_BUDGET)

    def test_a_broken_link_fails_the_run_only_when_crawling(self):
        with good_site(extra=flawed_routes()) as s:
            self.assertEqual(self.run_cli([s.base, "--fail-on", "fail"])[0], 0)
            self.assertEqual(self.run_cli([s.base, "--fail-on", "fail", "--crawl"])[0], 1)

    def test_the_report_shows_the_crawl_section(self):
        with good_site(extra=flawed_routes()) as s:
            _, out, _ = self.json_of(s, "--crawl", "--issues-only")
        self.assertIn("| links | broken internal links |", out)
        self.assertIn("## Must fix (", out)

    def test_help_documents_the_flag(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            ck.main(["--help"])
        self.assertIn("--crawl [N]", out.getvalue())
        self.assertIn(str(lc.MAX_BUDGET), out.getvalue())


if __name__ == "__main__":
    unittest.main()
