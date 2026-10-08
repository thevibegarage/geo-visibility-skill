import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

from helpers import ROOT, SKILL, Site, good_site

try:
    import yaml
except ImportError:  # PyYAML is optional; the workflow-syntax test is skipped without it
    yaml = None

SCRIPTS = [os.path.join(SKILL, "scripts", n) for n in ("check_ai_readiness.py", "score_tracker.py")]


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


class SkillManifest(unittest.TestCase):
    def test_frontmatter(self):
        text = read(SKILL, "SKILL.md")
        m = re.match(r"---\nname: (.+)\ndescription: (.+)\nlicense: (.+)\n---\n", text)
        self.assertIsNotNone(m, "SKILL.md must start with name/description/license frontmatter")
        self.assertEqual(m.group(1), "geo-visibility")
        self.assertLessEqual(len(m.group(2)), 1024, "skill descriptions are limited to 1024 characters")
        for word in ("Copilot", "Bing", "IndexNow"):
            self.assertIn(word, m.group(2), f"description should trigger on {word}")

    def test_skill_md_stays_short(self):
        self.assertLess(len(read(SKILL, "SKILL.md").splitlines()), 500)

    def test_reference_map_matches_the_files_on_disk(self):
        text = read(SKILL, "SKILL.md")
        on_disk = {f for f in os.listdir(os.path.join(SKILL, "references")) if f.endswith(".md")}
        mapped = set(re.findall(r"`references/([\w-]+\.md)`", text))
        self.assertEqual(mapped, on_disk)
        self.assertIn("bing-copilot.md", on_disk)

    def test_every_path_mentioned_in_the_docs_exists(self):
        for root, _, names in os.walk(SKILL):
            for n in names:
                if not n.endswith(".md"):
                    continue
                text = read(root, n)
                for rel in re.findall(r"`((?:references|assets|scripts)/[\w.-]+)`", text):
                    self.assertTrue(os.path.exists(os.path.join(SKILL, rel)), f"{n} mentions missing {rel}")

    def test_cross_references_between_reference_files_resolve(self):
        refs = os.path.join(SKILL, "references")
        for n in os.listdir(refs):
            for target in re.findall(r"`([\w-]+\.md)`", read(refs, n)):
                found = os.path.exists(os.path.join(refs, target)) or os.path.exists(os.path.join(SKILL, target))
                self.assertTrue(found, f"{n} mentions missing {target}")


class ReadmeAndExamples(unittest.TestCase):
    DEMO = os.path.join(ROOT, "examples", "demo-site-output.md")

    def docs(self):
        out = [os.path.join(ROOT, n) for n in ("README.md", "CONTRIBUTING.md", "CHANGELOG.md")]
        out += [os.path.join(ROOT, "examples", n) for n in os.listdir(os.path.join(ROOT, "examples")) if n.endswith(".md")]
        return out

    def test_relative_links_resolve(self):
        for path in self.docs():
            base = os.path.dirname(path)
            # "../../releases" style links are GitHub-relative URLs (they resolve on github.com, not on disk)
            for target in re.findall(r"\]\((?!https?:|#|mailto:|\.\./\.\./)([^)\s#]+)", read(path)):
                resolved = os.path.normpath(os.path.join(base, target))
                self.assertTrue(os.path.exists(resolved), f"{os.path.relpath(path, ROOT)} links to missing {target}")

    def test_readme_excerpt_is_verbatim_from_the_demo_output(self):
        """The README shows 'real, unedited output': every table row it shows must exist in the demo file."""
        demo = read(self.DEMO)
        rows = [l for l in read(ROOT, "README.md").splitlines() if re.match(r"\| (\d+ \||`/|Page \|)", l) or l.startswith("Technical readiness:")]
        self.assertGreaterEqual(len(rows), 12)  # score line + 8 Must fix rows + the words-per-agent table
        for row in rows:
            self.assertIn(row, demo, f"README row not found in the demo output: {row[:80]}")

    def test_numbers_quoted_in_the_readme_prose_come_from_the_demo_output(self):
        prose = read(ROOT, "README.md").split("`/features` shows why")[1].split("(The prompt-audit side")[0]
        demo = read(self.DEMO)
        for number in re.findall(r"\b\d{3}\b", prose):
            self.assertIn(number, demo, f"{number} is quoted in the README but is not in the demo output")

    def test_readme_must_fix_count_matches_its_rows(self):
        text = read(ROOT, "README.md")
        n = int(re.search(r"#### Must fix \((\d+)\)", text).group(1))
        block = text.split("#### Must fix")[1].split("It tests the way")[0]
        self.assertEqual(len(re.findall(r"^\| \d+ \| (?:fail|warn) \|", block, re.M)), n)

    def test_demo_output_has_the_documented_shape(self):
        demo = read(self.DEMO)
        self.assertIn("Real, unedited output", demo)
        self.assertIn("check_ai_readiness.py", demo)
        self.assertIn("fictional", demo)
        self.assertRegex(demo, r"\*\*[0-9]{2,3}%\*\* \(\d+ failures, \d+ warnings\)")
        n = int(re.search(r"## Must fix \((\d+)\)", demo).group(1))
        self.assertEqual(len(re.findall(r"^\| \d+ \| (?:fail|warn) \|", demo.split("## Worth checking")[0], re.M)), n)
        for section in ("## Worth checking (not scored)", "## Other notes", "## Words each agent received", "## What was planted"):
            self.assertIn(section, demo)

    def test_illustrative_report_is_clearly_labelled_and_points_to_the_demo(self):
        text = read(ROOT, "examples", "sample-report.md")
        self.assertIn("illustrative example", text)
        self.assertIn("Every number here is invented", text)
        self.assertIn("demo-site-output.md", text)

    def test_no_real_company_is_the_subject_of_any_example_or_test(self):
        """Examples show a fictional site only. (The domain is built from parts so this file does not contain it.)"""
        domain = "garage" + "labstech"
        allowed = ("Built and open-sourced by", "Full audit on a real brand", "Copyright (c)", "\u00a9 2026")
        for folder in ("examples", "tools", "tests", os.path.join("geo-visibility", "evals"), os.path.join("geo-visibility", "references")):
            for dirpath, _, names in os.walk(os.path.join(ROOT, folder)):
                for n in names:
                    if n.endswith((".md", ".py", ".json", ".txt", ".csv")):
                        self.assertNotIn(domain, read(dirpath, n).lower(), os.path.join(dirpath, n))
        for name in ("README.md", "CHANGELOG.md"):
            for line in read(ROOT, name).splitlines():
                if domain in line.lower():
                    self.assertTrue(any(a in line for a in allowed), f"{name} names a real site outside attribution: {line[:100]}")

    def test_mermaid_diagram_is_present_and_balanced(self):
        text = read(ROOT, "README.md")
        block = re.search(r"```mermaid\n(.*?)```", text, re.S)
        self.assertIsNotNone(block)
        self.assertIn("flowchart", block.group(1))
        self.assertEqual(block.group(1).count("["), block.group(1).count("]"))

    def test_readme_test_count_is_not_stale(self):
        claimed = int(re.search(r"\u2705 (\d+) tests", read(ROOT, "README.md")).group(1))
        actual = unittest.TestLoader().discover(os.path.dirname(os.path.abspath(__file__))).countTestCases()
        self.assertEqual(claimed, actual, "update the test count in README.md")


class Evals(unittest.TestCase):
    def test_shape(self):
        data = json.loads(read(SKILL, "evals", "evals.json"))
        evals = data["evals"]
        self.assertEqual([e["id"] for e in evals], list(range(1, len(evals) + 1)))
        for e in evals:
            self.assertTrue(e["prompt"].strip())
            self.assertTrue(e["expected_output"].strip())
            self.assertIsInstance(e["files"], list)
            self.assertIsInstance(e["assertions"], list)
            self.assertGreaterEqual(len(e["assertions"]), 3, f"eval {e['id']} needs checkable assertions")
            self.assertTrue(all(isinstance(a, str) and a.strip() for a in e["assertions"]))

    def test_covers_bing_snippet_robots_brave_tracker_and_markets(self):
        blob = read(SKILL, "evals", "evals.json").lower()
        for needle in ("copilot", "nosnippet", "user-agent: gptbot", "brave", "score_tracker.py", "japan"):
            self.assertIn(needle, blob)


class Scripts(unittest.TestCase):
    def test_standard_library_only(self):
        stdlib = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else None
        for path in SCRIPTS:
            tree = ast.parse(read(path))
            for node in ast.walk(tree):
                names = [a.name.split(".")[0] for a in node.names] if isinstance(node, ast.Import) else \
                        [node.module.split(".")[0]] if isinstance(node, ast.ImportFrom) and node.module else []
                for n in names:
                    if stdlib is not None:
                        self.assertIn(n, stdlib, f"{os.path.basename(path)} imports non-stdlib {n}")

    def test_syntax_is_python_38_compatible(self):
        for path in SCRIPTS:
            ast.parse(read(path), feature_version=(3, 8))

    def test_help_runs(self):
        for path in SCRIPTS:
            p = subprocess.run([sys.executable, path, "--help"], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("usage", p.stdout.lower())


@unittest.skipIf(yaml is None, "PyYAML not installed")
class Workflows(unittest.TestCase):
    def load(self, name):
        return yaml.safe_load(read(ROOT, ".github", "workflows", name))

    def test_both_workflows_parse(self):
        for name in ("ai-readiness.yml", "tests.yml"):
            wf = self.load(name)
            self.assertIn("jobs", wf)

    def test_readiness_workflow_propagates_the_exit_code(self):
        run = next(s["run"] for s in self.load("ai-readiness.yml")["jobs"]["check"]["steps"] if "run" in s)
        self.assertIn("pipefail", run)
        self.assertIn("--fail-on fail", run)
        self.assertIn("--issues-only", run)
        self.assertIn("--indexnow-key", run)

    def test_tests_workflow_runs_the_suite(self):
        steps = self.load("tests.yml")["jobs"]["test"]["steps"]
        self.assertTrue(any("unittest discover -s tests" in s.get("run", "") for s in steps))


class WorkflowCommandShape(unittest.TestCase):
    """Run the workflow's pipeline shape in bash: `script ... --fail-on fail | tee` must keep the script's exit code."""

    def run_shape(self, base):
        script = os.path.join(SKILL, "scripts", "check_ai_readiness.py")
        with tempfile.TemporaryDirectory() as d:
            cmd = (f'set -o pipefail; set -f; PATHS="/pricing"; python3 "{script}" "{base}" --paths $PATHS '
                   f'--json "{d}/r.json" --fail-on fail --issues-only | tee "{d}/summary.md" >/dev/null')
            return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True).returncode

    def test_exit_codes_survive_tee(self):
        robots = (200, {"Content-Type": "text/plain"}, "User-agent: OAI-SearchBot\nDisallow: /\n")
        with good_site() as ok, good_site(extra={"/robots.txt": robots}) as bad, Site(handler=lambda p, ua: (403, {}, "x")) as blocked:
            self.assertEqual(self.run_shape(ok.base), 0)
            self.assertEqual(self.run_shape(bad.base), 1)
            self.assertEqual(self.run_shape(blocked.base), 3)


class BuildSkill(unittest.TestCase):
    def test_archive_contents(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        try:
            import build_skill
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as d:
            out = build_skill.build(os.path.join(d, "geo-visibility.skill"))
            names = zipfile.ZipFile(out).namelist()
        self.assertIn("geo-visibility/SKILL.md", names)
        self.assertIn("geo-visibility/references/bing-copilot.md", names)
        self.assertIn("geo-visibility/scripts/check_ai_readiness.py", names)
        self.assertIn("geo-visibility/assets/robots-ai-template.txt", names)
        self.assertTrue(all(n.startswith("geo-visibility/") for n in names))
        self.assertFalse([n for n in names if "evals" in n or "__pycache__" in n or n.endswith(".pyc") or "tests" in n])


if __name__ == "__main__":
    unittest.main()
