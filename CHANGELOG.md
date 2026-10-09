# Changelog

## Unreleased

### Added
- **Claude Code plugin packaging.** `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` make the skill installable by name: `claude plugin marketplace add thevibegarage/geo-visibility-skill`, then `claude plugin install geo-visibility@geo-visibility`. The manifest points at the existing `geo-visibility/` folder, so nothing moved. Both files pass `claude plugin validate --strict`.
- Tests for the packaging (`tests/test_plugin.py`): documented manifest rules, reserved-name checks, the plugin version staying in step with the latest released changelog entry, README install commands matching the manifest, and the official validator when the `claude` CLI is present (skipped in CI).
- A release checklist in CONTRIBUTING.md.

## v0.2.0 — 2026-10-08

A showpiece README with a reproducible demo, plus two output fixes found by running the checker on live sites.

### Added
- `examples/demo_site.py`: a small fictional site ("Meridian CRM", standard library only) with flaws planted on purpose: a crawler disallowed in robots.txt, a crawler refused by a bot rule, an empty app shell, dynamic rendering by user agent, a page full for Googlebot but empty for Bingbot, `nosnippet`, no JSON-LD and identical sitemap dates.
- `examples/demo-site-output.md`: real, unedited checker output on that site, a words-per-agent table, and a map of planted flaws to Must fix rows. `tools/make_demo_report.py` regenerates it, and a test fails if the committed file drifts from what the tool prints.
- README: hero section, a "See it work" excerpt of that output (verbatim, checked by a test), a quick start, a flowchart of the six phases, a what's-in-the-box table, and a Tests badge.
- Tests for the demo, the README and the examples (links resolve, the excerpt is verbatim, counts match, no real company named in the examples, the claimed test count is current).

### Changed
- `check_ai_readiness.py --issues-only` now ends with a short **Other notes** list instead of repeating warnings and failures already shown in **Must fix** and info rows already shown in **Worth checking**. The default output is unchanged.
- Merged Must fix rows read "agent: detail" instead of nesting the detail in parentheses.
- `examples/sample-report.md` (still illustrative, with invented numbers) now uses the checker's Must fix layout and includes Copilot.
- README roadmap: the v0.2 items that shipped are removed; next up is v0.3.

### Fixed
- **Must fix** listed the same thin homepage twice ("visible text in raw HTML" and "render by agent: /"). It is now listed once, under the more severe of the two rows.

## v0.1.2 — 2026-10-07

Review fixes, a real Bing/Copilot playbook, and an automated test suite. Every fix below has a regression test that fails on v0.1.1.

### Fixed
- `assets/robots-ai-template.txt`: named bot groups held only `Allow: /`, so the `*` group's `Disallow: /admin/ /cart/ /checkout/ /account/` never applied to them (a crawler obeys only its most specific group). Private-path rules are now repeated in every group, before `Allow: /` so first-match parsers agree.
- `check_ai_readiness.py`: a 403/429/503/404 homepage now stops the run with a clear "homepage returned HTTP N" result (exit code 3) instead of producing a score and a page of fake findings.
- `check_ai_readiness.py`: `<meta name="robots" content>` (valueless attribute) no longer crashes the script.
- `check_ai_readiness.py`: robots rules are evaluated with an RFC 9309 matcher (wildcards, `$`, longest match, Allow wins ties, a named group does not inherit `*`) instead of Python's `robotparser`, which reported `Allow: /blog/public` after `Disallow: /blog` as blocked.
- `check_ai_readiness.py`: a 403 for a spoofed Googlebot or Bingbot user agent is a warning, not a failure (verified-bot WAFs reject spoofed copies); it no longer fails the GitHub Action. AI agents still fail.
- `check_ai_readiness.py`: word counts work for Chinese, Japanese, Korean and Thai (a full Japanese page was reported as a 2-word "empty shell"); a short page with an H1 is a warning, not a shell failure; agents that were refused (HTTP 4xx/5xx) are reported as blocked, not as "a shell".
- `check_ai_readiness.py`: `sitemap.xml.gz` is decoded; the checker falls back to `/sitemap.xml` when robots.txt lists a dead sitemap; sitemap indexes are followed (first 5 children); the 2 MB read cap no longer undercounts large sitemaps.
- `check_ai_readiness.py`: a robots.txt 5xx is a failure (Google treats it as disallow-all), an HTML body served as robots.txt is flagged, and per-agent rows say "not assessed" when robots.txt is unavailable.
- `check_ai_readiness.py`: Organization subtypes (`EducationalOrganization`, `Corporation`, `NGO`, ...) count as an Organization declaration (found by running the checker on a live site).
- `check_ai_readiness.py`: the readiness score counts each check once; per-agent robots, WAF and soft-404 rows collapse to the worst row in their group, so a wall of trivial passes no longer hides a failure.
- `check_ai_readiness.py`: pipes in titles and descriptions are escaped so they no longer break the markdown table; `CERTIFICATE_VERIFY_FAILED` gets an actionable hint (python.org builds on macOS).
- `score_tracker.py`: TRUE/FALSE (Sheets and Excel exports), any case, are accepted; any other flag value is a hard error with line numbers instead of silently counting as 0.
- `score_tracker.py`: search and no-search runs are reported separately instead of blended; engine names are trimmed and case-insensitive; Excel's UTF-8 BOM is handled; share of voice is `-` rather than 0 when nothing was mentioned.
- `engine-playbooks.md`: the Claude section no longer calls in-session WebSearch "a direct reading, not a proxy" (it contradicted `SKILL.md`).

### Added
- `references/bing-copilot.md`: Bing Webmaster Tools setup, IndexNow, Bingbot at robots/WAF/prerender, `nocache`/`noarchive`/`nosnippet`, the AI Performance report, testing in Copilot, failure modes, checklist. Wired into `SKILL.md`, the engine playbooks, technical readiness, measurement and the evals.
- `check_ai_readiness.py`: Googlebot and Bingbot in the render-by-agent and soft-404 probes (plus a Googlebot-vs-Bingbot parity warning); snippet/archive control warnings (`nosnippet`, `max-snippet:0`, `noarchive`, `nocache`) and bot-specific `noindex` (`googlebot`, `bingbot` metas, `X-Robots-Tag`); Bing and Google verification hints; `--indexnow-key`; `--paths` checked against the sitemap; robots rows for Applebot, Amazonbot, meta-externalagent, meta-externalfetcher, MistralAI-User, DuckAssistBot, Applebot-Extended and Bytespider (reported as `info`); `--fail-on fail`.
- `score_tracker.py`: `--by-stage`, sentiment mix, `--domain` (derive `cited` from `cited_domains`), a warning when `--compare` runs against a different prompt set, `Copilot` and `AI Overviews` engine aliases.
- `check_ai_readiness.py`: a **Must fix** table at the top of the output (failures first, then warnings, in the order access, render, indexing, discovery, schema, on-page; per-agent robots, WAF and soft-404 rows merged into one entry naming the agents), a **Worth checking** list of unscored open points, `--issues-only`, a `warn_count` score, and `must_fix` / `worth_checking` in the JSON. Every failing or warning row now carries a concrete fix (title, meta description, H1, Organization schema and a few others used to print an empty one). The weekly GitHub Action summary uses `--issues-only`.
- `check_ai_readiness.py`: `Amzn-SearchBot`, `Amzn-User` and `meta-webindexer` robots rows; a malformed `--indexnow-key` is flagged without a request.
- Technical-readiness guidance on robots.txt group semantics, snippet/archive/indexing controls, Brave's index (Claude web search is reported to use it), and other assistants and regional engines.
- `tests/` (stdlib `unittest`, 147 tests, no network), `.github/workflows/tests.yml`, `tools/build_skill.py`.
- Evals: assertions on every eval, and evals 6-11 (Copilot visibility, snippet controls, robots groups, Claude and Brave, tracker roll-up, India and Japan), with graded results in `geo-visibility/evals/results-2026-10-07.md`.
- Quick answers in `SKILL.md` for snippet controls and for a bot ignoring a robots.txt Disallow; the Copilot quick answer now names the full Bing checklist.

### Changed
- Checked against vendor pages on 2026-10-07 and corrected: Googlebot and Bingbot probes now send the evergreen Chrome-style strings; the Amazonbot string follows Amazon's documented form; Amazon's Alexa-related agents are `Amzn-SearchBot` and `Amzn-User` (Amazonbot may train Amazon AI models), not Amazonbot; Meta's search-quality crawler is `meta-webindexer`, and `meta-externalfetcher` may bypass robots.txt; Mistral's agent serves Vibe; Google-Extended has no user agent of its own. `bing-copilot.md` now reflects Microsoft's own posts: grounding queries are a sample, and Citation Share (June 2026) is observational and names no competitors.
- The Brave dependency is now stated as a hypothesis: Anthropic's own pages did not confirm it when checked.
- The readiness workflow propagates the script's exit code (`--fail-on fail` plus `pipefail`), fails on unreachable and homepage-error results, supports `GEO_INDEXNOW_KEY`, and documents the fork and 60-day-inactivity limits.
- The tracker template and example CSV include Copilot and a no-search row.

### Known limits
- Some Bing/Copilot details are still trade-press only (verification methods, the evergreen Bingbot string, the IndexNow-preference and schema statements) and `Bytespider` has no vendor documentation; see the README table.
- Evals 6-11 were run once or twice by sub-agents (28 of 34 assertions fully met; see `geo-visibility/evals/results-2026-10-07.md`); evals 1-5 were not re-run, and skill triggering from natural phrasing is untested. The checker has been run on two live sites but not on WordPress, Next.js or Shopify stacks.
- v0.1.1 was committed but never published as a GitHub release, so v0.1.2 is the first release since v0.1.0 and replaces its `.skill` asset (built with `python3 tools/build_skill.py`).

## v0.1.1 — 2026-10-06

Lessons from a real audit where a default-agent fetch wrongly suggested every page was an empty shell.

- `SKILL.md`: new rules to test as each kind of agent (browser, listed crawler, unlisted user-fetch) and to confirm a retrieval Fail with a second source (routing code, logs, Search Console) before reporting it; disclose which engines were actually run; read outreach/strategy docs in the repo; branch-and-handoff guidance when fixing a repo.
- `check_ai_readiness.py`: render-by-agent comparison on every `--paths` URL (word count, title, H1, JSON-LD, with a verdict for shell-for-everyone vs routing gap vs working dynamic rendering); soft-404 probe per agent; sitemap `lastmod` clustering warning; realistic bot user-agent strings.
- `technical-readiness.md`: new sections on unknown URLs and soft 404s, and freshness of facts (single source of truth, past dates, tax-inclusive pricing, UTC vs local dates); extended checklist.
- Templates: `priceSpecification` for tax-exclusive offers and future-only course/event dates in `schema-templates.md`; generate `llms.txt` from the source of truth.
- Eval 5: "my curl shows an empty shell" must not be taken at face value.
- Workflow: optional `GEO_PATHS` variable / `paths` input.
- Known limit: the new checks were tested against a local mock server, not yet against WordPress, Next.js or Shopify sites.

## v0.1.0 — 2026-10-05

First public release. Beta: see the tested/untested table in the README.

- Six-phase GEO workflow (baseline audit → technical → content → off-site → engine tuning → measurement)
- 9 reference playbooks, including evidence confidence tiers and 8 vertical profiles
- `check_ai_readiness.py`: robots/WAF/rendering/schema/llms.txt checker (stdlib only; fails loudly when the network is unreachable instead of reporting fake findings)
- `score_tracker.py`: tracker CSV → KPIs, cited-domain ranking, month-over-month deltas; validates input and rejects malformed CSVs
- Templates: robots.txt (crawler names verified against OpenAI/Anthropic/Perplexity/Google docs 2026-10-05), llms.txt, JSON-LD, tracker CSV, report
- Eval set with 4 test prompts, including a manipulation-refusal case
- Known limits: trigger reliability untested; engine behavior claims are hedged practitioner reports; one head-to-head run vs. no-skill baseline
