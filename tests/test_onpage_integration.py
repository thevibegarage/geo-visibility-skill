"""The on-page checks as the checker runs them: which HTML they read, how rows are named, scored and merged in Must fix."""
import unittest

from helpers import ck, good_site, html_page, lorem, one, SHELL

BAD_HEAD_FREE = "<!doctype html><html><head></head><body><h1>Page</h1><p>%s</p><img src='/x.png'></body></html>" % lorem(400)


def rows(res, base):
    return [f for f in res["findings"] if f.get("base") == base]


def page_at(path, title, desc=None, **kw):
    return html_page(title=title, path=path, **kw)


class Naming(unittest.TestCase):
    def test_homepage_rows_keep_their_plain_names_and_other_pages_get_a_suffix(self):
        with good_site() as s:
            res = ck.check(s.base, ["/pricing"])
        names = {f["check"] for f in res["findings"]}
        for plain in ("title", "meta description", "single h1", "canonical", "viewport", "html lang", "social tags", "response time"):
            self.assertIn(plain, names)
            self.assertIn(f"{plain}: /pricing", names)

    def test_rows_carry_the_base_name_and_the_page(self):
        with good_site() as s:
            res = ck.check(s.base, ["/pricing"])
        r = one(res, "title: /pricing")
        self.assertEqual((r["base"], r["page"], r["area"]), ("title", "/pricing", "onpage"))
        self.assertEqual(one(res, "title")["page"], "/")
        self.assertEqual(one(res, "canonical")["area"], "indexing")

    def test_passing_slash_as_a_path_does_not_duplicate_the_homepage(self):
        with good_site() as s:
            res = ck.check(s.base, ["/", "/pricing", "/pricing"])
        self.assertEqual(len([f for f in res["findings"] if f["check"] == "title"]), 1)
        self.assertEqual(len([f for f in res["findings"] if f["check"] == "title: /pricing"]), 1)

    def test_a_healthy_site_has_no_on_page_warnings(self):
        with good_site() as s:
            res = ck.check(s.base, ["/pricing"])
        self.assertEqual([f["check"] for f in res["findings"] if f["area"] in ("onpage", "indexing") and f["status"] in ("warn", "fail")], [])


class WhatIsRead(unittest.TestCase):
    def test_the_html_googlebot_receives_is_what_is_checked_not_the_browsers(self):
        """Dynamic-rendering sites give a browser a shell; judging the title from that would be a false alarm."""
        def handler(p, ua):
            if p == "/" and "Googlebot" not in ua:
                return SHELL
            return None
        with good_site(handler=handler) as s:
            res = ck.check(s.base, [])
        self.assertEqual(one(res, "title")["status"], "pass")

    def test_a_javascript_shell_is_not_assessed_rather_than_failed(self):
        with good_site(extra={"/shell": SHELL}) as s:
            res = ck.check(s.base, ["/shell"])
        r = one(res, "on-page checks: /shell")
        self.assertEqual(r["status"], "info")
        self.assertIn("JavaScript shell", r["detail"])
        self.assertNotIn("title: /shell", {f["check"] for f in res["findings"]})

    def test_an_http_error_is_not_assessed(self):
        with good_site() as s:
            res = ck.check(s.base, ["/does-not-exist"])
        r = one(res, "on-page checks: /does-not-exist")
        self.assertEqual(r["status"], "info")
        self.assertIn("HTTP 404", r["detail"])


class Scoring(unittest.TestCase):
    def test_more_pages_do_not_pad_or_multiply_the_on_page_part_of_the_score(self):
        """On-page rows are one scoring unit per check (worst page wins): 5 pages is not 5x the passes or 5x the penalty."""
        bad = {f"/p{i}": BAD_HEAD_FREE for i in range(5)}

        def seo_units(res):
            units = {}
            w = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
            for f in res["findings"]:
                if (f["group"] or "").startswith("seo:") and f["status"] in w:
                    units[f["group"]] = min(units.get(f["group"], 1.0), w[f["status"]])
            return units

        with good_site(extra=bad) as s:
            one_page = ck.check(s.base, ["/p0"])
            five_pages = ck.check(s.base, list(bad))
        self.assertEqual(seo_units(one_page), seo_units(five_pages))
        self.assertIn("seo:title", seo_units(five_pages))
        self.assertEqual(seo_units(five_pages)["seo:title"], 0.0)
        self.assertGreater(len([f for f in five_pages["findings"] if f["group"] == "seo:title"]), 1)

    def test_a_missing_title_is_the_only_on_page_failure(self):
        with good_site(extra={"/a": BAD_HEAD_FREE}) as s:
            res = ck.check(s.base, ["/a"])
        fails = [f["check"] for f in res["findings"] if f["status"] == "fail" and f["area"] in ("onpage", "indexing")]
        self.assertEqual(fails, ["title: /a"])


class MustFixMerging(unittest.TestCase):
    def test_the_same_issue_on_several_pages_is_one_entry_that_names_them(self):
        extra = {"/a": BAD_HEAD_FREE, "/b": BAD_HEAD_FREE}
        with good_site(extra=extra) as s:
            res = ck.check(s.base, ["/a", "/b"])
        entries = [e for e in res["must_fix"] if e["check"] == "viewport"]
        self.assertEqual(len(entries), 1)
        self.assertIn("/a, /b", entries[0]["detail"])
        self.assertEqual(entries[0]["status"], "warn")
        self.assertTrue(entries[0]["fix"].strip())

    def test_different_details_are_listed_page_by_page(self):
        extra = {"/a": html_page(title="Alpha page title", path="/a", body_extra="<img src='/1.png'>"),
                 "/b": html_page(title="Beta page title", path="/b", body_extra="<img src='/2.png'><img src='/3.png'>")}
        with good_site(extra=extra) as s:
            res = ck.check(s.base, ["/a", "/b"])
        entry = next(e for e in res["must_fix"] if e["check"] == "image alt text")
        self.assertIn("/a: 1 of 1 images", entry["detail"])
        self.assertIn("/b: 2 of 2 images", entry["detail"])

    def test_the_homepage_is_part_of_the_merge(self):
        findings = [
            {"area": "onpage", "check": "viewport", "status": "warn", "detail": "no viewport meta tag", "fix": "Add one.", "group": "seo:viewport", "base": "viewport", "page": "/"},
            {"area": "onpage", "check": "viewport: /a", "status": "warn", "detail": "no viewport meta tag", "fix": "Add one.", "group": "seo:viewport", "base": "viewport", "page": "/a"},
            {"area": "onpage", "check": "viewport: /b", "status": "warn", "detail": "no viewport meta tag", "fix": "Add one.", "group": "seo:viewport", "base": "viewport", "page": "/b"},
        ]
        entries = ck.must_fix(findings)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["detail"].startswith("/, /a, /b: "))

    def test_issues_with_different_fixes_stay_separate(self):
        mk = lambda page, fix: {"area": "onpage", "check": "title", "status": "warn", "detail": "d", "fix": fix, "group": "seo:title",
                                "base": "title", "page": page}
        self.assertEqual(len(ck.must_fix([mk("/", "Fix A"), mk("/a", "Fix B")])), 2)

    def test_more_than_three_differing_pages_are_summarised(self):
        mk = lambda page: {"area": "onpage", "check": "image alt text", "status": "warn", "detail": f"issue on {page}", "fix": "F",
                           "group": "seo:image alt text", "base": "image alt text", "page": page}
        entry = ck.must_fix([mk(f"/p{i}") for i in range(6)])[0]
        self.assertIn("and 3 more pages", entry["detail"])


class WorthCheckingMerging(unittest.TestCase):
    def test_the_same_advice_on_several_pages_is_one_line(self):
        mk = lambda page: {"area": "onpage", "check": "social tags", "status": "info", "detail": "no Open Graph tags", "fix": "Add them.",
                           "group": "seo:social tags", "base": "social tags", "page": page}
        out = ck.worth_checking([mk("/"), mk("/a"), mk("/b")])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["check"], "social tags")
        self.assertTrue(out[0]["detail"].startswith("/, /a, /b: "))

    def test_rows_without_a_page_are_unchanged(self):
        out = ck.worth_checking([{"area": "discovery", "check": "llms.txt", "status": "info", "detail": "not found", "fix": "Optional.",
                                  "group": None, "base": None, "page": None}])
        self.assertEqual(out, [{"check": "llms.txt", "detail": "not found", "fix": "Optional."}])


class CrossPage(unittest.TestCase):
    def test_duplicate_titles_and_descriptions_across_checked_pages_are_flagged(self):
        same = html_page(title="One shared title for both", path="/a")
        extra = {"/a": same, "/b": same.replace("/a", "/b")}
        with good_site(extra=extra) as s:
            res = ck.check(s.base, ["/a", "/b"])
        self.assertEqual(one(res, "duplicate titles")["status"], "warn")
        self.assertEqual(one(res, "duplicate descriptions")["status"], "warn")
        entry = next(e for e in res["must_fix"] if e["check"] == "duplicate titles")
        self.assertIn("/a, /b", entry["detail"])

    def test_distinct_pages_pass(self):
        with good_site() as s:
            res = ck.check(s.base, ["/pricing"])
        self.assertEqual(one(res, "duplicate titles")["status"], "pass")

    def test_no_paths_means_nothing_to_compare(self):
        with good_site() as s:
            res = ck.check(s.base, [])
        self.assertNotIn("duplicate titles", {f["check"] for f in res["findings"]})


if __name__ == "__main__":
    unittest.main()
