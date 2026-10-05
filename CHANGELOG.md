# Changelog

## v0.1.0 — 2026-10-05

First public release. Beta: see the tested/untested table in the README.

- Six-phase GEO workflow (baseline audit → technical → content → off-site → engine tuning → measurement)
- 9 reference playbooks, including evidence confidence tiers and 8 vertical profiles
- `check_ai_readiness.py`: robots/WAF/rendering/schema/llms.txt checker (stdlib only; fails loudly when the network is unreachable instead of reporting fake findings)
- `score_tracker.py`: tracker CSV → KPIs, cited-domain ranking, month-over-month deltas; validates input and rejects malformed CSVs
- Templates: robots.txt (crawler names verified against OpenAI/Anthropic/Perplexity/Google docs 2026-10-05), llms.txt, JSON-LD, tracker CSV, report
- Eval set with 4 test prompts, including a manipulation-refusal case
- Known limits: trigger reliability untested; engine behavior claims are hedged practitioner reports; one head-to-head run vs. no-skill baseline
