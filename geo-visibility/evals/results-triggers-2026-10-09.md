# Activation test, 2026-10-09: would a model pick this skill?

**What this measures.** Claude Code chooses which skill to load by reading every installed skill's name and description. This test rebuilds that choice as an experiment: a fresh model is shown a menu of 15 skills (ours, the 11 skills of a third-party classic-SEO plugin shown as `rival-seo`, and `code-review`, `pdf`, `docx`) and ten user messages at a time, and says which single skill, if any, it would load. 40 messages: 20 about AI-search visibility (our skill should be chosen) and 20 about classic SEO, content or unrelated work (it should not). Each batch runs with two menu orders (ours first, ours last) and a different shuffle, so position cannot explain a result.

**A note on names.** The models saw the rival plugin's real skill names and descriptions. In the saved answers its skill names are relabelled `rival-seo:*` (a label-only substitution) so this repository does not name another vendor; the descriptions, the prompts and every score are unchanged. The tool takes any plugin clone via `--competitors` and defaults to that label.

**What it does not measure.** It is a **simulation**: a stand-in model doing the routing, not Claude Code's own router. The prompt set is small (40) and written by the maintainers, so it is a regression signal, not a benchmark. Real users have more skills installed than 15.

**How it was kept honest.** The prompts were split into `dev` and `test` halves before any run. The skill description may be tuned using `dev` failures only; `test` is the held-out estimate. Prompts and split: [`triggers.json`](triggers.json). Raw answers from every run: [`trigger-runs/`](trigger-runs/). Re-score them with `python3 tools/trigger_sim.py score --out <folder containing answers/>` (a test does this and checks the numbers below). Method and tool: [`tools/trigger_sim.py`](../../tools/trigger_sim.py).

## Round 1: description as released in v0.2.0

| Split | Prompts | Chosen when it should be (A / B / both orders) | Chosen when it should not be (A / B / either order) | Orders agree |
|---|---|---|---|---|
| dev | 20 | 9/10 / 9/10 / 9/10 (90%) | 0/10 / 0/10 / 0/10 | 20/20 |
| test | 20 | 10/10 / 10/10 / 10/10 (100%) | 0/10 / 0/10 / 0/10 | 20/20 |
| all | 40 | 19/20 / 19/20 / 19/20 (95%) | 0/20 / 0/20 / 0/20 | 40/40 |

One miss, in `dev`: *"Is Googlebot seeing the same page as Bingbot on our site? We use a prerender service for our React app."* Both orders chose the rival plugin's `technical-seo` skill. Our description never said that the skill checks what each crawler receives from a prerendered or JavaScript site, which is one of its most distinctive features.

## The change

One phrase added to the description in `geo-visibility/SKILL.md` (897 to 1,000 characters; the limit is 1,024): *"crawler and technical fixes (including what Googlebot, Bingbot and AI crawlers each receive from a prerendered or JavaScript site)"*. Nothing else changed. The `test` half was not used to choose it.

## Round 2: description with that phrase

| Split | Prompts | Chosen when it should be (A / B / both orders) | Chosen when it should not be (A / B / either order) | Orders agree |
|---|---|---|---|---|
| dev | 20 | 10/10 / 10/10 / 10/10 (100%) | 0/10 / 0/10 / 0/10 | 20/20 |
| test | 20 | 10/10 / 10/10 / 10/10 (100%) | 0/10 / 0/10 / 0/10 | 20/20 |
| all | 40 | 20/20 / 20/20 / 20/20 (100%) | 0/20 / 0/20 / 0/20 | 40/40 |

## How to read this

- **Before the change:** our skill was chosen for 19 of 20 AI-search messages and for 0 of 20 messages it should leave alone, with both menu orders agreeing on every message.
- **After the change:** 20 of 20 and 0 of 20. The `dev` miss is fixed. The `test` half was already 100% before the change and stayed there, so there is **no held-out improvement to claim**, only evidence that the edit caused no regression and no new false positives (including on classic-SEO messages such as hreflang, Core Web Vitals, crawl errors and orphan pages).
- **Ceiling effect.** Perfect scores on a small, friendly set say the description is not obviously broken. They do not say it is safe against harder boundary cases, and the next step is more of those (for example "SEO audit" requests that mention AI in passing, and schema or `robots.txt` questions that both skills could claim).
- **Where the boundary sits.** Our `SKILL.md` tells the model to prefer a dedicated skill for a pure classic-SEO audit. The test confirms that stance: *"Do an SEO health check of my site: crawl errors, sitemap, indexation"* went to the rival plugin's `seo-audit` in both orders.
