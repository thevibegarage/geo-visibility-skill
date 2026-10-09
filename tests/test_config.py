import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

from helpers import SKILL, ROOT, Site, good_site, ck, st

sys.path.insert(0, os.path.join(SKILL, "scripts"))
import geo_config  # noqa: E402


def write(directory, data, name="geo-visibility.json", raw=False):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data if raw else json.dumps(data))
    return path


@contextlib.contextmanager
def cwd(path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def run(mod, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = mod.main(argv)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


class Loader(unittest.TestCase):
    def test_no_file_means_no_settings(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(geo_config.load(cwd=d), {})
            self.assertIsNone(geo_config.find(cwd=d))

    def test_valid_file_is_read_and_trimmed(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, {"domain": " example.com ", "paths": ["/a", "/b"], "indexnow_key": "k" * 16, "brand": "Acme"})
            self.assertEqual(geo_config.load(cwd=d), {"domain": "example.com", "paths": ["/a", "/b"], "indexnow_key": "k" * 16, "brand": "Acme"})

    def test_explicit_path_wins_over_the_default_name(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, {"domain": "default.example"})
            other = write(d, {"domain": "other.example"}, name="other.json")
            self.assertEqual(geo_config.load(other, cwd=d)["domain"], "other.example")

    def test_missing_explicit_file_is_an_error(self):
        with self.assertRaises(geo_config.ConfigError) as cm:
            geo_config.load("/no/such/file.json")
        self.assertIn("not found", str(cm.exception))

    def test_unknown_keys_are_an_error_not_silently_ignored(self):
        """A typo such as "domian" must not produce an audit of nothing."""
        with tempfile.TemporaryDirectory() as d:
            write(d, {"domian": "example.com"})
            with self.assertRaises(geo_config.ConfigError) as cm:
                geo_config.load(cwd=d)
        self.assertIn("unknown key(s) domian", str(cm.exception))
        self.assertIn("allowed keys are", str(cm.exception))

    def test_bad_json_and_wrong_shapes(self):
        cases = {
            "{not json": "not valid JSON",
            "[1, 2]": "must contain a JSON object",
            json.dumps({"domain": ""}): '"domain" must be a non-empty string',
            json.dumps({"domain": 5}): '"domain" must be a non-empty string',
            json.dumps({"brand": "  "}): '"brand" must be a non-empty string',
            json.dumps({"paths": "/a"}): '"paths" must be a list',
            json.dumps({"paths": ["a"]}): 'start with "/"',
            json.dumps({"paths": [1]}): 'start with "/"',
        }
        for raw, message in cases.items():
            with self.subTest(raw=raw):
                with tempfile.TemporaryDirectory() as d:
                    write(d, raw, raw=True)
                    with self.assertRaises(geo_config.ConfigError) as cm:
                        geo_config.load(cwd=d)
                self.assertIn(message, str(cm.exception))

    def test_a_byte_order_mark_is_tolerated(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "geo-visibility.json")
            with open(path, "wb") as fh:
                fh.write(b"\xef\xbb\xbf" + json.dumps({"domain": "example.com"}).encode())
            self.assertEqual(geo_config.load(cwd=d), {"domain": "example.com"})

    def test_the_shipped_example_is_valid_and_complete(self):
        settings = geo_config.load(os.path.join(ROOT, "examples", "geo-visibility.json"))
        self.assertEqual(set(settings), set(geo_config.KNOWN_KEYS))


class CheckerUsesTheFile(unittest.TestCase):
    def test_no_domain_and_no_file_is_a_clear_usage_error(self):
        with tempfile.TemporaryDirectory() as d, cwd(d):
            code, out, err = run(ck, [])
        self.assertEqual(code, 4)
        self.assertEqual(out, "")
        self.assertIn("no domain given", err)
        self.assertIn("geo-visibility.json", err)

    def test_domain_paths_and_key_come_from_the_file(self):
        key = "indexnowkey123456"
        with good_site(extra={f"/{key}.txt": key}) as s, tempfile.TemporaryDirectory() as d, cwd(d):
            write(d, {"domain": s.base, "paths": ["/pricing"], "indexnow_key": key})
            code, out, err = run(ck, [])
        self.assertEqual(code, 0, err)
        self.assertIn("render by agent: /pricing", out.replace("\\", ""))
        self.assertRegex(out, r"IndexNow key file \| pass")

    def test_arguments_override_the_file(self):
        with good_site() as real, tempfile.TemporaryDirectory() as d, cwd(d):
            write(d, {"domain": "http://127.0.0.1:1", "paths": ["/nowhere"], "indexnow_key": "wrongwrongwrong1"})
            code, out, err = run(ck, [real.base, "--paths", "/pricing", "--indexnow-key", "anotherkey123456"])
        self.assertEqual(code, 0, err)
        self.assertIn(real.base, out)
        self.assertNotIn("/nowhere", out)
        self.assertRegex(out, r"IndexNow key file \| warn")  # the argument's key was used, and is not hosted

    def test_an_empty_paths_argument_clears_the_files_paths(self):
        with good_site() as s, tempfile.TemporaryDirectory() as d, cwd(d):
            write(d, {"domain": s.base, "paths": ["/pricing"]})
            _, with_file, _ = run(ck, [])
            _, cleared, _ = run(ck, ["--paths"])
        self.assertIn("render by agent: /pricing", with_file)
        self.assertNotIn("render by agent: /pricing", cleared)

    def test_explicit_config_path(self):
        with good_site() as s, tempfile.TemporaryDirectory() as d:
            path = write(d, {"domain": s.base}, name="site.json")
            code, out, err = run(ck, ["--config", path])
        self.assertEqual(code, 0, err)
        self.assertIn(s.base, out)

    def test_a_bad_file_stops_the_run_with_exit_4_and_no_request(self):
        with tempfile.TemporaryDirectory() as d, cwd(d):
            write(d, {"domian": "oops.example"})
            code, out, err = run(ck, [])
        self.assertEqual(code, 4)
        self.assertEqual(out, "")
        self.assertIn("unknown key(s) domian", err)

    def test_the_file_is_used_by_the_script_run_as_a_program(self):
        import subprocess
        with good_site() as s, tempfile.TemporaryDirectory() as d:
            write(d, {"domain": s.base})
            p = subprocess.run([sys.executable, os.path.join(SKILL, "scripts", "check_ai_readiness.py"), "--issues-only"],
                               capture_output=True, text=True, cwd=d)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("## Must fix (0)", p.stdout)


class TrackerUsesTheFile(unittest.TestCase):
    CSV = ("prompt_id,stage,prompt,engine,mode,run,mentioned,cited,position,sentiment,accurate,competitors,cited_domains\n"
           "P01,category,q,ChatGPT,search,1,1,,1,,,A,www.acme.com\n")

    def run_tracker(self, args, settings):
        with tempfile.TemporaryDirectory() as d, cwd(d):
            csv_path = write(d, self.CSV, name="t.csv", raw=True)
            if settings is not None:
                write(d, settings)
            return run(st, [csv_path, *args])

    def test_brand_and_domain_default_to_the_file(self):
        code, out, err = self.run_tracker([], {"brand": "Acme", "domain": "acme.com"})
        self.assertIn("# AI visibility roll-up for Acme", out)
        self.assertIn("| ChatGPT | 1 | 100 | 100 |", out)  # cited derived from www.acme.com via the file's domain

    def test_arguments_override_the_file(self):
        _, out, _ = self.run_tracker(["--brand", "Other", "--domain", "nomatch.com"], {"brand": "Acme", "domain": "acme.com"})
        self.assertIn("for Other", out)
        self.assertIn("| ChatGPT | 1 | 100 | 0 |", out)

    def test_without_a_file_nothing_changes(self):
        _, out, _ = self.run_tracker([], None)
        self.assertIn("# AI visibility roll-up\n", out)

    def test_a_bad_file_is_a_clear_error(self):
        code, out, err = self.run_tracker([], {"domian": "x"})
        self.assertNotEqual(code, 0)
        self.assertIn("unknown key(s) domian", str(code) + err)


if __name__ == "__main__":
    unittest.main()
