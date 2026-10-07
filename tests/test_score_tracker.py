import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest

from helpers import st, SKILL

HEADER = "prompt_id,stage,prompt,engine,mode,run,mentioned,cited,position,sentiment,accurate,competitors,cited_domains\n"


def write(text, bom=False):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8-sig" if bom else "utf-8", newline="")
    f.write(text)
    f.close()
    return f.name


def row(pid="P01", stage="category", engine="ChatGPT", mode="search", run=1, mentioned="0", cited="0", position="",
        sentiment="", accurate="", competitors="", domains=""):
    return f"{pid},{stage},q,{engine},{mode},{run},{mentioned},{cited},{position},{sentiment},{accurate},{competitors},{domains}\n"


def pipeline(text, domain=None, bom=False):
    path = write(HEADER + text, bom)
    try:
        raw = st.load(path)
        st.check_input(raw, path)
        return st.collapse(st.normalize(raw), domain)
    finally:
        os.unlink(path)


def cli(text, *args):
    path = write(HEADER + text)
    try:
        p = subprocess.run([sys.executable, os.path.join(SKILL, "scripts", "score_tracker.py"), path, *args],
                           capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr
    finally:
        os.unlink(path)


def metric(rows, engine, mode="search"):
    return st.rollup(rows)[(engine.casefold(), mode)]


class BooleanParsing(unittest.TestCase):
    def test_sheets_and_excel_true_false_are_counted(self):
        """Regression: TRUE/FALSE exports silently counted as 0 (0% mention rate) with only a stderr warning."""
        rows = pipeline(row("P01", mentioned="TRUE", cited="TRUE", accurate="TRUE") +
                        row("P02", mentioned="TRUE", cited="FALSE", accurate="FALSE") +
                        row("P03", mentioned="FALSE", cited="FALSE"))
        m = metric(rows, "ChatGPT")
        self.assertEqual(m["mention_rate"], 67)
        self.assertEqual(m["citation_rate"], 33)
        self.assertEqual(m["accuracy_rate"], 50)

    def test_true_false_through_the_cli(self):
        code, out, err = cli(row("P01", mentioned="TRUE", cited="TRUE") + row("P02", mentioned="TRUE", cited="FALSE"))
        self.assertEqual(code, 0, err)
        self.assertIn("| ChatGPT | 2 | 100 | 50 |", out)
        self.assertEqual(err, "")

    def test_mixed_case_and_aliases(self):
        for yes in ("1", "true", "True", "YES", "y", "Y", "t", "x", "✓"):
            self.assertEqual(st.flag(yes), 1, yes)
        for no in ("0", "false", "No", "N", "f"):
            self.assertEqual(st.flag(no), 0, no)
        self.assertIsNone(st.flag(""))
        self.assertIsNone(st.flag("maybe"))

    def test_unscoreable_values_are_a_hard_error_with_line_numbers(self):
        path = write(HEADER + row("P01", mentioned="1") + row("P02", mentioned="maybe", cited="2"))
        with self.assertRaises(SystemExit) as cm:
            st.check_input(st.load(path), path)
        msg = str(cm.exception)
        self.assertIn("line 3", msg)
        self.assertIn("mentioned='maybe'", msg)
        self.assertIn("cited='2'", msg)
        code, out, err = cli(row("P01", mentioned="maybe"))
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")

    def test_empty_engine_is_an_error(self):
        path = write(HEADER + row("P01", engine=""))
        with self.assertRaises(SystemExit) as cm:
            st.check_input(st.load(path), path)
        self.assertIn("engine is empty", str(cm.exception))

    def test_blank_flags_are_allowed(self):
        self.assertEqual(metric(pipeline(row(mentioned="", cited="")), "ChatGPT")["mention_rate"], 0)

    def test_empty_and_missing_column_files_still_fail_loudly(self):
        path = write(HEADER)
        with self.assertRaises(SystemExit):
            st.check_input(st.load(path), path)
        path = write("prompt_id,engine\nP01,ChatGPT\n")
        with self.assertRaises(SystemExit) as cm:
            st.check_input(st.load(path), path)
        self.assertIn("mentioned", str(cm.exception))


class Encoding(unittest.TestCase):
    def test_excel_utf8_bom_header_is_read(self):
        """Regression: the BOM made the first header '\\ufeffprompt_id' -> 'missing required column(s): prompt_id'."""
        rows = pipeline(row("P01", mentioned="1"), bom=True)
        self.assertEqual(rows[0]["prompt_id"], "P01")


    def test_bom_file_through_the_cli(self):
        path = write(HEADER + row("P01", mentioned="1"), bom=True)
        try:
            p = subprocess.run([sys.executable, os.path.join(SKILL, "scripts", "score_tracker.py"), path], capture_output=True, text=True)
        finally:
            os.unlink(path)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("| ChatGPT | 1 | 100 |", p.stdout)


class Normalization(unittest.TestCase):
    def test_engine_names_are_trimmed_and_case_insensitive(self):
        """Regression: 'chatgpt ' was reported as a different engine from 'ChatGPT' and broke month-over-month deltas."""
        rows = pipeline(row("P01", engine="ChatGPT", mentioned="1") + row("P02", engine="chatgpt ", mentioned="0"))
        res = st.rollup(rows)
        engines = {m["label"] for k, m in res.items() if k[0] != "all"}
        self.assertEqual(engines, {"ChatGPT"})
        self.assertEqual(metric(rows, "chatgpt")["prompts"], 2)

    def test_copilot_and_ai_overviews_aliases(self):
        rows = pipeline(row("P01", engine="Bing Chat") + row("P02", engine="Microsoft Copilot") + row("P03", engine="Copilot") +
                        row("P04", engine="Google AI Overview") + row("P05", engine="AI Overviews"))
        labels = {m["label"] for k, m in st.rollup(rows).items() if k[0] != "all"}
        self.assertEqual(labels, {"Copilot", "AI Overviews"})
        self.assertEqual(metric(rows, "Copilot")["prompts"], 3)

    def test_mode_aliases(self):
        self.assertEqual({st.norm_mode(m) for m in ("", "search", "ON", "Search On", "web", "search_on")}, {"search"})
        self.assertEqual({st.norm_mode(m) for m in ("off", "No-Search", "no search", "memory", "search_off")}, {"no-search"})
        self.assertEqual(st.norm_mode("agent"), "agent")


class ModeSeparation(unittest.TestCase):
    TEXT = (row("P01", mode="search", mentioned="0", competitors="A") + row("P02", mode="search", mentioned="0", competitors="A") +
            row("P01", mode="no-search", mentioned="1", position="1", competitors="A") +
            row("P02", mode="no-search", mentioned="1", position="1", competitors="A"))

    def test_search_and_no_search_runs_are_not_blended(self):
        """Regression: two prompts run in both modes were reported as 4 prompts with a blended 50% mention rate."""
        rows = pipeline(self.TEXT)
        s, n = metric(rows, "ChatGPT", "search"), metric(rows, "ChatGPT", "no-search")
        self.assertEqual((s["prompts"], s["mention_rate"]), (2, 0))
        self.assertEqual((n["prompts"], n["mention_rate"]), (2, 100))
        self.assertEqual(metric(rows, "ALL", "search")["mention_rate"], 0)
        self.assertEqual(metric(rows, "ALL", "no-search")["mention_rate"], 100)

    def test_output_labels_the_no_search_rows(self):
        code, out, _ = cli(self.TEXT)
        self.assertEqual(code, 0)
        self.assertIn("| ChatGPT [no-search] | 2 | 100 |", out)
        self.assertIn("| ChatGPT | 2 | 0 |", out)

    def test_blank_mode_counts_as_search(self):
        self.assertEqual(metric(pipeline(row(mode="", mentioned="1")), "ChatGPT", "search")["mention_rate"], 100)


class StageAndSentiment(unittest.TestCase):
    TEXT = (row("P01", stage="category", mentioned="1", sentiment="positive", competitors="A") +
            row("P02", stage="category", mentioned="0", sentiment="negative", competitors="A") +
            row("P03", stage="brand", mentioned="1", sentiment="positive") +
            row("P04", stage="brand", mentioned="1", sentiment="inaccurate", accurate="0"))

    def test_by_stage_rollup(self):
        """Regression: per-stage roll-up was documented but never computed."""
        res = st.rollup_by_stage(pipeline(self.TEXT))
        self.assertEqual(res[("category", "all", "search")]["mention_rate"], 50)
        self.assertEqual(res[("brand", "all", "search")]["mention_rate"], 100)
        self.assertEqual(res[("brand", "chatgpt", "search")]["prompts"], 2)

    def test_by_stage_flag_prints_a_table(self):
        _, out, _ = cli(self.TEXT, "--by-stage")
        self.assertIn("## By funnel stage", out)
        self.assertIn("| category | ALL | 2 | 50 |", out)
        self.assertIn("| brand | ChatGPT | 2 | 100 |", out)
        _, out, _ = cli(self.TEXT)
        self.assertNotIn("By funnel stage", out)

    def test_sentiment_mix(self):
        """Regression: sentiment was recorded but never summarised."""
        m = metric(pipeline(self.TEXT), "ChatGPT")
        self.assertEqual(m["sentiment"], {"positive": 50, "negative": 25, "inaccurate": 25})
        _, out, _ = cli(self.TEXT)
        self.assertIn("## Sentiment mix", out)
        self.assertIn("| ChatGPT | 50 | 0 | 25 | 25 |", out)

    def test_no_sentiment_no_table(self):
        _, out, _ = cli(row(mentioned="1"))
        self.assertNotIn("Sentiment mix", out)

    def test_sentiment_normalization_and_tie_break(self):
        self.assertEqual([st.norm_sentiment(x) for x in ("Positive", "pos", "NEUTRAL", "Negative", "inaccurate", "weird", "")],
                         ["positive", "positive", "neutral", "negative", "inaccurate", "other", None])
        rows = pipeline(row(run=1, sentiment="positive") + row(run=2, sentiment="negative"))
        self.assertEqual(rows[0]["sentiment"], "negative")  # ties go to the more negative reading


class DerivedCitation(unittest.TestCase):
    def test_blank_cited_is_derived_from_cited_domains(self):
        rows = pipeline(row("P01", cited="", domains="g2.com;www.acme.com") + row("P02", cited="", domains="notacme.com;g2.com") +
                        row("P03", cited="", domains="blog.acme.com") + row("P04", cited="", domains=""), domain="acme.com")
        self.assertEqual({r["prompt_id"]: r["cited"] for r in rows}, {"P01": 1, "P02": 0, "P03": 1, "P04": 0})

    def test_explicit_cited_wins_over_derivation(self):
        rows = pipeline(row("P01", cited="0", domains="acme.com"), domain="acme.com")
        self.assertEqual(rows[0]["cited"], 0)

    def test_no_domain_flag_means_no_derivation(self):
        self.assertEqual(pipeline(row("P01", cited="", domains="acme.com"))[0]["cited"], 0)

    def test_domain_flag_on_the_cli(self):
        _, out, _ = cli(row("P01", cited="", domains="acme.com", mentioned="1"), "--domain", "acme.com")
        self.assertIn("| ChatGPT | 1 | 100 | 100 |", out)


class Rollup(unittest.TestCase):
    def test_majority_vote_and_ties_count_as_zero(self):
        rows = pipeline(row(run=1, mentioned="1") + row(run=2, mentioned="1") + row(run=3, mentioned="0") +
                        row("P02", run=1, mentioned="1") + row("P02", run=2, mentioned="0"))
        by = {r["prompt_id"]: r["mentioned"] for r in rows}
        self.assertEqual(by, {"P01": 1, "P02": 0})

    def test_competitors_need_a_strict_majority_and_domains_half(self):
        rows = pipeline(row(run=1, competitors="A;B", domains="x.com;y.com") + row(run=2, competitors="A", domains="x.com"))
        r = rows[0]
        self.assertEqual(r["competitors"], ["A"])
        self.assertEqual(sorted(r["domains"]), ["x.com", "y.com"])  # y.com cited in 1 of 2 runs: half is enough

    def test_share_of_voice(self):
        m = metric(pipeline(row("P01", mentioned="1", competitors="A") + row("P02", mentioned="0", competitors="A;B")), "ChatGPT")
        self.assertEqual(m["share_of_voice"], round(100 * 1 / (1 + 3)))

    def test_share_of_voice_is_undefined_not_zero_without_any_mentions(self):
        """Regression: no brand and no competitor mentions printed 0% share of voice."""
        m = metric(pipeline(row("P01", mentioned="0")), "ChatGPT")
        self.assertIsNone(m["share_of_voice"])
        _, out, _ = cli(row("P01", mentioned="0"))
        self.assertIn("| ChatGPT | 1 | 0 | 0 | - | - | - |", out)

    def test_position_median_and_accuracy_blank(self):
        m = metric(pipeline(row(run=1, mentioned="1", position="1") + row(run=2, mentioned="1", position="3") + row(run=3, mentioned="1", position="2")), "ChatGPT")
        self.assertEqual(m["avg_position"], 2)
        self.assertIsNone(m["accuracy_rate"])

    def test_lost_prompts_and_top_domains(self):
        rows = pipeline(row("P01", mentioned="0", competitors="A", domains="g2.com") + row("P02", mentioned="1", domains="g2.com;x.com"))
        self.assertEqual(st.top_domains(rows)[0], ("g2.com", 2))
        self.assertEqual(st.lost_prompts(rows), [("P01", "ChatGPT", "A")])


class Compare(unittest.TestCase):
    A = row("P01", mentioned="0") + row("P02", mentioned="1")
    B = row("P01", mentioned="1") + row("P02", mentioned="1")

    def run_compare(self, current, previous):
        prev = write(HEADER + previous)
        try:
            return cli(current, "--compare", prev)
        finally:
            os.unlink(prev)

    def test_deltas(self):
        code, out, _ = self.run_compare(self.B, self.A)
        self.assertEqual(code, 0)
        self.assertIn("| ChatGPT | 2 | 100 (+50) |", out)
        self.assertNotIn("WARNING", out)

    def test_deltas_pair_across_engine_name_spelling(self):
        code, out, _ = self.run_compare(self.B, row("P01", engine="chatgpt", mentioned="0") + row("P02", engine="CHATGPT ", mentioned="1"))
        self.assertIn("100 (+50)", out)

    def test_different_prompt_sets_warn(self):
        """Regression: month-over-month deltas on different prompt sets were silently presented as like-for-like."""
        code, out, _ = self.run_compare(self.B + row("P03", mentioned="1"), self.A)
        self.assertIn("WARNING: the prompt sets differ (1 new, 0 missing)", out)


class ShippedExample(unittest.TestCase):
    def test_example_csv_runs_and_includes_copilot(self):
        path = os.path.join(SKILL, "assets", "visibility-tracker.csv")
        p = subprocess.run([sys.executable, os.path.join(SKILL, "scripts", "score_tracker.py"), path, "--by-stage"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Copilot", p.stdout)
        self.assertEqual(p.stderr, "")


if __name__ == "__main__":
    unittest.main()
