"""Unit tests for the on-page checks (geo-visibility/scripts/seo_checks.py). No network: HTML in, findings out."""
import os
import sys
import unittest

from helpers import SKILL

sys.path.insert(0, os.path.join(SKILL, "scripts"))
import seo_checks as sc  # noqa: E402

URL = "https://example.com/pricing"
TITLE = "Pricing and plans for agencies | Example"
DESC = "Example CRM pricing for agencies: three plans, all with unlimited contacts and a REST API."


def page(lang='lang="en"', head="", body="", title=TITLE, desc=DESC, viewport=True, charset=True, canonical=URL, og=True):
    h = []
    if charset:
        h.append('<meta charset="utf-8">')
    if title is not None:
        h.append(f"<title>{title}</title>")
    if desc is not None:
        h.append(f'<meta name="description" content="{desc}">')
    if viewport:
        h.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    if canonical:
        h.append(f'<link rel="canonical" href="{canonical}">')
    if og:
        h.append('<meta property="og:title" content="t"><meta property="og:description" content="d"><meta property="og:image" content="i">'
                 '<meta name="twitter:card" content="summary">')
    if body == "":
        body = ('<h1>Pricing</h1><h2>Plans</h2><p>text</p><img src="/a.png" alt="A chart" width="10" height="10">'
                '<a href="/features">Compare features</a><a href="/about">About our team</a>')
    return f"<!doctype html><html {lang}><head>{''.join(h)}{head}</head><body>{body}</body></html>"


def run(html, url=URL, ms=120):
    rows = sc.page_findings(sc.analyze(html), url, ms)
    return {check: (status, detail, fix) for _, check, status, detail, fix in rows}


class Analyze(unittest.TestCase):
    def test_extracts_the_basics(self):
        f = sc.analyze(page())
        self.assertEqual(f["title"], TITLE)
        self.assertEqual(f["description"], DESC)
        self.assertEqual(f["lang"], "en")
        self.assertEqual(f["charset"], "utf-8")
        self.assertEqual(f["canonicals"], [URL])
        self.assertEqual(f["h1_count"], 1)
        self.assertEqual(f["headings"], [(1, "Pricing"), (2, "Plans")])
        self.assertEqual(f["og"]["og:image"], "i")
        self.assertEqual(f["twitter_card"], "summary")

    def test_http_equiv_charset_and_hreflang_and_multiple_titles(self):
        html = ('<html><head><meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1"><title>One</title><title>Two</title>'
                '<link rel="alternate" hreflang="fr" href="/fr"><link rel="ALTERNATE" hreflang="x-default" href="/"></head><body></body></html>')
        f = sc.analyze(html)
        self.assertIn("iso-8859-1", f["charset"])
        self.assertEqual(f["title"], "One")
        self.assertEqual(f["hreflangs"], [("fr", "/fr"), ("x-default", "/")])

    def test_images_distinguish_a_missing_alt_from_an_empty_one(self):
        f = sc.analyze('<img src="a.png"><img src="b.png" alt=""><img src="c.png" alt="C" width="1" height="2">')
        self.assertEqual([i["alt"] for i in f["images"]], [None, "", "C"])
        self.assertEqual(f["images"][2]["width"], "1")

    def test_anchor_text_includes_the_alt_of_an_image_inside(self):
        f = sc.analyze('<a href="/x"><img src="i.png" alt="Logo"></a><a href="/y">  Pricing   page </a><a href="/z"></a>')
        self.assertEqual([lk["text"] for lk in f["links"]], ["Logo", "Pricing page", ""])

    def test_only_blocking_external_head_scripts_are_counted(self):
        head = ('<script src="a.js"></script><script src="b.js" async></script><script src="c.js" defer></script>'
                '<script src="d.js" type="module"></script><script>inline()</script>')
        body = '<script src="late.js"></script>'
        self.assertEqual(sc.analyze(f"<html><head>{head}</head><body>{body}</body></html>")["blocking_scripts"], 1)

    def test_broken_html_does_not_raise(self):
        self.assertIsNone(sc.analyze("<<<<not html <title>")["title"])
        self.assertEqual(sc.analyze("")["h1_count"], 0)


class GoodPage(unittest.TestCase):
    def test_a_healthy_page_has_no_warnings_failures_or_advice(self):
        rows = run(page())
        bad = {k: v for k, v in rows.items() if v[0] != "pass"}
        self.assertEqual(bad, {})
        for expected in ("title", "meta description", "single h1", "canonical", "viewport", "html lang", "social tags",
                         "image alt text", "link text", "response time"):
            self.assertEqual(rows[expected][0], "pass", expected)


class Title(unittest.TestCase):
    def test_missing_and_empty_titles_fail(self):
        self.assertEqual(run(page(title=None))["title"][0], "fail")
        self.assertEqual(run(page(title="   "))["title"][0], "fail")

    def test_short_long_and_duplicate_title_elements_warn(self):
        self.assertEqual(run(page(title="Hi"))["title"][0], "warn")
        long = run(page(title="x" * 95))["title"]
        self.assertEqual(long[0], "warn")
        self.assertIn("a guideline, not a rule", long[1])
        self.assertEqual(run(page(head="<title>Another title here</title>"))["title"][0], "warn")

    def test_boundaries(self):
        self.assertEqual(run(page(title="x" * 10))["title"][0], "pass")
        self.assertEqual(run(page(title="x" * 70))["title"][0], "pass")
        self.assertEqual(run(page(title="x" * 71))["title"][0], "warn")
        self.assertEqual(run(page(title="x" * 9))["title"][0], "warn")


class Description(unittest.TestCase):
    def test_missing_is_a_warning_short_and_long_are_advice(self):
        self.assertEqual(run(page(desc=None))["meta description"][0], "warn")
        self.assertEqual(run(page(desc=""))["meta description"][0], "warn")
        self.assertEqual(run(page(desc="Too short."))["meta description"][0], "info")
        self.assertEqual(run(page(desc="y" * 400))["meta description"][0], "info")
        self.assertEqual(run(page(desc="y" * 160))["meta description"][0], "pass")


class Headings(unittest.TestCase):
    def test_no_h1_warns_several_is_advice(self):
        self.assertEqual(run(page(body="<h2>Only h2</h2><p>x</p>"))["single h1"][0], "warn")
        self.assertEqual(run(page(body="<h1>A</h1><h1>B</h1>"))["single h1"][0], "info")

    def test_skipped_levels_are_advice_and_empty_headings_warn(self):
        skip = run(page(body="<h1>A</h1><h3>C</h3>"))["heading structure"]
        self.assertEqual(skip[0], "info")
        self.assertIn("h1 to h3", skip[1])
        self.assertEqual(run(page(body="<h1>A</h1><h2> </h2>"))["heading structure"][0], "warn")

    def test_going_back_up_is_fine(self):
        self.assertEqual(run(page(body="<h1>A</h1><h2>B</h2><h3>C</h3><h2>D</h2>"))["heading structure"][0], "pass")


class Canonical(unittest.TestCase):
    def test_cases(self):
        self.assertEqual(run(page(canonical=None))["canonical"][0], "warn")
        self.assertIn("relative", run(page(canonical="/pricing"))["canonical"][1])
        self.assertEqual(run(page(canonical="/pricing"))["canonical"][0], "warn")
        other = run(page(canonical="https://other.example/pricing"))["canonical"]
        self.assertEqual(other[0], "warn")
        self.assertIn("another host", other[1])
        self.assertEqual(run(page(canonical="http://example.com/pricing"))["canonical"][0], "warn")
        moved = run(page(canonical="https://example.com/plans"))["canonical"]
        self.assertEqual(moved[0], "info")
        self.assertIn("/plans", moved[1])
        two = run(page(head='<link rel="canonical" href="https://example.com/x">'))["canonical"]
        self.assertEqual(two[0], "warn")

    def test_trailing_slash_and_query_are_not_a_mismatch(self):
        self.assertEqual(run(page(canonical="https://example.com/pricing/"))["canonical"][0], "pass")
        self.assertEqual(run(page(canonical="https://example.com/pricing?ref=x"))["canonical"][0], "pass")

    def test_homepage(self):
        self.assertEqual(run(page(canonical="https://example.com/"), url="https://example.com/")["canonical"][0], "pass")
        self.assertEqual(run(page(canonical="https://example.com"), url="https://example.com/")["canonical"][0], "pass")


class Basics(unittest.TestCase):
    def test_viewport(self):
        self.assertEqual(run(page(viewport=False))["viewport"][0], "warn")
        blocked = run(page(viewport=False, head='<meta name="viewport" content="width=device-width, user-scalable=no">'))["viewport"]
        self.assertEqual(blocked[0], "info")
        self.assertIn("pinch-zoom", blocked[2])

    def test_lang(self):
        self.assertEqual(run(page(lang=""))["html lang"][0], "warn")
        self.assertEqual(run(page(lang='lang="english!"'))["html lang"][0], "warn")
        for good in ("en", "en-GB", "hi-IN", "zh-Hant-TW"):
            self.assertEqual(run(page(lang=f'lang="{good}"'))["html lang"][0], "pass", good)

    def test_charset_is_advice(self):
        self.assertEqual(run(page(charset=False))["charset"][0], "info")
        self.assertNotIn("charset", run(page()))


class Social(unittest.TestCase):
    def test_none_partial_full(self):
        self.assertEqual(run(page(og=False))["social tags"][0], "info")
        partial = run(page(og=False, head='<meta property="og:title" content="t">'))["social tags"]
        self.assertEqual(partial[0], "info")
        self.assertIn("og:description", partial[1])
        self.assertEqual(run(page())["social tags"][0], "pass")


class Images(unittest.TestCase):
    def test_missing_alt_warns_and_names_examples(self):
        r = run(page(body='<h1>A</h1><img src="/one.png"><img src="/two.png"><img src="/three.png" alt="ok" width="1" height="1">'))
        self.assertEqual(r["image alt text"][0], "warn")
        self.assertIn("2 of 3", r["image alt text"][1])
        self.assertIn("/one.png", r["image alt text"][1])

    def test_empty_alt_is_decorative_and_fine(self):
        self.assertEqual(run(page(body='<h1>A</h1><img src="/d.png" alt="" width="1" height="1">'))["image alt text"][0], "pass")

    def test_no_images_no_row(self):
        self.assertNotIn("image alt text", run(page(body="<h1>A</h1><p>text</p>")))

    def test_missing_dimensions_are_advice(self):
        r = run(page(body='<h1>A</h1><img src="/a.png" alt="a">'))
        self.assertEqual(r["image dimensions"][0], "info")


class Links(unittest.TestCase):
    def test_textless_links_warn(self):
        r = run(page(body='<h1>A</h1><a href="/x"></a><a href="/y">Fine</a>'))
        self.assertEqual(r["link text"][0], "warn")

    def test_generic_anchor_text_is_advice_from_three(self):
        gen = '<a href="/1">Read more</a><a href="/2">click here</a><a href="/3">Here.</a>'
        self.assertEqual(run(page(body=f"<h1>A</h1>{gen}"))["link text"][0], "info")
        self.assertEqual(run(page(body='<h1>A</h1><a href="/1">Read more</a><a href="/2">Pricing</a>'))["link text"][0], "pass")

    def test_fragments_mailto_and_javascript_links_are_ignored(self):
        r = run(page(body='<h1>A</h1><a href="#top"></a><a href="mailto:a@b.c"></a><a href="javascript:x()"></a><a href="/ok">OK page</a>'))
        self.assertEqual(r["link text"][0], "pass")

    def test_an_image_link_with_alt_has_text(self):
        self.assertEqual(run(page(body='<h1>A</h1><a href="/x"><img src="l.png" alt="Home" width="1" height="1"></a>'))["link text"][0], "pass")


class Speed(unittest.TestCase):
    def test_response_time_bands_and_the_single_sample_caveat(self):
        self.assertEqual(run(page(), ms=300)["response time"][0], "pass")
        slow = run(page(), ms=1500)["response time"]
        self.assertEqual(slow[0], "info")
        self.assertIn("one request", slow[1])
        self.assertEqual(run(page(), ms=2500)["response time"][0], "warn")
        self.assertNotIn("response time", run(page(), ms=None))

    def test_blocking_scripts_threshold(self):
        scripts = "".join(f'<script src="s{i}.js"></script>' for i in range(4))
        self.assertEqual(run(page(head=scripts))["render-blocking scripts"][0], "info")
        self.assertNotIn("render-blocking scripts", run(page(head=scripts[: len(scripts) // 2])))


class Contract(unittest.TestCase):
    BROKEN = [
        page(title=None, desc=None, viewport=False, lang="", canonical=None, og=False, charset=False,
             body='<h2>x</h2><h4></h4><img src="a.png"><a href="/x"></a>'),
        page(title="x" * 120, desc="d" * 500, canonical="/rel", body="<h1>a</h1><h1>b</h1><h3>c</h3>"),
        "",
    ]

    def test_every_warning_and_failure_carries_a_fix_and_every_advice_row_too(self):
        for html in self.BROKEN:
            for area, check, status, detail, fix in sc.page_findings(sc.analyze(html), URL, 3000):
                self.assertIn(status, ("pass", "info", "warn", "fail"))
                self.assertIn(area, ("onpage", "indexing"))
                self.assertTrue(detail, check)
                if status != "pass":
                    self.assertTrue(fix.strip(), f"{check} ({status}) has no fix")

    def test_failures_are_reserved_for_a_missing_title(self):
        fails = {check for html in self.BROKEN for _, check, status, _, _ in sc.page_findings(sc.analyze(html), URL, 3000) if status == "fail"}
        self.assertEqual(fails, {"title"})


class Duplicates(unittest.TestCase):
    def facts(self, title, desc):
        return sc.analyze(page(title=title, desc=desc))

    def test_duplicate_titles_and_descriptions_are_found_case_insensitively(self):
        pages = {"/a": self.facts("Same Title Here", "d1 " * 20), "/b": self.facts("same title here", "d2 " * 20),
                 "/c": self.facts("Different title", "d1 " * 20)}
        rows = {check: (status, detail) for _, check, status, detail, _ in sc.duplicates(pages)}
        self.assertEqual(rows["duplicate titles"][0], "warn")
        self.assertIn("/a, /b", rows["duplicate titles"][1])
        self.assertEqual(rows["duplicate descriptions"][0], "warn")
        self.assertIn("/a, /c", rows["duplicate descriptions"][1])

    def test_distinct_pages_pass_and_a_single_page_has_nothing_to_compare(self):
        pages = {"/a": self.facts("Alpha page title", "a " * 30), "/b": self.facts("Beta page title", "b " * 30)}
        self.assertTrue(all(status == "pass" for _, _, status, _, _ in sc.duplicates(pages)))
        self.assertEqual(sc.duplicates({"/a": self.facts("Alpha page title", "a " * 30)}), [])

    def test_pages_without_a_title_are_not_called_duplicates(self):
        pages = {"/a": sc.analyze(page(title=None)), "/b": sc.analyze(page(title=None))}
        self.assertNotIn("duplicate titles", [c for _, c, s, _, _ in sc.duplicates(pages) if s == "warn"])


if __name__ == "__main__":
    unittest.main()
