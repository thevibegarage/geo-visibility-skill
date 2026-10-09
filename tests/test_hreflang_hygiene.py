"""hreflang validity and return links, HTTP-to-HTTPS and www/apex hygiene (item 3b)."""
import unittest
from unittest import mock

from helpers import SHELL, Site, ck, good_site, html_page, lorem, one

seo = ck.seo_checks


def alt(code, path):
    return f"<link rel='alternate' hreflang='{code}' href='{{BASE}}{path}'>"


def tags(*pairs):
    return "".join(alt(c, p) for c, p in pairs)


EN_FR = tags(("en", "/"), ("fr", "/fr"), ("x-default", "/"))


def fr_page(back=True):
    return html_page(title="Acme Widgets en français", h1="Acme en français", path="/fr",
                     head=EN_FR if back else alt("fr", "/fr"))


class HreflangRow(unittest.TestCase):
    URL = "https://a.com/"

    def row(self, *pairs):
        return seo.hreflang_row(list(pairs), self.URL)

    def test_a_valid_self_referencing_set_with_x_default_passes(self):
        self.assertEqual(self.row(("en", "https://a.com/"), ("fr", "https://a.com/fr"), ("x-default", "https://a.com/"))[0], "pass")

    def test_missing_x_default_is_advice_not_a_defect(self):
        status, detail, fix = self.row(("en", "https://a.com/"), ("fr", "https://a.com/fr"))
        self.assertEqual(status, "info")
        self.assertIn("x-default", detail)
        self.assertTrue(fix)

    def test_invalid_codes_warn(self):
        for bad in ("english", "en_GB", "uk-ua-x", "e", "en-gb-extra-long-tag"):
            status, detail, _ = self.row(("en", "https://a.com/"), (bad, "https://a.com/x"))
            self.assertEqual(status, "warn", bad)
            self.assertIn("invalid language code", detail)

    def test_valid_codes_are_accepted(self):
        for good in ("en", "EN", "en-GB", "pt-br", "zh-Hans", "zh-Hant-TW", "es-419", "x-default"):
            self.assertEqual(self.row(("en", "https://a.com/"), (good, "https://a.com/x"))[0] == "warn" and "invalid" in
                             self.row(("en", "https://a.com/"), (good, "https://a.com/x"))[1], False, good)

    def test_the_same_code_pointing_at_two_urls_warns(self):
        status, detail, _ = self.row(("en", "https://a.com/"), ("fr", "https://a.com/fr"), ("fr", "https://a.com/fr2"))
        self.assertEqual(status, "warn")
        self.assertIn("different URLs", detail)

    def test_a_repeated_identical_entry_is_not_a_clash(self):
        self.assertEqual(self.row(("en", "https://a.com/"), ("fr", "https://a.com/fr"), ("fr", "https://a.com/fr"), ("x-default", "https://a.com/"))[0], "pass")

    def test_relative_urls_warn(self):
        status, detail, _ = self.row(("en", "https://a.com/"), ("fr", "/fr"))
        self.assertEqual(status, "warn")
        self.assertIn("relative", detail)

    def test_a_page_that_does_not_list_itself_warns(self):
        status, detail, _ = self.row(("fr", "https://a.com/fr"), ("de", "https://a.com/de"))
        self.assertEqual(status, "warn")
        self.assertIn("does not list itself", detail)

    def test_self_reference_ignores_a_trailing_slash_but_not_the_scheme(self):
        self.assertEqual(seo.hreflang_row([("en", "https://a.com/pricing/"), ("fr", "https://a.com/fr")], "https://a.com/pricing")[0], "info")
        self.assertEqual(seo.hreflang_row([("en", "http://a.com/"), ("fr", "https://a.com/fr")], "https://a.com/")[0], "warn")

    def test_every_warning_carries_a_fix(self):
        status, _, fix = self.row(("xx_yy", "/rel"))
        self.assertEqual(status, "warn")
        self.assertTrue(fix)


class SameUrl(unittest.TestCase):
    def test_equality_rules(self):
        self.assertTrue(seo.same_url("https://A.com/x/", "https://a.com/x"))
        self.assertTrue(seo.same_url("https://a.com", "https://a.com/"))
        self.assertFalse(seo.same_url("http://a.com/", "https://a.com/"))
        self.assertFalse(seo.same_url("https://a.com/x?l=fr", "https://a.com/x?l=en"))
        self.assertFalse(seo.same_url("https://a.com/x", "https://b.com/x"))


class ReturnLinks(unittest.TestCase):
    def test_a_page_that_links_back_passes(self):
        self.assertIsNone(seo.return_link_problem("https://a.com/", "https://a.com/fr", 200, [("en", "https://a.com/")]))

    def test_a_relative_return_link_is_resolved_against_the_alternate(self):
        self.assertIsNone(seo.return_link_problem("https://a.com/", "https://a.com/fr", 200, [("en", "/")]))

    def test_no_return_link_is_a_problem_that_names_both_pages(self):
        msg = seo.return_link_problem("https://a.com/", "https://a.com/fr", 200, [("fr", "https://a.com/fr")])
        self.assertIn("/fr", msg)
        self.assertIn("does not link back to /", msg)

    def test_an_alternate_that_errors_is_a_problem(self):
        self.assertIn("HTTP 404", seo.return_link_problem("https://a.com/", "https://a.com/fr", 404, []))
        self.assertIn("could not be fetched", seo.return_link_problem("https://a.com/", "https://a.com/fr", 0, []))

    def test_reciprocity_row_statuses(self):
        self.assertEqual(seo.reciprocity_row([], 2)[0], "pass")
        st, detail, fix = seo.reciprocity_row(["/fr does not link back to /"], 1)
        self.assertEqual(st, "warn")
        self.assertTrue(fix)
        self.assertEqual(seo.reciprocity_row([], 0)[0], "info")

    def test_other_hosts_and_shells_are_named_not_hidden(self):
        st, detail, _ = seo.reciprocity_row([], 1, ["/app"], ["example.fr", "example.de"])
        self.assertEqual(st, "pass")
        self.assertIn("/app", detail)
        self.assertIn("example.fr", detail)
        self.assertIn("only the audited host", detail)


class HreflangEndToEnd(unittest.TestCase):
    def site(self, fr=None, home=EN_FR, extra=None):
        routes = {"/": html_page(head=home), "/fr": fr if fr is not None else fr_page()}
        routes.update(extra or {})
        return good_site(extra=routes)

    def test_a_site_with_no_hreflang_gets_no_hreflang_rows(self):
        with good_site() as s:
            res = ck.check(s.base, ["/pricing"])
        self.assertEqual([f for f in res["findings"] if "hreflang" in f["check"]], [])

    def test_a_correct_pair_passes_both_checks(self):
        with self.site() as s:
            res = ck.check(s.base, ["/fr"])
        self.assertEqual(one(res, "hreflang")["status"], "pass")
        self.assertEqual(one(res, "hreflang return links")["status"], "pass")
        self.assertEqual(one(res, "hreflang: /fr")["status"], "pass")

    def test_a_missing_return_link_is_found_by_fetching_the_alternate(self):
        with self.site(fr=fr_page(back=False)) as s:
            res = ck.check(s.base, [])  # /fr is not in --paths: the alternate is still fetched
        r = one(res, "hreflang return links")
        self.assertEqual(r["status"], "warn")
        self.assertIn("/fr does not link back to /", r["detail"])
        self.assertTrue(r["fix"])

    def test_an_alternate_that_is_gone_is_reported(self):
        with self.site(extra={"/fr": (404, {}, "gone")}) as s:
            res = ck.check(s.base, [])
        self.assertIn("HTTP 404", one(res, "hreflang return links")["detail"])

    def test_an_alternate_on_another_host_is_never_fetched(self):
        with Site({"/": "x"}) as other:
            hosts = []
            real = ck.urllib.request.urlopen

            def spy(req, *a, **kw):
                hosts.append(req.full_url.split("/")[2])
                return real(req, *a, **kw)

            head = tags(("en", "/")) + f"<link rel='alternate' hreflang='fr' href='{other.base}/fr'>"
            with self.site(home=head) as s:
                ck.urllib.request.urlopen = spy
                try:
                    res = ck.check(s.base, [])
                finally:
                    ck.urllib.request.urlopen = real
        self.assertNotIn(other.base.split("//")[1], hosts)
        r = one(res, "hreflang return links")
        self.assertIn(other.base.split("//")[1], r["detail"])
        self.assertEqual(r["status"], "info")

    def test_a_javascript_shell_alternate_is_not_called_a_failure(self):
        with self.site(fr=SHELL) as s:
            res = ck.check(s.base, [])
        r = one(res, "hreflang return links")
        self.assertNotEqual(r["status"], "warn")
        self.assertIn("JavaScript shell", r["detail"])

    def test_the_fetch_limit_bounds_the_work(self):
        many = tags(*[("en", "/")] + [(f"l{i}", f"/p{i}") for i in range(30)])
        extra = {f"/p{i}": html_page(path=f"/p{i}", head=many) for i in range(30)}
        with self.site(home=many, extra=extra) as s:
            seen = []
            real = ck.fetch

            def spy(url, *a, **kw):
                seen.append(url)
                return real(url, *a, **kw)

            with mock.patch.object(ck, "fetch", spy):
                res = ck.check(s.base, [])
        alt_fetches = [u for u in seen if "/p" in u and "pricing" not in u]
        self.assertLessEqual(len(set(alt_fetches)), ck.HREFLANG_FETCH_LIMIT)
        self.assertIn("stopped after", one(res, "hreflang return links")["detail"])

    def test_return_links_count_once_in_the_score_however_many_pages_name_them(self):
        def units(res):
            return [f for f in res["findings"] if f.get("group") == "seo:hreflang return links"]
        with self.site(fr=fr_page(back=False)) as s:
            res = ck.check(s.base, ["/fr"])
        self.assertEqual(len(units(res)), 1)

    def test_it_appears_in_must_fix_when_broken(self):
        with self.site(fr=fr_page(back=False)) as s:
            res = ck.check(s.base, [])
        self.assertIn("hreflang return links", [e["check"] for e in ck.must_fix(res["findings"])])


class ProtocolAndHostRows(unittest.TestCase):
    def test_permanent_redirect_to_https_passes(self):
        for code in (301, 308):
            self.assertEqual(seo.protocol_row(code, "https://a.com/", "", "a.com")[0], "pass")

    def test_temporary_redirect_warns_with_a_fix(self):
        for code in (302, 303, 307):
            st, _, fix = seo.protocol_row(code, "https://a.com/", "", "a.com")
            self.assertEqual(st, "warn")
            self.assertIn("301", fix)

    def test_serving_content_over_http_warns(self):
        self.assertEqual(seo.protocol_row(200, "", "", "a.com")[0], "warn")

    def test_a_redirect_that_stays_on_http_warns(self):
        self.assertEqual(seo.protocol_row(301, "http://a.com/home", "", "a.com")[0], "warn")

    def test_a_closed_port_is_not_a_defect(self):
        self.assertEqual(seo.protocol_row(0, "", "refused", "a.com")[0], "info")

    def test_twin_host_rules(self):
        self.assertEqual(seo.twin_host("example.com"), "www.example.com")
        self.assertEqual(seo.twin_host("www.example.com"), "example.com")
        self.assertEqual(seo.twin_host("example.co.uk"), "www.example.co.uk")
        for none in ("127.0.0.1", "localhost", "blog.example.com", "example.com:8443", "app.localhost", "10.0.0.5", "shop.test"):
            self.assertIsNone(seo.twin_host(none), none)

    def test_host_row_outcomes(self):
        self.assertEqual(seo.host_row(301, "https://example.com/", "", "example.com", "www.example.com")[0], "pass")
        self.assertEqual(seo.host_row(302, "https://example.com/", "", "example.com", "www.example.com")[0], "warn")
        self.assertEqual(seo.host_row(301, "https://other.com/", "", "example.com", "www.example.com")[0], "warn")
        st, detail, fix = seo.host_row(200, "", "", "example.com", "www.example.com")
        self.assertEqual(st, "warn")
        self.assertIn("two URLs", detail)
        self.assertTrue(fix)
        self.assertEqual(seo.host_row(0, "", "dns", "example.com", "www.example.com")[0], "info")
        self.assertEqual(seo.host_row(503, "", "", "example.com", "www.example.com")[0], "info")


class Probe(unittest.TestCase):
    def test_it_reports_the_redirect_instead_of_following_it(self):
        with Site({"/": (301, {"Location": "https://example.com/"}, ""), "/final": "ok"}) as s:
            self.assertEqual(ck.probe(s.base + "/"), (301, "https://example.com/", ""))

    def test_it_reports_an_ordinary_status(self):
        with Site({"/": "ok"}) as s:
            self.assertEqual(ck.probe(s.base + "/")[0], 200)
            self.assertEqual(ck.probe(s.base + "/missing")[0], 404)

    def test_a_refused_connection_is_status_zero_with_the_error(self):
        status, loc, err = ck.probe("http://127.0.0.1:1/")
        self.assertEqual((status, loc), (0, ""))
        self.assertTrue(err)

    def test_the_http_variant_only_exists_for_default_port_https_targets(self):
        self.assertEqual(ck._http_variant("https://example.com"), "http://example.com/")
        self.assertIsNone(ck._http_variant("http://example.com"))
        self.assertIsNone(ck._http_variant("https://example.com:8443"))
        self.assertEqual(ck._twin_root("https://example.com"), ("www.example.com", "https://www.example.com/"))
        self.assertEqual(ck._twin_root("http://127.0.0.1:5000"), (None, None))


class HygieneEndToEnd(unittest.TestCase):
    def run_with(self, http_site, twin_site=None):
        with good_site() as s:
            patches = [mock.patch.object(ck, "_http_variant", lambda base: http_site.base + "/")]
            twin = (lambda base: ("www.example.test", twin_site.base + "/")) if twin_site else (lambda base: (None, None))
            patches.append(mock.patch.object(ck, "_twin_root", twin))
            for p in patches:
                p.start()
            try:
                return ck.check(s.base, []), s
            finally:
                mock.patch.stopall()

    def test_no_hygiene_rows_when_the_target_is_plain_http(self):
        with good_site() as s:
            res = ck.check(s.base, [])
        self.assertEqual([f for f in res["findings"] if f["check"] in ("HTTP to HTTPS redirect", "www and apex host")], [])

    def test_a_permanent_https_redirect_passes(self):
        with Site({"/": (301, {"Location": "https://x.test/"}, "")}) as h:
            res, _ = self.run_with(h)
        self.assertEqual(one(res, "HTTP to HTTPS redirect")["status"], "pass")

    def test_serving_http_directly_is_a_warning_and_a_must_fix(self):
        with Site({"/": "<html>plain</html>"}) as h:
            res, _ = self.run_with(h)
        r = one(res, "HTTP to HTTPS redirect")
        self.assertEqual(r["status"], "warn")
        self.assertIn("HTTP to HTTPS redirect", [e["check"] for e in ck.must_fix(res["findings"])])

    def test_the_twin_host_serving_the_site_is_a_warning(self):
        with Site({"/": "<html>dup</html>"}) as h, Site({"/": "<html>dup</html>"}) as t:
            res, _ = self.run_with(h, t)
        self.assertEqual(one(res, "www and apex host")["status"], "warn")

    def test_the_twin_redirecting_to_the_audited_host_passes(self):
        with good_site() as s, Site({"/": (301, {"Location": s.base + "/"}, "")}) as t, Site({"/": (301, {"Location": "https://x/"}, "")}) as h:
            with mock.patch.object(ck, "_http_variant", lambda base: h.base + "/"), \
                    mock.patch.object(ck, "_twin_root", lambda base: ("www.example.test", t.base + "/")):
                res = ck.check(s.base, [])
        self.assertEqual(one(res, "www and apex host")["status"], "pass")

    def test_each_hygiene_check_counts_as_one_scored_unit(self):
        with Site({"/": "<html>plain</html>"}) as h, Site({"/": "<html>dup</html>"}) as t:
            res, _ = self.run_with(h, t)
        groups = [f["group"] for f in res["findings"] if f["check"] in ("HTTP to HTTPS redirect", "www and apex host")]
        self.assertEqual(sorted(groups), ["seo:HTTP to HTTPS redirect", "seo:www and apex host"])

    def test_the_probes_contact_only_the_audited_host_and_its_twin(self):
        with Site({"/": (301, {"Location": "https://x.test/"}, "")}) as h, Site({"/": "dup"}) as t, good_site() as s:
            hosts = []
            real = ck._NO_FOLLOW.open

            def spy(req, *a, **kw):
                hosts.append(req.full_url.split("/")[2])
                return real(req, *a, **kw)

            with mock.patch.object(ck, "_http_variant", lambda base: h.base + "/"), \
                    mock.patch.object(ck, "_twin_root", lambda base: ("www.example.test", t.base + "/")), \
                    mock.patch.object(ck._NO_FOLLOW, "open", spy):
                ck.check(s.base, [])
        self.assertEqual(sorted(hosts), sorted([h.base.split("//")[1], t.base.split("//")[1]]))


if __name__ == "__main__":
    unittest.main()
