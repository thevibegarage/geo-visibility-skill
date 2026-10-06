import unittest

from helpers import ck, asset

R = ck.Robots


class RobotsMatcher(unittest.TestCase):
    def ok(self, txt, ua, path):
        return R(txt).can_fetch(ua, "https://x.com" + path)

    def test_wildcard_and_end_anchor(self):
        txt = "User-agent: *\nDisallow: /*.pdf$"
        self.assertFalse(self.ok(txt, "GPTBot", "/a/b.pdf"))
        self.assertTrue(self.ok(txt, "GPTBot", "/a/b.pdf.html"))
        self.assertTrue(self.ok(txt, "GPTBot", "/a/b.html"))

    def test_wildcard_query_string(self):
        txt = "User-agent: *\nDisallow: /*?"
        self.assertFalse(self.ok(txt, "GPTBot", "/p?x=1"))
        self.assertTrue(self.ok(txt, "GPTBot", "/p"))

    def test_longest_match_wins_regardless_of_order(self):
        for txt in ("User-agent: *\nDisallow: /blog\nAllow: /blog/public",
                    "User-agent: *\nAllow: /blog/public\nDisallow: /blog"):
            self.assertTrue(self.ok(txt, "Bingbot", "/blog/public/x"), txt)
            self.assertFalse(self.ok(txt, "Bingbot", "/blog/private"), txt)

    def test_tie_goes_to_allow(self):
        self.assertTrue(self.ok("User-agent: *\nDisallow: /a\nAllow: /a", "Bingbot", "/a"))

    def test_named_group_does_not_inherit_star(self):
        txt = "User-agent: Googlebot\nAllow: /\n\nUser-agent: *\nDisallow: /admin/"
        self.assertTrue(self.ok(txt, "Googlebot", "/admin/x"))  # named group wins entirely
        self.assertFalse(self.ok(txt, "OAI-SearchBot", "/admin/x"))  # falls back to *

    def test_star_blocks_everything_not_named(self):
        txt = "User-agent: Googlebot\nAllow: /\n\nUser-agent: *\nDisallow: /"
        self.assertTrue(self.ok(txt, "Googlebot", "/"))
        self.assertFalse(self.ok(txt, "OAI-SearchBot", "/"))

    def test_agent_match_is_case_insensitive_and_exact(self):
        txt = "User-agent: BINGBOT\nDisallow: /"
        self.assertFalse(self.ok(txt, "Bingbot", "/"))
        self.assertTrue(self.ok(txt, "Bing", "/"))  # no substring matching

    def test_multiple_user_agent_lines_share_one_rule_block(self):
        txt = "User-agent: A\nUser-agent: B\nDisallow: /x/\n"
        self.assertFalse(self.ok(txt, "A", "/x/1"))
        self.assertFalse(self.ok(txt, "B", "/x/1"))
        self.assertTrue(self.ok(txt, "C", "/x/1"))

    def test_groups_for_same_agent_are_merged(self):
        txt = "User-agent: A\nDisallow: /one/\n\nUser-agent: A\nDisallow: /two/\n"
        self.assertFalse(self.ok(txt, "A", "/one/"))
        self.assertFalse(self.ok(txt, "A", "/two/"))

    def test_empty_disallow_allows_everything(self):
        self.assertTrue(self.ok("User-agent: *\nDisallow:", "GPTBot", "/anything"))

    def test_comments_blank_lines_and_unknown_fields(self):
        txt = "# hi\nUser-agent: *  # all\nCrawl-delay: 5\nDisallow: /p/ # private\nSitemap: https://x.com/s.xml\n"
        self.assertFalse(self.ok(txt, "GPTBot", "/p/1"))

    def test_no_groups_or_empty_file_allows_all(self):
        self.assertTrue(self.ok("", "GPTBot", "/x"))
        self.assertTrue(self.ok("Sitemap: https://x.com/s.xml", "GPTBot", "/x"))

    def test_byte_order_mark_does_not_hide_the_first_group(self):
        self.assertFalse(self.ok("\ufeffUser-agent: *\nDisallow: /", "GPTBot", "/x"))

    def test_rule_before_any_user_agent_is_ignored(self):
        self.assertTrue(self.ok("Disallow: /\nUser-agent: A\nAllow: /", "A", "/x"))


class ShippedRobotsTemplate(unittest.TestCase):
    """Regression: the old template listed named bots with only 'Allow: /', so the '*' group's
    private-path rules never applied to them and /admin/ etc. were open to every named crawler."""

    PRIVATE = ("/admin/", "/cart/", "/checkout/", "/account/")

    @classmethod
    def setUpClass(cls):
        cls.text = asset("assets", "robots-ai-template.txt")
        cls.robots = R(cls.text)
        cls.tokens = list(ck.AGENTS["search_and_user_fetch"]) + list(ck.AGENTS["training"])

    def test_private_paths_blocked_for_every_named_agent_and_everyone_else(self):
        for token in self.tokens + ["SomeRandomBot"]:
            for p in self.PRIVATE:
                self.assertFalse(self.robots.can_fetch(token, "https://x.com" + p + "page"), f"{token} can fetch {p}")

    def test_public_pages_allowed_for_named_agents(self):
        for token in self.tokens + ["SomeRandomBot"]:
            for p in ("/", "/pricing", "/blog/post"):
                self.assertTrue(self.robots.can_fetch(token, "https://x.com" + p), f"{token} blocked on {p}")

    def test_every_checked_agent_is_named_in_the_template(self):
        for token in self.tokens:
            self.assertIn(token, self.text, token)

    def test_disallow_precedes_allow_for_first_match_parsers(self):
        import urllib.robotparser as rp
        r = rp.RobotFileParser()
        r.parse(self.text.splitlines())
        self.assertFalse(r.can_fetch("Bingbot", "https://x.com/admin/x"))
        self.assertTrue(r.can_fetch("Bingbot", "https://x.com/pricing"))

    def test_sitemap_placeholder_present(self):
        self.assertIn("Sitemap: https://{{YOUR_DOMAIN}}/sitemap.xml", self.text)


if __name__ == "__main__":
    unittest.main()
