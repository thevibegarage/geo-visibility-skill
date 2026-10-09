"""Claude Code plugin packaging: the manifest, the marketplace file, and that they stay in sync with the repo.

Rules come from the official plugin and marketplace references (code.claude.com/docs/en/plugins). When the `claude`
CLI is installed, the official validator also runs; in CI (no CLI) that one test is skipped.
"""
import json
import os
import re
import shutil
import subprocess
import unittest
from urllib.parse import urlparse

from helpers import ROOT, SKILL

PLUGIN_JSON = os.path.join(ROOT, ".claude-plugin", "plugin.json")
MARKETPLACE_JSON = os.path.join(ROOT, ".claude-plugin", "marketplace.json")

PLUGIN_FIELDS = {
    "$schema", "name", "displayName", "version", "description", "author", "homepage", "repository", "license", "keywords",
    "metadata", "icon", "documentationUrl", "supportUrl", "privacyPolicyUrl", "termsOfServiceUrl", "defaultEnabled",
    "dependencies", "settings", "userConfig", "types", "channels", "skills", "commands", "agents", "hooks", "mcpServers",
    "lspServers", "outputStyles", "workflows", "experimental",
}
MARKETPLACE_FIELDS = {"$schema", "name", "owner", "plugins", "description", "version", "metadata", "forceRemoveDeletedPlugins",
                      "allowCrossMarketplaceDependenciesOn", "renames"}
ENTRY_FIELDS = ({"source", "category", "tags", "strict", "relevance", "headers", "headersHelper"} |
                (PLUGIN_FIELDS - {"icon", "documentationUrl", "supportUrl", "privacyPolicyUrl", "termsOfServiceUrl", "$schema"}))
RESERVED_MARKETPLACES = {
    "claude-code-marketplace", "claude-code-plugins", "claude-plugins-official", "anthropic-marketplace", "anthropic-plugins",
    "agent-skills", "anthropic-agent-skills", "life-sciences", "knowledge-work-plugins", "claude-for-legal",
    "claude-for-financial-services", "financial-services-plugins", "first-party-plugins", "claude-tag-plugins",
    "claude-community", "claude-plugins-community", "healthcare", "anthropic-plugin-directory", "claude-plugin-directory",
    "inline", "builtin", "skills-dir", "synced", "claude-plugin-test", "npm", "pip", "uv", "cargo", "github", "gh",
}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def latest_released_version():
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"## v(\d+\.\d+\.\d+)\b", line)
            if m:
                return m.group(1)
    raise AssertionError("no released version heading in CHANGELOG.md")


def reserved_plugin_name(name):
    n = re.sub(r"[-_.\s]+", "-", name.lower())
    return (n.startswith(("claude-", "anthropic-", "anthropics-", "cc-plugin-"))
            or n in {"claude", "anthropic", "anthropics", "claude-code", "claude-mods"}
            or ("official" in n.split("-") and bool({"claude", "anthropic"} & set(n.split("-")))))


class PluginManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load(PLUGIN_JSON)

    def test_name_is_kebab_case_and_not_reserved(self):
        name = self.m["name"]
        self.assertRegex(name, r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertFalse(reserved_plugin_name(name), name)

    def test_the_reserved_name_check_catches_what_the_docs_list(self):
        for bad in ("claude-evil", "anthropic-tools", "cc-plugin-x", "claude", "official-claude-tools", "Claude_Code"):
            self.assertTrue(reserved_plugin_name(bad), bad)
        for good in ("geo-visibility", "seo-toolkit", "deploy-tools"):
            self.assertFalse(reserved_plugin_name(good), good)

    def test_only_documented_top_level_fields_are_used(self):
        self.assertEqual(set(self.m) - PLUGIN_FIELDS, set())

    def test_skill_paths_start_with_dot_slash_exist_and_hold_a_skill(self):
        paths = self.m["skills"]
        self.assertIsInstance(paths, list)
        for p in paths:
            self.assertTrue(p.startswith("./"), p)
            self.assertNotIn("..", p)
            full = os.path.normpath(os.path.join(ROOT, p))
            self.assertTrue(os.path.isdir(full), p)
            self.assertTrue(os.path.isfile(os.path.join(full, "SKILL.md")), f"{p} must hold SKILL.md directly")

    def test_the_skill_folder_matches_what_the_manifest_points_at(self):
        self.assertEqual(self.m["skills"], ["./" + os.path.basename(SKILL) + "/"])

    def test_version_matches_the_latest_released_changelog_entry(self):
        """Setting `version` pins users until it changes, so a release must bump it together with the changelog."""
        self.assertEqual(self.m["version"], latest_released_version())

    def test_metadata_is_present_and_consistent(self):
        self.assertEqual(self.m["license"], "MIT")
        with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as fh:
            self.assertTrue(fh.read().lstrip().startswith("MIT License"))
        for key in ("homepage", "repository"):
            u = urlparse(self.m[key])
            self.assertEqual((u.scheme, u.netloc), ("https", "github.com"), key)
        self.assertTrue(self.m["author"]["name"])
        self.assertGreaterEqual(len(self.m["keywords"]), 3)
        self.assertLessEqual(len(self.m["description"]), 400)

    def test_description_matches_the_skill_scope(self):
        for engine in ("ChatGPT", "Claude", "Gemini", "Perplexity", "Copilot"):
            self.assertIn(engine, self.m["description"])


class Marketplace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mk = load(MARKETPLACE_JSON)
        cls.plugin = load(PLUGIN_JSON)

    def test_required_fields_and_name_rules(self):
        self.assertEqual(set(self.mk) - MARKETPLACE_FIELDS, set())
        self.assertRegex(self.mk["name"], r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
        self.assertNotIn("..", self.mk["name"])
        self.assertNotIn(self.mk["name"].lower(), RESERVED_MARKETPLACES)
        self.assertFalse(self.mk["name"].lower().startswith("claudeai-"))
        self.assertTrue(self.mk["owner"]["name"])
        self.assertTrue(self.mk["description"])

    def test_marketplace_name_differs_from_the_github_download_folder(self):
        # Claude Code downloads a GitHub marketplace into <owner>-<repo>; a different marketplace name must not collide with it
        self.assertNotEqual(self.mk["name"], "thevibegarage-geo-visibility-skill")

    def test_one_entry_that_points_at_this_repository_root(self):
        self.assertEqual(len(self.mk["plugins"]), 1)
        entry = self.mk["plugins"][0]
        self.assertEqual(entry["source"], "./")
        self.assertTrue(os.path.isfile(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
        self.assertEqual(set(entry) - ENTRY_FIELDS, set())

    def test_entry_name_matches_the_manifest_name(self):
        """A mismatch makes users install under one name and get components namespaced under another."""
        self.assertEqual(self.mk["plugins"][0]["name"], self.plugin["name"])

    def test_entry_does_not_repeat_the_version(self):
        """plugin.json wins over the entry's version and the validator warns on a duplicate; keep one source of truth."""
        self.assertNotIn("version", self.mk["plugins"][0])

    def test_entry_names_are_unique_and_valid(self):
        names = [p["name"] for p in self.mk["plugins"]]
        self.assertEqual(len(names), len(set(names)))
        for n in names:
            self.assertRegex(n, r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class DocsStayInSync(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
            return fh.read()

    def test_readme_gives_the_exact_install_commands(self):
        readme = self.read("README.md")
        mk, plugin = load(MARKETPLACE_JSON), load(PLUGIN_JSON)
        self.assertIn("claude plugin marketplace add thevibegarage/geo-visibility-skill", readme)
        self.assertIn(f"claude plugin install {plugin['name']}@{mk['name']}", readme)
        self.assertIn(f"claude plugin update {plugin['name']}@{mk['name']}", readme)

    def test_contributing_documents_the_release_checklist(self):
        text = self.read("CONTRIBUTING.md")
        for needle in ("plugin.json", "CHANGELOG.md", "claude plugin validate"):
            self.assertIn(needle, text)

    def test_the_downloadable_skill_does_not_ship_plugin_metadata(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        try:
            import build_skill
        finally:
            sys.path.pop(0)
        arcs = [arc for _, arc in build_skill.files()]
        self.assertTrue(arcs)
        self.assertFalse([a for a in arcs if ".claude-plugin" in a])


@unittest.skipUnless(shutil.which("claude"), "claude CLI not installed (skipped in CI)")
class OfficialValidator(unittest.TestCase):
    """Runs the real `claude plugin validate --strict` on both manifests."""

    def validate(self, path):
        p = subprocess.run(["claude", "plugin", "validate", "--strict", path], capture_output=True, text=True, timeout=120)
        return p.returncode, (p.stdout + p.stderr)

    def test_marketplace_passes(self):
        code, out = self.validate(ROOT)
        self.assertEqual(code, 0, out)
        self.assertIn("Validation passed", out)

    def test_plugin_manifest_passes(self):
        code, out = self.validate(PLUGIN_JSON)
        self.assertEqual(code, 0, out)
        self.assertIn("Validation passed", out)


if __name__ == "__main__":
    unittest.main()
