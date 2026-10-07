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
