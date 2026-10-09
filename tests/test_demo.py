import importlib.util
import os
import sys
import unittest

from helpers import ROOT, ck

EXAMPLES = os.path.join(ROOT, "examples")


def _load(name, *parts):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, *parts))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


demo = _load("demo_site", "examples", "demo_site.py")
report = _load("make_demo_report", "tools", "make_demo_report.py")


class DemoSiteBehaviour(unittest.TestCase):
    """The demo site routes by user agent; these are the behaviours the README leans on."""

    BROWSER = ck.BROWSER_UA
    BING = ck.AGENTS["search_and_user_fetch"]["Bingbot"]
    GOOGLE = ck.AGENTS["search_and_user_fetch"]["Googlebot"]

    def status_and_words(self, path, ua):
        code, _, body = demo.respond(path, ua, "127.0.0.1:8765")[0:3]
        return code, ck.count_words(" ".join(ck.parse_page(body).text))

    def test_pricing_is_an_empty_shell_for_everyone(self):
        for ua in (self.BROWSER, self.BING, self.GOOGLE):
            self.assertEqual(self.status_and_words("/pricing", ua), (200, 0))

    def test_features_is_full_for_crawlers_and_a_shell_for_a_default_fetch(self):
        self.assertEqual(self.status_and_words("/features", self.BROWSER)[1], 0)
        self.assertGreater(self.status_and_words("/features", self.GOOGLE)[1], 500)

    def test_blog_is_full_for_googlebot_and_empty_for_bingbot(self):
        self.assertGreater(self.status_and_words("/blog/crm-for-agencies", self.GOOGLE)[1], 600)
        self.assertEqual(self.status_and_words("/blog/crm-for-agencies", self.BING)[1], 0)

    def test_perplexitybot_is_refused_and_unknown_paths_are_404(self):
        ua = ck.AGENTS["search_and_user_fetch"]["PerplexityBot"]
        self.assertEqual(demo.respond("/", ua, "x")[0], 403)
        self.assertEqual(demo.respond("/nope", self.GOOGLE, "x")[0], 404)

    def test_word_helper_is_exact_and_deterministic(self):
        for n in (1, 40, 400, 643):
            self.assertEqual(len(demo.words(n).split()), n)
        self.assertEqual(demo.words(50), demo.words(50))


class CheckerOnTheDemoSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = demo.serve_in_background(0)
        cls.res = ck.check(f"http://127.0.0.1:{cls.server.server_address[1]}", report.PATHS)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_every_planted_flaw_is_reported_in_the_documented_order(self):
        got = [(e["status"], e["check"]) for e in self.res["must_fix"]]
        self.assertEqual(got, [
            ("fail", "robots.txt blocks AI or search agents"),
            ("fail", "WAF refuses crawler user agents"),
            ("fail", "render by agent: /pricing"),
            ("fail", "JSON-LD present"),
            ("warn", "render by agent: /blog/crm-for-agencies"),
            ("warn", "snippet and archive controls"),
            ("warn", "sitemap lastmod honesty"),
            ("warn", "Organization schema"),
            ("warn", "image alt text"),
            ("warn", "duplicate descriptions"),
        ])

    def test_the_named_agents_are_the_planted_ones(self):
        by = {e["check"]: e for e in self.res["must_fix"]}
        self.assertTrue(by["robots.txt blocks AI or search agents"]["detail"].startswith("Claude-SearchBot:"))
        self.assertTrue(by["WAF refuses crawler user agents"]["detail"].startswith("PerplexityBot:"))
        self.assertIn("Googlebot and Bingbot receive different HTML", by["render by agent: /blog/crm-for-agencies"]["detail"])

    def test_dynamic_rendering_is_credited_not_reported(self):
        row = next(f for f in self.res["findings"] if f["check"] == "render by agent: /features")
        self.assertEqual(row["status"], "pass")
        self.assertIn("dynamic rendering", row["detail"])
        self.assertNotIn("render by agent: /features", [e["check"] for e in self.res["must_fix"]])

    def test_a_training_opt_out_is_information_not_a_failure(self):
        row = next(f for f in self.res["findings"] if f["check"] == "robots: GPTBot (training)")
        self.assertEqual(row["status"], "info")
        self.assertIn("blocked", row["detail"])

    def test_open_points_are_listed(self):
        names = [e["check"] for e in self.res["worth_checking"]]
        for expected in ("llms.txt", "Bing Webmaster Tools verification", "Google Search Console verification", "IndexNow key file"):
            self.assertIn(expected, names)

    def test_score_line(self):
        self.assertEqual((self.res["scores"]["fail_count"], self.res["scores"]["warn_count"]), (4, 6))


class GeneratedReport(unittest.TestCase):
    def test_committed_report_matches_what_the_tool_prints(self):
        """Regenerates the report from a live run on a free port. Fails if examples/demo-site-output.md is stale."""
        with open(os.path.join(EXAMPLES, "demo-site-output.md"), encoding="utf-8") as fh:
            committed = fh.read()
        self.assertEqual(report.build(0), committed,
                         "examples/demo-site-output.md is out of date: run python3 tools/make_demo_report.py")

    def test_check_mode_exit_code(self):
        self.assertEqual(report.main(["--check"]), 0)

    def test_report_always_shows_the_documented_port(self):
        text = report.build(0)
        self.assertIn(f"http://127.0.0.1:{demo.PORT}", text)
        self.assertNotRegex(text, r"127\.0\.0\.1:(?!8765\b)\d+")


if __name__ == "__main__":
    unittest.main()
