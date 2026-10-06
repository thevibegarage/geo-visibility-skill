# Changelog

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
