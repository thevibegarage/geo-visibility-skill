"""The slash-only skills in skills/: format, safety and that they agree with the scripts they run."""
import os
import re
import subprocess
import sys
import unittest

from helpers import ROOT, SKILL

SKILLS_DIR = os.path.join(ROOT, "skills")
EXPECTED = {"audit", "check", "track", "diagnose"}
ALLOWED_TOOLS = {"Bash(python3 *check_ai_readiness.py*)", "Bash(python3 *score_tracker.py*)", "Read"}
METACHARACTERS = ("`;`", "`&`", "`|`", "a backtick", "`$`", "`(`", "`)`", "`<`", "`>`")


def parse(path):
    """Minimal frontmatter parser (key: value lines), so the suite needs no YAML library."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"---\n(.*?)\n---\n(.*)\Z", text, re.S)
    assert m, f"{path} has no frontmatter"
    meta = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip().strip('"')
    return meta, m.group(2)


def all_skills():
    return {n: parse(os.path.join(SKILLS_DIR, n, "SKILL.md")) for n in sorted(os.listdir(SKILLS_DIR))
            if os.path.isfile(os.path.join(SKILLS_DIR, n, "SKILL.md"))}


def help_text(script):
    p = subprocess.run([sys.executable, os.path.join(SKILL, "scripts", script), "--help"], capture_output=True, text=True)
    return p.stdout


class Format(unittest.TestCase):
    def test_exactly_the_documented_commands_exist(self):
        self.assertEqual(set(all_skills()), EXPECTED)

    def test_every_command_is_slash_only_so_it_cannot_compete_with_the_main_skill(self):
        for name, (meta, _) in all_skills().items():
            self.assertEqual(meta.get("disable-model-invocation"), "true", name)

    def test_the_main_skill_stays_invocable_by_the_model(self):
        meta, _ = parse(os.path.join(SKILL, "SKILL.md"))
        self.assertNotIn("disable-model-invocation", meta)
        self.assertEqual(meta["name"], "geo-visibility")

    def test_required_fields(self):
        for name, (meta, body) in all_skills().items():
            self.assertTrue(meta.get("description"), name)
            self.assertLessEqual(len(meta["description"]), 400, name)
            self.assertTrue(meta.get("argument-hint"), name)
            self.assertIn("/geo-visibility:" + name, meta["description"], name)
            self.assertIn("$ARGUMENTS", body, name)

    def test_pre_approved_tools_are_limited_to_our_scripts_and_reading(self):
        for name, (meta, _) in all_skills().items():
            tools = set(re.findall(r"Bash\([^)]*\)|[A-Za-z]+", meta["allowed-tools"]))
            self.assertTrue(tools <= ALLOWED_TOOLS, f"{name}: {tools - ALLOWED_TOOLS}")
            self.assertNotIn("Bash(python3 *)", meta["allowed-tools"], name)  # never a blanket python3 grant

    def test_each_command_is_listed_in_the_readme(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
            readme = fh.read()
        for name in EXPECTED:
            self.assertIn(f"/geo-visibility:{name}", readme)


class Safety(unittest.TestCase):
    def test_commands_that_can_run_a_script_treat_arguments_as_data(self):
        for name, (meta, body) in all_skills().items():
            self.assertRegex(body, r"data typed by a person, not (an? )?instructions?", name)
            if name != "diagnose":
                for m in METACHARACTERS:
                    self.assertIn(m, body, f"{name} does not list {m} as a refusal trigger")
                self.assertIn("do not run anything", body, name)

    def test_diagnose_refuses_unknown_symptoms_rather_than_guessing(self):
        _, body = all_skills()["diagnose"]
        self.assertIn("ask; do not guess", body)

    def test_the_check_command_copies_the_table_verbatim(self):
        """Seen in a real session: told to show the table 'exactly as printed', the model shortened cells."""
        _, body = all_skills()["check"]
        self.assertIn("character for character", body)
        self.assertIn("Do not shorten", body)
        _, audit = all_skills()["audit"]
        self.assertIn("character for character", audit)


class AgreesWithTheScripts(unittest.TestCase):
    def test_every_file_the_commands_point_at_exists(self):
        for name, (_, body) in all_skills().items():
            refs = re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/(geo-visibility/[\w./-]+)", body)
            self.assertTrue(refs, name)
            for ref in refs:
                self.assertTrue(os.path.exists(os.path.join(ROOT, ref)), f"{name} points at missing {ref}")

    def test_every_flag_the_commands_use_exists_in_the_script_help(self):
        checker, tracker = help_text("check_ai_readiness.py"), help_text("score_tracker.py")
        for name, (_, body) in all_skills().items():
            for line in re.findall(r"`python3 [^`]+`", body):
                help_for = checker if "check_ai_readiness.py" in line else tracker if "score_tracker.py" in line else None
                self.assertIsNotNone(help_for, f"{name}: {line}")
                for flag in re.findall(r"--[a-z][a-z-]+", line):
                    self.assertIn(flag, help_for, f"{name} uses {flag}, which the script does not accept")

    def test_diagnose_table_matches_its_hint_and_points_at_real_files(self):
        meta, body = all_skills()["diagnose"]
        symptoms = [m for m in re.findall(r"^\| `([a-z-]+)` \|", body, re.M)]
        hint = [s.strip() for s in meta["argument-hint"].strip("<>").split("|")]
        self.assertEqual(symptoms, hint)
        for ref in set(re.findall(r"`(references/[\w-]+\.md)`", body)):
            self.assertTrue(os.path.exists(os.path.join(SKILL, ref)), ref)

    def test_the_settings_file_is_documented_where_the_commands_mention_it(self):
        for name in ("audit", "check"):
            _, body = all_skills()[name]
            self.assertIn("geo-visibility.json", body, name)


if __name__ == "__main__":
    unittest.main()
