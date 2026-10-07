import json
import os
import re
import tempfile
import unittest

from helpers import (Site, ck, good_site, html_page, by_check, one, run_main, closed_port, gz, sitemap_xml, SHELL,
                     ROBOTS_OK, lorem)

BING = "bingbot"


def status_of(res, name):
    return one(res, name)["status"]


# ---------------------------------------------------------------------------------------------
class Baseline(unittest.TestCase):
    def test_healthy_site_scores_100_with_no_failures(self):
        with good_site() as s:
            res = ck.check(s.base, ["/pricing"])
        self.assertEqual(res["scores"]["fail_count"], 0, [f for f in res["findings"] if f["status"] == "fail"])
        self.assertEqual(res["scores"]["technical_readiness_pct"], 100)

    def test_render_compares_googlebot_and_bingbot(self):
        self.assertIn("search crawler (Googlebot)", ck.RENDER_AGENTS)
        self.assertIn("search crawler (Bingbot)", ck.RENDER_AGENTS)
        with good_site() as s:
            res = ck.check(s.base, [])
        row = one(res, "render by agent: /")
        self.assertEqual(row["status"], "pass")
        self.assertIn("Bingbot", row["detail"])
        self.assertIn("Googlebot", row["detail"])
        self.assertTrue(any(f["check"].startswith("soft 404 (search crawler (Bingbot))") for f in res["findings"]))


# ---------------------------------------------------------------------------------------------
class HomepageGate(unittest.TestCase):
    """Regression: a 403/429/503 homepage used to produce a score and a page of fake findings."""

    def test_http_errors_stop_the_checks(self):
        for code in (403, 404, 429, 503):
            with self.subTest(code=code):
                with Site(handler=lambda p, ua, c=code: (c, {}, "<html>Just a moment...</html>")) as s:
                    res = ck.check(s.base, [])
                self.assertEqual(res["homepage_error"], code)
                self.assertEqual(len(res["findings"]), 1)
                self.assertEqual(res["scores"], {})
                md = ck.to_markdown(res)
                self.assertIn(f"HOMEPAGE RETURNED HTTP {code}", md)
                self.assertNotIn("Technical readiness", md)

    def test_exit_codes(self):
        with Site(handler=lambda p, ua: (403, {}, "x")) as s:
            code, _ = run_main(ck, [s.base])
        self.assertEqual(code, 3)
        code, out = run_main(ck, [f"http://127.0.0.1:{closed_port()}"])
        self.assertEqual(code, 2)
        self.assertIn("UNREACHABLE", out)

    def test_certificate_errors_get_an_actionable_hint(self):
        res = {"unreachable": True, "domain": "https://x.example",
               "error": "<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed>"}
        md = ck.to_markdown(res)
        self.assertIn("UNREACHABLE", md)
        self.assertIn("Install Certificates.command", md)
        self.assertIn("SSL_CERT_FILE", md)
        plain = ck.to_markdown({"unreachable": True, "domain": "https://x.example", "error": "timed out"})
        self.assertNotIn("Install Certificates", plain)

    def test_json_output_for_homepage_error(self):
        with Site(handler=lambda p, ua: (503, {}, "x")) as s, tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "r.json")
            run_main(ck, [s.base, "--json", path])
            with open(path) as fh:
                data = json.load(fh)
        self.assertEqual(data["homepage_error"], 503)


# ---------------------------------------------------------------------------------------------
class ParserRobustness(unittest.TestCase):
    def test_valueless_meta_content_does_not_crash(self):
        """Regression: <meta name=robots content> raised AttributeError at .lower()."""
        with good_site(extra={"/": html_page(head="<meta name='robots' content><meta name='description' content>")}) as s:
            res = ck.check(s.base, [])
        self.assertEqual(status_of(res, "noindex"), "pass")

    def test_markdown_table_survives_pipes_in_cells(self):
        """Regression: a title like 'Acme | Widgets' added a column and broke the table."""
        with good_site(extra={"/": html_page(title="Acme | Best invoice widgets")}) as s:
            md = ck.to_markdown(ck.check(s.base, []))
        for line in md.splitlines():
            if line.startswith("|"):
                self.assertEqual(len(re.findall(r"(?<!\\)\|", line)), 6, line)
        self.assertIn("Acme \\| Best invoice widgets", md)


# ---------------------------------------------------------------------------------------------
class UserAgentStrings(unittest.TestCase):
    """Strings follow the vendors' documented formats (checked 2026-10-07)."""

    def test_search_crawlers_use_the_evergreen_chrome_form(self):
        for token in ("Googlebot", "Bingbot"):
            ua = ck.AGENTS["search_and_user_fetch"][token]
            self.assertTrue(ua.startswith("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; "), token)
            self.assertRegex(ua, r"Chrome/\d+\.\d+\.\d+\.\d+ Safari/537\.36$")
        self.assertIn("bingbot/2.0; +http://www.bing.com/bingbot.htm", ck.AGENTS["search_and_user_fetch"]["Bingbot"])
        self.assertIn("Googlebot/2.1; +http://www.google.com/bot.html", ck.AGENTS["search_and_user_fetch"]["Googlebot"])

    def test_every_probe_string_names_its_own_token(self):
        for group, agents in ck.AGENTS.items():
            for token, ua in agents.items():
                if token in ("Google-Extended", "Applebot-Extended"):  # robots.txt tokens, never sent as user agents
                    self.assertEqual(ua, token)
                else:
                    self.assertIn(token.lower().replace("-", ""), ua.lower().replace("-", ""), token)

    def test_amazon_agents_and_meta_indexer_are_present(self):
        other = ck.AGENTS["other_ai"]
        for token in ("Amzn-SearchBot", "Amzn-User", "meta-webindexer", "meta-externalfetcher"):
            self.assertIn(token, other)
        self.assertIn("Amazonbot", ck.AGENTS["training"])  # Amazon: may be used to train Amazon AI models


class OrganizationSchema(unittest.TestCase):
    """Regression (found on a live site): EducationalOrganization on the homepage was reported as 'Organization missing'."""

    def check(self, jsonld_type):
        ld = ('<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"%s","name":"Acme"}]}</script>'
              % jsonld_type)
        with good_site(extra={"/": html_page(jsonld=False, head=ld)}) as s:
            return ck.check(s.base, [])

    def test_subtypes_count_as_an_organization(self):
        for t in ("Organization", "EducationalOrganization", "Corporation", "NGO", "LocalBusiness", "ProfessionalService",
                  "NewsMediaOrganization", "MedicalBusiness", "https://schema.org/Organization"):
            with self.subTest(type=t):
                self.assertEqual(one(self.check(t), "Organization schema")["status"], "pass", t)

    def test_non_organization_types_do_not_count(self):
        for t in ("WebSite", "Article", "Person", "Product"):
            with self.subTest(type=t):
                self.assertEqual(one(self.check(t), "Organization schema")["status"], "warn")

    def test_helper(self):
        self.assertTrue(ck.is_organization_type("EducationalOrganization"))
        self.assertTrue(ck.is_organization_type("https://schema.org/LocalBusiness"))
        self.assertFalse(ck.is_organization_type("OrganizationRole"))
        self.assertFalse(ck.is_organization_type("Person"))


class WordCount(unittest.TestCase):
    def test_space_separated(self):
        self.assertEqual(ck.count_words("one two  three\nfour"), 4)
        self.assertEqual(ck.count_words(""), 0)

    def test_cjk_and_thai_are_not_counted_as_one_word(self):
        """Regression: whitespace splitting gave a full Japanese page 2 words."""
        self.assertGreater(ck.count_words("これは日本語のページです。" * 120), 500)
        self.assertGreater(ck.count_words("这是一个完整的中文页面内容" * 60), 300)
        self.assertGreater(ck.count_words("นี่คือหน้าเว็บภาษาไทยที่มีเนื้อหาครบถ้วน" * 30), 150)
        self.assertGreater(ck.count_words("한국어 페이지입니다 " * 100), 150)

    def test_mixed_script(self):
        self.assertEqual(ck.count_words("Acme 日本語"), 1 + 2)  # 3 CJK chars -> 2 words

    def test_full_japanese_page_is_not_flagged_as_a_shell(self):
        jp = "<p>" + "これは日本語のページです。" * 120 + "</p>"
        with good_site(extra={"/": html_page(words=0, body_extra=jp)}) as s:
            res = ck.check(s.base, [])
        self.assertEqual(status_of(res, "visible text in raw HTML"), "pass")
        self.assertEqual(status_of(res, "render by agent: /"), "pass")


# ---------------------------------------------------------------------------------------------
class RenderByAgent(unittest.TestCase):
    def render(self, handler=None, routes=None):
        with good_site(extra=routes, handler=handler) as s:
            return ck.render_by_agent(s.base + "/")

    def test_shell_for_everyone_is_a_fail(self):
        st, detail, _ = self.render(routes={"/": SHELL})
        self.assertEqual(st, "fail")
        self.assertIn("empty shell for everyone", detail)
        self.assertIn("mount point", detail)

    def test_short_real_page_is_a_warning_not_a_fail(self):
        st, detail, _ = self.render(routes={"/": html_page(words=80)})
        self.assertEqual(st, "warn")
        self.assertIn("short page", detail)

    def test_routing_gap_for_unlisted_user_fetch_agent(self):
        st, detail, _ = self.render(handler=lambda p, ua: SHELL if p == "/" and "Claude-User" in ua else None)
        self.assertEqual(st, "fail")
        self.assertIn("routing gap", detail)
        self.assertIn("user-fetch (Claude-User)", detail)

    def test_dynamic_rendering_by_user_agent_is_a_pass(self):
        st, detail, _ = self.render(handler=lambda p, ua: SHELL if p == "/" and ua == ck.BROWSER_UA else None)
        self.assertEqual(st, "pass")
        self.assertIn("dynamic rendering", detail)

    def test_ai_agent_refused_is_a_block_not_a_shell(self):
        st, detail, _ = self.render(handler=lambda p, ua: (403, {}, "no") if "GPTBot" in ua else None)
        self.assertEqual(st, "fail")
        self.assertIn("refused", detail)
        self.assertNotIn("routing gap", detail)

    def test_googlebot_403_is_only_a_warning(self):
        st, detail, fix = self.render(handler=lambda p, ua: (403, {}, "no") if "Googlebot" in ua else None)
        self.assertEqual(st, "warn")
        self.assertIn("Search Console", fix)

    def test_bingbot_served_a_different_page_than_googlebot_warns(self):
        st, detail, fix = self.render(handler=lambda p, ua: SHELL if p == "/" and BING in ua.lower() else None)
        self.assertEqual(st, "warn")
        self.assertIn("Googlebot and Bingbot receive different HTML", detail)
        self.assertIn("Bing", fix)

    def test_bingbot_403_is_only_a_warning(self):
        st, detail, fix = self.render(handler=lambda p, ua: (403, {}, "no") if BING in ua.lower() else None)
        self.assertEqual(st, "warn")
        self.assertIn("Bing Webmaster Tools", fix)

    def test_browser_error_means_no_comparison(self):
        st, detail, _ = self.render(handler=lambda p, ua: (500, {}, "err") if ua == ck.BROWSER_UA else None)
        self.assertEqual(st, "warn")
        self.assertIn("cannot be compared", detail)


# ---------------------------------------------------------------------------------------------
class WafProbe(unittest.TestCase):
    def test_spoofed_search_crawler_rejection_is_a_warning_and_does_not_fail_ci(self):
        """Regression: verified-bot WAFs reject spoofed Googlebot/Bingbot UAs; that used to fail the run."""
        h = lambda p, ua: (403, {}, "blocked") if p == "/" and ("Googlebot" in ua or BING in ua.lower()) else None
        with good_site(handler=h) as s:
            res = ck.check(s.base, [])
            code, _ = run_main(ck, [s.base, "--fail-on", "fail"])
        self.assertEqual(status_of(res, "WAF probe: Googlebot"), "warn")
        self.assertEqual(status_of(res, "WAF probe: Bingbot"), "warn")
        self.assertEqual(res["scores"]["fail_count"], 0, [f for f in res["findings"] if f["status"] == "fail"])
        self.assertEqual(code, 0)

    def test_ai_agent_rejection_is_still_a_failure(self):
        h = lambda p, ua: (403, {}, "blocked") if p == "/" and "OAI-SearchBot" in ua else None
        with good_site(handler=h) as s:
            res = ck.check(s.base, [])
        self.assertEqual(status_of(res, "WAF probe: OAI-SearchBot"), "fail")
        self.assertGreaterEqual(res["scores"]["fail_count"], 1)


# ---------------------------------------------------------------------------------------------
class RobotsRows(unittest.TestCase):
    def check(self, robots, paths=()):
        with good_site(extra={"/robots.txt": (200, {"Content-Type": "text/plain"}, robots)}) as s:
            return ck.check(s.base, list(paths))

    def test_named_group_does_not_inherit_star_in_the_report(self):
        res = self.check("User-agent: Googlebot\nAllow: /\n\nUser-agent: *\nDisallow: /\n")
        self.assertEqual(status_of(res, "robots: Googlebot (search_and_user_fetch)"), "pass")
        self.assertEqual(status_of(res, "robots: OAI-SearchBot (search_and_user_fetch)"), "fail")
        self.assertEqual(status_of(res, "robots: Bingbot (search_and_user_fetch)"), "fail")

    def test_longest_match_in_the_report(self):
        """Regression: first-match parsing reported Allow:/blog/public after Disallow:/blog as blocked."""
        res = self.check("User-agent: *\nDisallow: /pricing\nAllow: /pricing", paths=["/pricing"])
        self.assertEqual(status_of(res, "robots: OAI-SearchBot (search_and_user_fetch)"), "pass")

    def test_wildcard_rule_blocks_in_the_report(self):
        res = self.check("User-agent: OAI-SearchBot\nDisallow: /*ricing\nAllow: /$\n", paths=["/pricing"])
        row = one(res, "robots: OAI-SearchBot (search_and_user_fetch)")
        self.assertEqual(row["status"], "fail")
        self.assertIn("1/2", row["detail"])

    def test_training_and_other_ai_blocks_are_info_not_failures(self):
        res = self.check("User-agent: GPTBot\nUser-agent: Bytespider\nUser-agent: Amazonbot\nUser-agent: Amzn-SearchBot\nDisallow: /\n")
        for name in ("robots: GPTBot (training)", "robots: Bytespider (training)", "robots: Amazonbot (training)",
                     "robots: Amzn-SearchBot (other_ai)"):
            row = one(res, name)
            self.assertEqual(row["status"], "info", name)
            self.assertIn("blocked", row["detail"])
        self.assertEqual(res["scores"]["fail_count"], 0)

    def test_other_assistants_are_covered(self):
        with good_site() as s:
            res = ck.check(s.base, [])
        for token in ("Applebot", "Amazonbot", "Amzn-SearchBot", "Amzn-User", "meta-webindexer", "meta-externalagent",
                      "meta-externalfetcher", "MistralAI-User", "DuckAssistBot", "Applebot-Extended", "Bytespider", "Bingbot"):
            self.assertTrue(by_check(res, f"robots: {token} "), token)

    def test_robots_5xx_is_a_failure_and_per_agent_rules_are_not_assessed(self):
        """Regression: a 5xx robots.txt was reported as 'crawlers treat it as allow-all'."""
        with good_site(extra={"/robots.txt": (503, {}, "down")}) as s:
            res = ck.check(s.base, [])
        row = one(res, "robots.txt present")
        self.assertEqual(row["status"], "fail")
        self.assertIn("disallow-all", row["detail"])
        self.assertEqual(status_of(res, "robots: OAI-SearchBot (search_and_user_fetch)"), "info")
        self.assertIn("not assessed", one(res, "robots: OAI-SearchBot (search_and_user_fetch)")["detail"])

    def test_robots_4xx_is_allow_all_warning(self):
        with good_site(extra={"/robots.txt": (404, {}, "nf")}) as s:
            res = ck.check(s.base, [])
        row = one(res, "robots.txt present")
        self.assertEqual(row["status"], "warn")
        self.assertIn("allow-all", row["detail"])
        self.assertEqual(status_of(res, "robots: OAI-SearchBot (search_and_user_fetch)"), "pass")

    def test_robots_txt_with_a_byte_order_mark_is_parsed(self):
        with good_site(extra={"/robots.txt": (200, {"Content-Type": "text/plain"}, b"\xef\xbb\xbfUser-agent: *\nDisallow: /\n")}) as s:
            res = ck.check(s.base, [])
        self.assertEqual(status_of(res, "robots: OAI-SearchBot (search_and_user_fetch)"), "fail")

    def test_robots_returning_html_is_flagged(self):
        with good_site(extra={"/robots.txt": html_page()}) as s:
            res = ck.check(s.base, [])
        row = one(res, "robots.txt present")
        self.assertEqual(row["status"], "warn")
        self.assertIn("HTML", row["detail"])


# ---------------------------------------------------------------------------------------------
class Scoring(unittest.TestCase):
    """Regression: 8 robots rows and 8 WAF rows each counted as a check, so trivial passes inflated the score."""

    def score(self, robots):
        with good_site(extra={"/robots.txt": (200, {"Content-Type": "text/plain"}, robots)}) as s:
            return ck.check(s.base, [])

    def test_a_single_blocked_ai_agent_costs_a_whole_check(self):
        res = self.score("User-agent: OAI-SearchBot\nDisallow: /\n")
        self.assertLess(res["scores"]["technical_readiness_pct"], 100)
        self.assertEqual(res["scores"]["fail_count"], 1)

    def test_blocking_every_agent_costs_the_same_single_check(self):
        one_blocked = self.score("User-agent: OAI-SearchBot\nDisallow: /\n")
        all_blocked = self.score("User-agent: *\nDisallow: /\n")
        self.assertEqual(all_blocked["scores"]["fail_count"], 8)
        self.assertEqual(all_blocked["scores"]["technical_readiness_pct"], one_blocked["scores"]["technical_readiness_pct"])

    def test_unit_cost_is_a_meaningful_share(self):
        res = self.score("User-agent: OAI-SearchBot\nDisallow: /\n")
        self.assertLessEqual(res["scores"]["technical_readiness_pct"], 95)


# ---------------------------------------------------------------------------------------------
class Sitemaps(unittest.TestCase):
    def rows(self, res):
        return [f for f in res["findings"] if f["check"].startswith("sitemap ") and f["check"] != "sitemap lastmod honesty"]

    def test_gzip_sitemap_listed_in_robots(self):
        """Regression: sitemap.xml.gz was never decoded, so the check reported 'no valid sitemap found'."""
        extra = {
            "/robots.txt": lambda b: (200, {"Content-Type": "text/plain"}, f"User-agent: *\nSitemap: {b}/sitemap.xml.gz\n"),
            "/sitemap.xml.gz": lambda b: (200, {"Content-Type": "application/gzip"}, gz(sitemap_xml([b + "/", b + "/pricing"]))),
            "/sitemap.xml": (404, {}, "nf"),
        }
        with good_site(extra=extra) as s:
            res = ck.check(s.base, [])
        rows = self.rows(res)
        self.assertEqual([r["status"] for r in rows], ["pass"])
        self.assertTrue(rows[0]["check"].endswith("sitemap.xml.gz"))
        self.assertEqual(res["scores"]["fail_count"], 0)

    def test_falls_back_to_sitemap_xml_when_robots_lists_a_dead_one(self):
        extra = {"/robots.txt": lambda b: (200, {"Content-Type": "text/plain"}, f"User-agent: *\nSitemap: {b}/gone.xml\n")}
        with good_site(extra=extra) as s:
            res = ck.check(s.base, [])
        rows = self.rows(res)
        self.assertEqual(rows[0]["status"], "pass")
        self.assertTrue(rows[0]["check"].endswith("/sitemap.xml"))

    def test_no_valid_sitemap_fails_and_lists_what_was_tried(self):
        with good_site(extra={"/sitemap.xml": (404, {}, "nf")}) as s:
            res = ck.check(s.base, [])
        row = one(res, "sitemap")
        self.assertEqual(row["status"], "fail")
        self.assertIn("tried", row["detail"])

    def test_sitemap_index_is_followed(self):
        def child(b, n, lm):
            return (200, {"Content-Type": "application/xml"},
                    sitemap_xml([f"{b}/p{n}-{i}" for i in range(12)], [lm] * 12))
        extra = {
            "/sitemap.xml": lambda b: (200, {"Content-Type": "application/xml"},
                                       "<sitemapindex>" + "".join(f"<sitemap><loc>{b}/s{n}.xml</loc></sitemap>" for n in (1, 2)) + "</sitemapindex>"),
            "/s1.xml": lambda b: child(b, 1, "2025-01-01"),
            "/s2.xml": lambda b: child(b, 2, "2025-01-01"),
        }
        with good_site(extra=extra) as s:
            res = ck.check(s.base, [])
        row = self.rows(res)[0]
        self.assertIn("2 child sitemaps", row["detail"])
        self.assertIn("24 URLs", row["detail"])
        self.assertEqual(status_of(res, "sitemap lastmod honesty"), "warn")  # all 24 share one date

    def test_paths_must_be_in_the_sitemap(self):
        with good_site() as s:
            ok = ck.check(s.base, ["/pricing"])
            missing = ck.check(s.base, ["/pricing", "/blog/post-1"])
        self.assertEqual(status_of(ok, "--paths listed in sitemap"), "pass")
        row = one(missing, "--paths listed in sitemap")
        self.assertEqual(row["status"], "warn")
        self.assertIn("/blog/post-1", row["detail"])

    def test_paths_not_assessed_when_index_is_only_partly_sampled(self):
        extra = {"/sitemap.xml": lambda b: (200, {}, "<sitemapindex>" + "".join(
                     f"<sitemap><loc>{b}/s{n}.xml</loc></sitemap>" for n in range(7)) + "</sitemapindex>")}
        extra.update({f"/s{n}.xml": (lambda b, n=n: (200, {}, sitemap_xml([f"{b}/x{n}"]))) for n in range(7)})
        with good_site(extra=extra) as s:
            res = ck.check(s.base, ["/pricing"])
        self.assertEqual(status_of(res, "--paths listed in sitemap"), "info")

    def test_lastmod_clustering_still_warns(self):
        urls = lambda b: [f"{b}/p{i}" for i in range(20)]
        extra = {"/sitemap.xml": lambda b: (200, {}, sitemap_xml(urls(b), ["2025-03-03"] * 20))}
        with good_site(extra=extra) as s:
            res = ck.check(s.base, [])
        self.assertEqual(status_of(res, "sitemap lastmod honesty"), "warn")

    def test_gunzip_helper_tolerates_truncated_streams(self):
        blob = gz("<urlset>" + "<url><loc>https://x.com/a</loc></url>" * 500 + "</urlset>")
        self.assertIn("<urlset>", ck._decode(blob))
        self.assertIn("<urlset>", ck._decode(blob[: len(blob) // 2]))  # truncated: partial, no exception
        self.assertEqual(ck._decode(b"plain text"), "plain text")


# ---------------------------------------------------------------------------------------------
class Directives(unittest.TestCase):
    def check(self, head="", headers=None):
        with good_site(extra={"/": (200, headers or {}, html_page(head=head + "<meta name='msvalidate.01' content='x'>"))}) as s:
            return ck.check(s.base, [])

    def test_noindex_in_googlebot_or_bingbot_meta_is_a_failure(self):
        for name in ("googlebot", BING, "robots"):
            with self.subTest(name=name):
                res = self.check(f"<meta name='{name}' content='noindex, follow'>")
                row = one(res, "noindex")
                self.assertEqual(row["status"], "fail")
                self.assertIn(f"meta {name}", row["detail"])

    def test_bot_prefixed_x_robots_tag_noindex_is_found(self):
        res = self.check(headers=[("X-Robots-Tag", "bingbot: noindex")])
        self.assertEqual(status_of(res, "noindex"), "fail")

    def test_none_means_noindex_but_max_image_preview_none_does_not(self):
        self.assertEqual(status_of(self.check("<meta name='robots' content='none'>"), "noindex"), "fail")
        self.assertEqual(status_of(self.check("<meta name='robots' content='max-image-preview:none'>"), "noindex"), "pass")

    def test_duplicate_x_robots_tag_headers_are_joined(self):
        with Site(routes={"/": (200, [("X-Robots-Tag", "noindex"), ("X-Robots-Tag", "nosnippet")], "x")}) as s:
            headers = ck.fetch(s.base + "/")[1]
        self.assertEqual(headers["X-Robots-Tag"], "noindex, nosnippet")

    def test_snippet_and_archive_controls_are_reported(self):
        res = self.check("<meta name='robots' content='max-snippet:0, noarchive'><meta name='bingbot' content='nocache'>")
        row = one(res, "snippet and archive controls")
        self.assertEqual(row["status"], "warn")
        for needle in ("nosnippet/max-snippet:0", "noarchive", "nocache"):
            self.assertIn(needle, row["detail"])
        self.assertEqual(res["scores"]["fail_count"], 0)  # a deliberate opt-out is not a failure

    def test_nosnippet_in_x_robots_tag_is_reported(self):
        res = self.check(headers={"X-Robots-Tag": "nosnippet"})
        self.assertEqual(status_of(res, "snippet and archive controls"), "warn")

    def test_no_controls_is_a_pass(self):
        self.assertEqual(status_of(self.check(), "snippet and archive controls"), "pass")


# ---------------------------------------------------------------------------------------------
class BingAndIndexNow(unittest.TestCase):
    def test_meta_tag_verification(self):
        with good_site() as s:
            res = ck.check(s.base, [])
        self.assertEqual(one(res, "Bing Webmaster Tools verification")["status"], "pass")

    def test_bing_site_auth_xml_verification(self):
        extra = {"/": html_page(), "/BingSiteAuth.xml": "<?xml version='1.0'?><users><user>ABC</user></users>"}
        with good_site(extra=extra) as s:
            res = ck.check(s.base, [])
        row = one(res, "Bing Webmaster Tools verification")
        self.assertEqual(row["status"], "pass")
        self.assertIn("BingSiteAuth.xml", row["detail"])

    def test_no_verification_is_info_with_a_pointer(self):
        with good_site(extra={"/": html_page()}) as s:
            res = ck.check(s.base, [])
        row = one(res, "Bing Webmaster Tools verification")
        self.assertEqual(row["status"], "info")
        self.assertIn("IndexNow", row["fix"])
        self.assertIn("AI Performance", row["fix"])

    def test_google_verification_hint(self):
        extra = {"/": html_page(head="<meta name='google-site-verification' content='tok'>")}
        with good_site(extra=extra) as s:
            res = ck.check(s.base, [])
        self.assertEqual(status_of(res, "Google Search Console verification"), "pass")

    def test_indexnow_key_file(self):
        key = "abc123def456"
        with good_site(extra={f"/{key}.txt": (200, {"Content-Type": "text/plain"}, key + "\n")}) as s:
            self.assertEqual(status_of(ck.check(s.base, [], indexnow_key=key), "IndexNow key file"), "pass")
            self.assertEqual(status_of(ck.check(s.base, [], indexnow_key="otherkey"), "IndexNow key file"), "warn")
            self.assertEqual(status_of(ck.check(s.base, []), "IndexNow key file"), "info")

    def test_malformed_indexnow_key_is_flagged_without_a_request(self):
        for bad in ("short", "has spaces in it", "x" * 129, "bad/slash/key1"):
            with self.subTest(key=bad):
                with good_site() as s:
                    row = one(ck.check(s.base, [], indexnow_key=bad), "IndexNow key file")
                self.assertEqual(row["status"], "warn")
                self.assertIn("not a valid IndexNow key", row["detail"])

    def test_indexnow_key_flag_on_the_cli(self):
        key = "k" * 16
        with good_site(extra={f"/{key}.txt": (200, {"Content-Type": "text/plain"}, key)}) as s:
            _, out = run_main(ck, [s.base, "--indexnow-key", key])
        self.assertRegex(out, r"IndexNow key file \| pass")


# ---------------------------------------------------------------------------------------------
class SoftFourOhFour(unittest.TestCase):
    def test_catch_all_200_for_crawlers_fails_and_is_one_scored_check(self):
        h = lambda p, ua: (200, {}, html_page()) if p.startswith("/geo-audit-missing") else None
        with good_site(handler=h) as s:
            res = ck.check(s.base, [])
        rows = [f for f in res["findings"] if f["check"].startswith("soft 404")]
        by = {f["check"]: f["status"] for f in rows}
        self.assertEqual(by["soft 404 (browser)"], "info")
        self.assertEqual(sum(1 for v in by.values() if v == "fail"), 5)
        self.assertTrue(all(f["group"] == "soft404" for f in rows if f["status"] in ("pass", "warn", "fail")))

    def test_real_404_passes(self):
        with good_site() as s:
            res = ck.check(s.base, [])
        self.assertTrue(all(f["status"] == "pass" for f in res["findings"] if f["check"].startswith("soft 404")))


# ---------------------------------------------------------------------------------------------
BARE = f"<!doctype html><html><head><title>A decent page title here</title></head><body><h1>Hi</h1><p>{lorem(300)}</p></body></html>"
BOT_BLOCKED = lambda p, ua: (403, {}, "no") if ua != ck.BROWSER_UA and p != "/robots.txt" else None


class MustFix(unittest.TestCase):
    """The checker has to say what to fix, not just print 50 rows: failures first, each with a concrete fix."""

    def broken(self):
        robots = (200, {"Content-Type": "text/plain"}, "User-agent: OAI-SearchBot\nDisallow: /\n")
        return good_site(extra={"/robots.txt": robots, "/": BARE})

    def test_failures_come_before_warnings_and_every_entry_has_a_fix(self):
        with self.broken() as s:
            res = ck.check(s.base, [])
        entries = res["must_fix"]
        statuses = [e["status"] for e in entries]
        self.assertEqual(statuses, sorted(statuses, key=lambda x: 0 if x == "fail" else 1))
        self.assertIn("fail", statuses)
        self.assertIn("warn", statuses)
        self.assertTrue(all(e["fix"].strip() and e["fix"] != ck.NO_FIX for e in entries), entries)
        self.assertTrue(all(e["status"] in ("fail", "warn") for e in entries))
        self.assertEqual(entries[0]["area"], "access")  # retrieval blockers first

    def test_scores_include_a_warning_count(self):
        with self.broken() as s:
            res = ck.check(s.base, [])
        self.assertEqual(res["scores"]["warn_count"], sum(1 for f in res["findings"] if f["status"] == "warn"))

    def test_per_agent_robots_rows_are_merged_into_one_entry(self):
        robots = (200, {"Content-Type": "text/plain"}, "User-agent: *\nDisallow: /\n")
        with good_site(extra={"/robots.txt": robots}) as s:
            res = ck.check(s.base, [])
        rows = [e for e in res["must_fix"] if e["check"].startswith("robots.txt blocks")]
        self.assertEqual(len(rows), 1)
        for token in ck.AGENTS["search_and_user_fetch"]:
            self.assertIn(token, rows[0]["detail"])
        self.assertEqual(res["scores"]["fail_count"], 8)  # the raw count is unchanged

    def test_soft_404_rows_are_merged_and_waf_failures_and_warnings_stay_separate(self):
        h = lambda p, ua: (200, {}, html_page()) if p.startswith("/geo-audit-missing") else None
        with good_site(handler=h) as s:
            res = ck.check(s.base, [])
        soft = [e for e in res["must_fix"] if "soft 404" in e["check"]]
        self.assertEqual(len(soft), 1)
        self.assertIn("Bingbot", soft[0]["detail"])
        h = lambda p, ua: (403, {}, "no") if p == "/" and ("Googlebot" in ua or "OAI-SearchBot" in ua) else None
        with good_site(handler=h) as s:
            res = ck.check(s.base, [])
        waf = [(e["status"], e["detail"].split(" (")[0]) for e in res["must_fix"] if e["check"].startswith("WAF refuses")]
        self.assertEqual(sorted(waf), [("fail", "OAI-SearchBot"), ("warn", "Googlebot")])

    def test_markdown_leads_with_the_must_fix_table(self):
        with self.broken() as s:
            md = ck.to_markdown(ck.check(s.base, []))
        self.assertLess(md.index("## Must fix"), md.index("## All checks"))
        self.assertRegex(md, r"\(\d+ failures, \d+ warnings\)")
        first_row = next(line for line in md.splitlines() if line.startswith("| 1 |"))
        self.assertIn("| fail |", first_row)

    def test_healthy_site_has_nothing_to_fix(self):
        with good_site(extra={"/indexnow-key-1234.txt": "indexnow-key-1234"}) as s:
            md = ck.to_markdown(ck.check(s.base, [], indexnow_key="indexnow-key-1234"))
        self.assertIn("## Must fix (0)", md)
        self.assertIn("Nothing failed or warned.", md)

    def test_issues_only_hides_passing_rows_but_json_keeps_everything(self):
        with self.broken() as s, tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "r.json")
            code, full = run_main(ck, [s.base])
            code, short = run_main(ck, [s.base, "--issues-only", "--json", path])
            with open(path) as fh:
                data = json.load(fh)
        tail = short.split("## All checks")[1]
        self.assertNotIn("| pass |", tail)
        self.assertRegex(tail.splitlines()[0], r"\(\d+ routine checks hidden\)")
        self.assertNotIn("| info | allowed |", tail)
        self.assertIn("| pass |", full.split("## All checks")[1])
        self.assertIn("## Must fix", short)
        self.assertGreater(sum(1 for f in data["findings"] if f["status"] == "pass"), 0)
        self.assertTrue(data["must_fix"])
        self.assertIn("worth_checking", data)

    def test_issues_only_still_shows_a_blocked_training_agent(self):
        robots = (200, {"Content-Type": "text/plain"}, "User-agent: GPTBot\nDisallow: /\n")
        with good_site(extra={"/robots.txt": robots}) as s:
            _, out = run_main(ck, [s.base, "--issues-only"])
        self.assertRegex(out, r"robots: GPTBot \(training\) \| info \| blocked")

    def test_worth_checking_lists_unscored_open_points(self):
        with good_site(extra={"/": html_page()}) as s:  # no Bing or Google verification tag
            res = ck.check(s.base, [])
        names = [e["check"] for e in res["worth_checking"]]
        self.assertIn("Bing Webmaster Tools verification", names)
        self.assertIn("IndexNow key file", names)
        self.assertIn("Google Search Console verification", names)
        self.assertEqual(res["must_fix"], [])  # info rows are not defects
        with good_site() as s:  # has the msvalidate tag
            names = [e["check"] for e in ck.check(s.base, [])["worth_checking"]]
        self.assertNotIn("Bing Webmaster Tools verification", names)

    def test_no_failing_or_warning_row_ever_has_an_empty_fix(self):
        """Regression: title, meta description, H1 and a few other warnings used to print an empty Fix cell."""
        fixtures = {
            "bare page": dict(extra={"/": BARE}),
            "no meta/h1/title": dict(extra={"/": "<html><body><p>" + lorem(300) + "</p></body></html>"}),
            "robots 5xx": dict(extra={"/robots.txt": (503, {}, "x")}),
            "robots 404": dict(extra={"/robots.txt": (404, {}, "x")}),
            "robots html": dict(extra={"/robots.txt": html_page()}),
            "bots refused": dict(handler=BOT_BLOCKED),
            "catch-all 200": dict(handler=lambda p, ua: (200, {}, html_page()) if p.startswith("/geo-audit-missing") else None),
            "noindex+nosnippet": dict(extra={"/": html_page(head="<meta name='robots' content='noindex, nosnippet'>")}),
            "shell": dict(extra={"/": SHELL}),
            "short page": dict(extra={"/": html_page(words=80)}),
            "no sitemap": dict(extra={"/sitemap.xml": (404, {}, "nf")}),
            "title mismatch": dict(handler=lambda p, ua: html_page(title="Different title for the bot", words=400) if p == "/" and "GPTBot" in ua else None),
        }
        for name, kw in fixtures.items():
            with self.subTest(fixture=name):
                with good_site(**kw) as s:
                    res = ck.check(s.base, ["/pricing"])
                for f in res["findings"]:
                    if f["status"] in ("fail", "warn"):
                        self.assertTrue(f["fix"].strip(), f"{name}: {f['check']} has no fix")
                self.assertTrue(all(e["fix"] != ck.NO_FIX for e in res["must_fix"]), name)

    def test_short_keeps_headlines_and_truncates_long_details(self):
        self.assertEqual(ck._short("every agent sees under 150 words. browser: HTTP 200, 25 words"), "every agent sees under 150 words")
        long = "x" * 500
        self.assertLessEqual(len(ck._short(long)), 220)
        self.assertTrue(ck._short(long).endswith("..."))
        self.assertEqual(ck._short("short"), "short")

    def test_no_fix_placeholder_is_used_when_a_row_has_none(self):
        rows = [{"status": "warn", "area": "onpage", "check": "x", "detail": "d", "fix": "", "group": None}]
        self.assertEqual(ck.must_fix(rows)[0]["fix"], ck.NO_FIX)


# ---------------------------------------------------------------------------------------------
class Cli(unittest.TestCase):
    def test_fail_on_flag(self):
        robots = (200, {"Content-Type": "text/plain"}, "User-agent: OAI-SearchBot\nDisallow: /\n")
        with good_site(extra={"/robots.txt": robots}) as bad, good_site() as good:
            self.assertEqual(run_main(ck, [bad.base])[0], 0)
            self.assertEqual(run_main(ck, [bad.base, "--fail-on", "fail"])[0], 1)
            self.assertEqual(run_main(ck, [good.base, "--fail-on", "fail"])[0], 0)

    def test_json_output_and_paths(self):
        with good_site() as s, tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.json")
            code, out = run_main(ck, [s.base, "--paths", "/pricing", "--json", path])
            with open(path) as fh:
                data = json.load(fh)
        self.assertEqual(code, 0)
        self.assertEqual(data["scores"]["technical_readiness_pct"], 100)
        self.assertIn("render by agent: /pricing", out)
        self.assertTrue(all("group" in f for f in data["findings"]))


if __name__ == "__main__":
    unittest.main()
