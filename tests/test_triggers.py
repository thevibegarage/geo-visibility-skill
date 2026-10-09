"""The activation-test tool (tools/trigger_sim.py) and its prompt set. Model runs are not repeatable in CI, so these test
everything around them: the prompt set's integrity, menu building, batching, answer parsing and the scoring maths."""
import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest

from helpers import ROOT, SKILL

spec = importlib.util.spec_from_file_location("trigger_sim", os.path.join(ROOT, "tools", "trigger_sim.py"))
ts = importlib.util.module_from_spec(spec)
sys.modules["trigger_sim"] = ts
spec.loader.exec_module(ts)

PROMPTS = ts.load_prompts()


def fake_competitor(root, skills):
    base = os.path.join(root, "rival-seo", "skills")
    for name, front in skills.items():
        os.makedirs(os.path.join(base, name))
        with open(os.path.join(base, name, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write(f"---\n{front}\n---\n\nBody\n")
    return os.path.join(root, "rival-seo")


class PromptSet(unittest.TestCase):
    def test_ids_are_unique_and_consecutive(self):
        self.assertEqual([p["id"] for p in PROMPTS], list(range(1, len(PROMPTS) + 1)))

    def test_fields_and_values(self):
        for p in PROMPTS:
            self.assertIn(p["split"], ("dev", "test"))
            self.assertIn(p["expect"], ("fire", "no-fire"))
            self.assertGreater(len(p["prompt"].split()), 3)
            self.assertLess(len(p["prompt"]), 200)

    def test_balanced_across_split_and_expectation(self):
        for split in ("dev", "test"):
            for expect in ("fire", "no-fire"):
                self.assertEqual(sum(1 for p in PROMPTS if p["split"] == split and p["expect"] == expect), 10)

    def test_no_duplicate_prompts(self):
        texts = [p["prompt"].lower() for p in PROMPTS]
        self.assertEqual(len(texts), len(set(texts)))

    def test_prompts_never_name_the_skill_or_its_commands(self):
        """A prompt that says 'geo-visibility' or '/geo-visibility:audit' would make routing trivial."""
        for p in PROMPTS:
            self.assertNotRegex(p["prompt"].lower(), r"geo-visibility|/geo|skill")

    def test_no_fire_prompts_say_who_should_handle_them(self):
        for p in PROMPTS:
            if p["expect"] == "no-fire":
                self.assertTrue(p["note"], p["id"])

    def test_the_split_rule_is_written_down(self):
        with open(os.path.join(SKILL, "evals", "triggers.json"), encoding="utf-8") as fh:
            about = json.load(fh)["about"]
        self.assertIn("dev", about)
        self.assertIn("held-out", about)
        self.assertIn("must not be used to tune", about)


class Menu(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.comp = fake_competitor(self.tmp.name, {
            "alpha": 'description: Does alpha things. Use when asked about "alpha".',
            "beta": 'description: Does beta things.',
            "quiet": 'description: Slash only.\ndisable-model-invocation: true',
            "nodesc": "name: nodesc",
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_competitor_entries_use_plugin_prefixed_names_and_skip_unlistable_skills(self):
        names = [n for n, _ in ts.competitor_entries(self.comp)]
        self.assertEqual(names, ["rival-seo:alpha", "rival-seo:beta"])  # slash-only and description-less skills are not on a model's menu

    def test_the_label_replaces_the_folder_name_so_no_vendor_is_named(self):
        names = [n for n, _ in ts.competitor_entries(self.comp, "rival-seo")]
        self.assertTrue(all(n.startswith("rival-seo:") for n in names))
        self.assertEqual(ts.competitor_entries(self.comp, "x")[0][0], "x:alpha")

    def test_prepare_uses_the_neutral_label_by_default_on_the_command_line(self):
        with tempfile.TemporaryDirectory() as d:
            comp = fake_competitor(d, {"alpha": "description: Alpha."})
            out = os.path.join(d, "run")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ts.main(["prepare", "--competitors", comp, "--out", out]), 0)
            with open(os.path.join(out, "jobs", "A-1.md"), encoding="utf-8") as fh:
                self.assertIn("- rival-seo:alpha: Alpha.", fh.read())

    def test_our_entry_is_the_real_description(self):
        name, desc = ts.our_entry()
        self.assertEqual(name, ts.OURS)
        with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as fh:
            self.assertIn(desc, fh.read())

    def test_order_a_puts_ours_first_and_b_puts_it_last_with_the_same_contents(self):
        comps = ts.competitor_entries(self.comp)
        a, b = ts.menu("A", comps), ts.menu("B", comps)
        self.assertEqual(a[0][0], ts.OURS)
        self.assertEqual(b[-1][0], ts.OURS)
        self.assertEqual(sorted(n for n, _ in a), sorted(n for n, _ in b))
        self.assertEqual(len(a), 1 + 2 + len(ts.DISTRACTORS))

    def test_menus_are_deterministic(self):
        comps = ts.competitor_entries(self.comp)
        self.assertEqual(ts.menu("A", comps), ts.menu("A", comps))

    def test_unknown_order_is_rejected(self):
        with self.assertRaises(ValueError):
            ts.menu("C", [])

    def test_menu_text_is_one_line_per_skill(self):
        text = ts.menu_text([("x:y", "does y"), ("z", "does z")])
        self.assertEqual(text, "- x:y: does y\n- z: does z")


class Batching(unittest.TestCase):
    def test_every_prompt_appears_exactly_once_per_order(self):
        for order in ts.ORDERS:
            ids = [p["id"] for b in ts.batches(PROMPTS, order) for p in b]
            self.assertEqual(sorted(ids), [p["id"] for p in PROMPTS])

    def test_batches_have_the_documented_size_and_mix_both_kinds(self):
        for order in ts.ORDERS:
            bs = ts.batches(PROMPTS, order)
            self.assertEqual([len(b) for b in bs], [10, 10, 10, 10])
            self.assertTrue(any(len({p["expect"] for p in b}) == 2 for b in bs))

    def test_orders_shuffle_differently_but_stably(self):
        a, b = ts.batches(PROMPTS, "A"), ts.batches(PROMPTS, "B")
        self.assertNotEqual([p["id"] for p in a[0]], [p["id"] for p in b[0]])
        self.assertEqual([p["id"] for p in ts.batches(PROMPTS, "A")[0]], [p["id"] for p in a[0]])

    def test_job_text_has_everything_a_router_needs_and_nothing_that_gives_the_answer(self):
        batch = ts.batches(PROMPTS, "A")[0]
        text = ts.job_text([(ts.OURS, "desc")], batch, "/tmp/answers/A-1.jsonl")
        self.assertIn("/tmp/answers/A-1.jsonl", text)
        for p in batch:
            self.assertIn(f'{p["id"]}. {p["prompt"]}', text)
        self.assertNotRegex(text.lower(), r"\bfire\b|no-fire|\bexpect\b|\bdev\b|\bsplit\b")  # nothing that reveals the answer key


class Prepare(unittest.TestCase):
    def test_prepare_writes_eight_jobs_and_answer_folder(self):
        with tempfile.TemporaryDirectory() as d:
            comp = fake_competitor(d, {"alpha": "description: Alpha."})
            out = os.path.join(d, "run")
            jobs, names = ts.prepare(comp, out)
            self.assertEqual(len(jobs), 8)
            self.assertEqual(names, ["rival-seo:alpha"])
            self.assertTrue(os.path.isdir(os.path.join(out, "answers")))
            with open(jobs[0], encoding="utf-8") as fh:
                first = fh.read()
            self.assertIn(os.path.join(out, "answers", "A-1.jsonl"), first)


def write_answers(out, answers):
    os.makedirs(os.path.join(out, "answers"), exist_ok=True)
    for order, mapping in answers.items():
        with open(os.path.join(out, "answers", f"{order}-1.jsonl"), "w", encoding="utf-8") as fh:
            for pid, skill in mapping.items():
                fh.write(json.dumps({"id": pid, "skill": skill}) + "\n")


NAMES = [ts.OURS, "rival-seo:alpha", "pdf"]


def perfect():
    one = {p["id"]: (ts.OURS if p["expect"] == "fire" else "rival-seo:alpha") for p in PROMPTS}
    return {"A": dict(one), "B": dict(one)}


class Parsing(unittest.TestCase):
    def read(self, answers, names=NAMES):
        with tempfile.TemporaryDirectory() as d:
            write_answers(d, answers)
            return ts.read_answers(d, PROMPTS, names)

    def test_complete_answers_are_read_and_names_are_canonicalised(self):
        ans = perfect()
        ans["A"][1] = "GEO-VISIBILITY:geo-visibility"
        ans["B"][2] = "None"
        got = self.read(ans)
        self.assertEqual(got["A"][1], ts.OURS)
        self.assertEqual(got["B"][2], "none")

    def test_a_missing_answer_is_an_error_that_names_the_ids(self):
        ans = perfect()
        del ans["B"][7]
        with self.assertRaises(ValueError) as cm:
            self.read(ans)
        self.assertIn("order B: no answer for ids [7]", str(cm.exception))

    def test_a_skill_that_is_not_on_the_menu_is_an_error(self):
        ans = perfect()
        ans["A"][3] = "made-up-skill"
        with self.assertRaises(ValueError) as cm:
            self.read(ans)
        self.assertIn("not on the menu", str(cm.exception))

    def test_unreadable_lines_and_duplicates_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            write_answers(d, perfect())
            with open(os.path.join(d, "answers", "A-1.jsonl"), "a", encoding="utf-8") as fh:
                fh.write("not json\n" + json.dumps({"id": 1, "skill": "pdf"}) + "\n")
            with self.assertRaises(ValueError) as cm:
                ts.read_answers(d, PROMPTS, NAMES)
        self.assertIn("unreadable line", str(cm.exception))
        self.assertIn("answered twice", str(cm.exception))


class Scoring(unittest.TestCase):
    def test_a_perfect_router(self):
        m = ts.score(PROMPTS, perfect())
        for split in ("dev", "test", "all"):
            self.assertEqual(m[split]["fire"]["ours_chosen_in_both_orders"], m[split]["fire"]["n"])
            self.assertEqual(m[split]["no-fire"]["ours_chosen_in_either_order"], 0)
            self.assertEqual(m[split]["fire_missed_to"], {})
            self.assertEqual(m[split]["agreement_between_orders"], m[split]["n"])
        self.assertEqual(m["all"]["fire"]["n"], 20)

    def test_misses_false_positives_and_who_stole_the_prompt(self):
        ans = perfect()
        fire_dev = [p["id"] for p in PROMPTS if p["expect"] == "fire" and p["split"] == "dev"]
        nofire_test = [p["id"] for p in PROMPTS if p["expect"] == "no-fire" and p["split"] == "test"]
        ans["A"][fire_dev[0]] = "rival-seo:alpha"            # one order misses
        ans["A"][fire_dev[1]] = ans["B"][fire_dev[1]] = "pdf"  # both orders miss
        ans["B"][nofire_test[0]] = ts.OURS                   # one false positive in order B
        m = ts.score(PROMPTS, ans)
        d, t = m["dev"], m["test"]
        self.assertEqual(d["fire"]["ours_chosen"], {"A": 8, "B": 9})
        self.assertEqual(d["fire"]["ours_chosen_in_both_orders"], 8)
        self.assertEqual(d["fire_missed_to"], {"pdf": 2, "rival-seo:alpha": 1})
        self.assertEqual(t["no-fire"]["ours_chosen"], {"A": 0, "B": 1})
        self.assertEqual(t["no-fire"]["ours_chosen_in_either_order"], 1)
        self.assertEqual(d["agreement_between_orders"], 10 + 10 - 1)  # only the order-A-only miss disagrees

    def test_markdown_lists_every_miss_with_both_orders(self):
        ans = perfect()
        pid = next(p["id"] for p in PROMPTS if p["expect"] == "fire")
        ans["A"][pid] = "rival-seo:alpha"
        md = ts.to_markdown(ts.score(PROMPTS, ans), PROMPTS, ans)
        self.assertIn("| Split | Prompts |", md)
        self.assertIn("rival-seo:alpha", md)
        self.assertIn(PROMPTS[pid - 1]["prompt"], md)
        self.assertIn("No misses", ts.to_markdown(ts.score(PROMPTS, perfect()), PROMPTS, perfect()))

    def test_pct_helper(self):
        self.assertEqual(ts.pct(1, 4), "25%")
        self.assertEqual(ts.pct(0, 0), "n/a")


RUNS = os.path.join(SKILL, "evals", "trigger-runs")


def rescore(round_name):
    """The saved raw answers, laid out the way the scorer expects (<out>/answers/*.jsonl)."""
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "answers"))
        src = os.path.join(RUNS, round_name)
        for n in os.listdir(src):
            with open(os.path.join(src, n), "rb") as fi, open(os.path.join(d, "answers", n), "wb") as fo:
                fo.write(fi.read())
        answers = ts.read_answers(d, PROMPTS)
    return ts.score(PROMPTS, answers)


class SavedRuns(unittest.TestCase):
    """The committed raw answers must still produce the numbers the results file states."""

    @classmethod
    def setUpClass(cls):
        cls.r1, cls.r2 = rescore("round1"), rescore("round2")
        with open(os.path.join(SKILL, "evals", "results-triggers-2026-10-09.md"), encoding="utf-8") as fh:
            cls.doc = fh.read()

    def test_round_one_is_what_the_document_says(self):
        self.assertEqual(self.r1["all"]["fire"]["ours_chosen_in_both_orders"], 19)
        self.assertEqual(self.r1["dev"]["fire"]["ours_chosen_in_both_orders"], 9)
        self.assertEqual(self.r1["test"]["fire"]["ours_chosen_in_both_orders"], 10)
        self.assertEqual(self.r1["all"]["no-fire"]["ours_chosen_in_either_order"], 0)
        self.assertIn("19 of 20", self.doc)

    def test_round_two_is_what_the_document_says(self):
        self.assertEqual(self.r2["all"]["fire"]["ours_chosen_in_both_orders"], 20)
        self.assertEqual(self.r2["all"]["no-fire"]["ours_chosen_in_either_order"], 0)
        self.assertEqual(self.r2["all"]["agreement_between_orders"], 40)
        self.assertIn("20 of 20", self.doc)

    def test_the_document_does_not_claim_a_held_out_improvement(self):
        """The test half was already perfect in round 1; the write-up must say so rather than imply a gain."""
        self.assertEqual(self.r1["test"]["fire"]["ours_chosen_in_both_orders"], self.r2["test"]["fire"]["ours_chosen_in_both_orders"])
        self.assertIn("no held-out improvement to claim", self.doc)

    def test_the_documented_miss_is_the_one_in_the_saved_answers(self):
        miss = [p for p in PROMPTS if p["expect"] == "fire" and p["split"] == "dev"
                and p["prompt"].startswith("Is Googlebot seeing the same page")]
        self.assertEqual(len(miss), 1)
        self.assertIn(miss[0]["prompt"], self.doc)

    def test_the_described_phrase_is_really_in_the_skill_description(self):
        _, desc = ts.our_entry()
        self.assertIn("each receive from a prerendered or JavaScript site", desc)
        self.assertIn("each receive from a prerendered or JavaScript site", self.doc)
        self.assertLessEqual(len(desc), 1024)

    def test_both_rounds_contain_all_eight_answer_files(self):
        for r in ("round1", "round2"):
            self.assertEqual(sorted(os.listdir(os.path.join(RUNS, r))), [f"{o}-{n}.jsonl" for o in "AB" for n in range(1, 5)])


class DescriptionCoverage(unittest.TestCase):
    """A cheap lexical floor under the simulated test: the description names the things people actually say."""

    def test_the_description_names_the_core_phrases(self):
        _, desc = ts.our_entry()
        for needle in ("GEO", "AEO", "AI search", "llms.txt", "AI crawlers", "share of voice", "Copilot", "Perplexity", "Gemini",
                       "ChatGPT", "Bing Webmaster Tools", "IndexNow"):
            self.assertIn(needle, desc)

    def test_the_description_stays_within_the_limit_and_defers_pure_seo(self):
        _, desc = ts.our_entry()
        self.assertLessEqual(len(desc), 1024)
        self.assertRegex(desc, r"pure classic-SEO audit with no AI angle")


if __name__ == "__main__":
    unittest.main()
