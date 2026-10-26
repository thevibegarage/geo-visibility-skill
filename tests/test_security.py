"""SECURITY.md makes claims about what the scripts do. These tests enforce them."""
import ast
import contextlib
import io
import os
import tempfile
import unittest

from unittest import mock

from helpers import ROOT, SKILL, Site, ck, html_page, st, good_site

SCRIPTS = [os.path.join(SKILL, "scripts", n) for n in sorted(os.listdir(os.path.join(SKILL, "scripts"))) if n.endswith(".py")]
FORBIDDEN_MODULES = {"subprocess", "socket", "ctypes", "ftplib", "smtplib", "telnetlib", "http.client", "xmlrpc", "pickle",
                     "marshal", "shutil", "webbrowser", "multiprocessing", "asyncio"}
FORBIDDEN_BUILTINS = {"eval", "exec", "compile", "__import__"}  # bare calls; re.compile is fine
FORBIDDEN_ATTRIBUTE_CALLS = {"system", "popen", "spawnl", "spawnv", "execv", "execl", "fork"}


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class StaticClaims(unittest.TestCase):
    def test_no_process_network_or_dynamic_code_modules_are_imported(self):
        for path in SCRIPTS:
            tree = ast.parse(read(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for n in names:
                    self.assertNotIn(n, FORBIDDEN_MODULES, f"{os.path.basename(path)} imports {n}")
                    self.assertNotIn(n.split(".")[0], FORBIDDEN_MODULES, f"{os.path.basename(path)} imports {n}")

    def test_no_eval_exec_or_shell_calls(self):
        for path in SCRIPTS:
            for node in ast.walk(ast.parse(read(path))):
                if isinstance(node, ast.Call):
                    f = node.func
                    if isinstance(f, ast.Name):
                        self.assertNotIn(f.id, FORBIDDEN_BUILTINS, f"{os.path.basename(path)} calls {f.id}()")
                    elif isinstance(f, ast.Attribute):
                        self.assertNotIn(f.attr, FORBIDDEN_ATTRIBUTE_CALLS, f"{os.path.basename(path)} calls .{f.attr}()")

    def test_only_the_checker_touches_the_network(self):
        for path in SCRIPTS:
            uses_urllib = "urllib.request" in read(path)
            self.assertEqual(uses_urllib, os.path.basename(path) == "check_ai_readiness.py", os.path.basename(path))

    def test_security_md_names_each_enforced_claim(self):
        text = read(os.path.join(ROOT, "SECURITY.md"))
        for needle in ("No telemetry", "only when you pass `--json`", "Responsible use", "Prompt injection",
                       "Report a vulnerability", "Only the latest release is supported"):
            self.assertIn(needle, text)

    def test_security_md_describes_the_crawl_and_its_limits(self):
        text = read(os.path.join(ROOT, "SECURITY.md"))
        for needle in ("`--crawl`", "Googlebot", "robots.txt", "never another host", "HTTP 429", "link_crawl.py"):
            self.assertIn(needle, text)


class Runtime(unittest.TestCase):
    def record_hosts(self, fn):
        """Run fn while recording the host of every urlopen call made through the checker."""
        hosts = []
        real = ck.urllib.request.urlopen

        def spy(req, *a, **kw):
            hosts.append(req.full_url.split("/")[2] if hasattr(req, "full_url") else str(req))
            return real(req, *a, **kw)

        real_probe = ck._NO_FOLLOW.open  # the redirect-free probe uses its own opener, so it is recorded too

        def probe_spy(req, *a, **kw):
            hosts.append(req.full_url.split("/")[2])
            return real_probe(req, *a, **kw)

        ck.urllib.request.urlopen = spy
        ck._NO_FOLLOW.open = probe_spy
        try:
            fn()
        finally:
            ck.urllib.request.urlopen = real
            ck._NO_FOLLOW.open = real_probe
        return hosts

    def test_every_request_in_a_run_goes_to_the_target_host(self):
        with good_site() as s:
            hosts = self.record_hosts(lambda: ck.check(s.base, ["/pricing"], "indexnow-key-123456"))
            target = s.base.split("//")[1]
        self.assertGreater(len(hosts), 20)  # a full run makes about 30 requests; the point is that none leave the target
        self.assertEqual(set(hosts), {target})

    def test_the_only_other_hosts_contacted_are_ones_the_site_itself_lists(self):
        with good_site() as other, good_site() as s:
            s.routes["/robots.txt"] = (200, {"Content-Type": "text/plain"}, f"User-agent: *\nSitemap: {other.base}/sitemap.xml\n")
            hosts = self.record_hosts(lambda: ck.check(s.base, []))
            allowed = {s.base.split("//")[1], other.base.split("//")[1]}
        self.assertEqual(set(hosts), allowed)
        self.assertIn(other.base.split("//")[1], hosts)  # the listed sitemap host was contacted, as SECURITY.md says

    def test_a_run_without_json_leaves_the_working_directory_unchanged(self):
        old = os.getcwd()
        with good_site() as s, tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    ck.main([s.base, "--paths", "/pricing"])
                self.assertEqual(os.listdir(d), [])
                with contextlib.redirect_stdout(io.StringIO()):
                    ck.main([s.base, "--json", "out.json"])
                self.assertEqual(os.listdir(d), ["out.json"])
            finally:
                os.chdir(old)

    def crawl_routes(self):
        links = "".join(f'<a href="/p{i}">page {i}</a>' for i in range(12))
        return {"/": html_page(body_extra=links + '<a href="https://elsewhere.example/x">out</a><a href="/leave">leave</a>'
                                                   '<a href="https://www.127.0.0.1/twin">twin</a>'),
                "/leave": (302, {"Location": "https://elsewhere.example/landing"}, "")}

    def test_a_crawl_stays_on_the_target_host_and_inside_its_budget(self):
        with mock.patch.object(ck, "CRAWL_DELAY", 0), good_site(extra=self.crawl_routes()) as s:
            without = self.record_hosts(lambda: ck.check(s.base, ["/pricing"]))
            crawled = self.record_hosts(lambda: ck.check(s.base, ["/pricing"], crawl=5))
            target = s.base.split("//")[1]
        self.assertEqual(set(crawled), {target})  # pages link to and redirect to other hosts; none was contacted
        self.assertEqual(len(crawled) - len(without), 5)  # the budget is exact: a site with more pages gets no more requests

    def test_a_crawl_never_requests_what_robots_txt_disallows_googlebot(self):
        seen = []
        robots = "User-agent: Googlebot\nDisallow: /g-only/\n\nUser-agent: *\nDisallow: /star-only/\n\nSitemap: {base}/sitemap.xml\n"
        home = html_page(body_extra='<a href="/g-only/x">g</a><a href="/star-only/x">s</a><a href="/fine">f</a>')
        with mock.patch.object(ck, "CRAWL_DELAY", 0), good_site(
                extra={"/": home, "/robots.txt": lambda base: (200, {"Content-Type": "text/plain"}, robots.format(base=base)),
                       "/g-only/x": "private", "/star-only/x": "allowed for Googlebot", "/fine": "ok"},
                handler=lambda path, ua: seen.append(path)) as s:
            res = ck.check(s.base, [], crawl=30)
        self.assertNotIn("/g-only/x", seen)  # the group that names Googlebot applies to the crawl
        self.assertIn("/star-only/x", seen)  # and the "*" group does not (a named group does not inherit it)
        self.assertTrue(next(p for p in res["crawl"]["pages"] if p["url"].endswith("/g-only/x"))["blocked"])

    def test_a_crawl_without_json_leaves_the_working_directory_unchanged(self):
        old = os.getcwd()
        with mock.patch.object(ck, "CRAWL_DELAY", 0), good_site(extra=self.crawl_routes()) as s, tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    ck.main([s.base, "--crawl", "8"])
                self.assertEqual(os.listdir(d), [])
            finally:
                os.chdir(old)

    def test_the_tracker_makes_no_network_requests(self):
        calls = []
        real = ck.urllib.request.urlopen
        ck.urllib.request.urlopen = lambda *a, **k: calls.append(a) or real(*a, **k)
        try:
            with tempfile.TemporaryDirectory() as d:
                path = os.path.join(d, "t.csv")
                with open(path, "w") as fh:
                    fh.write("prompt_id,engine,mentioned,cited\nP1,ChatGPT,1,0\n")
                with contextlib.redirect_stdout(io.StringIO()):
                    st.main([path])
        finally:
            ck.urllib.request.urlopen = real
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
