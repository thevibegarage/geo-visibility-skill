# AI Search Visibility Report: {{BRAND}}

Prepared {{DATE}} · Domain: {{DOMAIN}} · Category: {{CATEGORY}} · Engines tested: {{LIST}}
Assumptions and limits: {{ASSUMPTIONS; AI answers vary by run, user, location and model version; this is a point-in-time baseline}}

## 1. Executive summary
- **Where you stand:** {{one sentence with share of voice and citation rate}}
- **Biggest 3 gaps:** {{1}} · {{2}} · {{3}}
- **Fastest wins (week 1):** {{3 items}}
- **Expected effort:** {{hours/people}} · **Time to first measurable movement:** {{weeks, with caveat}}

## 2. Baseline
Prompt set: {{N}} prompts, {{stages}}. Runs: {{n}} per prompt for top prompts.
{{roll-up table from scripts/score_tracker.py}}
**Top cited sources in your category** (where engines get their answers):
| Rank | Domain | Type | Cited | You present? | Competitor present? | Action |
|---|---|---|---|---|---|---|
**Inaccuracies found:** {{table: engine, wrong statement, truth, likely source, fix}}

## 3. Technical readiness
Score: {{pct}}% · Failures: {{n}}
{{table from scripts/check_ai_readiness.py, failures first, each with an owner and exact fix}}

## 4. 30-day action plan
| # | Action | Why (evidence from audit) | Owner | Effort | Impact | Due |
|---|---|---|---|---|---|---|
Ordered: retrieval blockers, wrong facts, entity assets, answer-first rewrites, content gaps, off-site targets.

## 5. Ready-to-ship assets
- robots.txt block (verified against current docs on {{DATE}})
- llms.txt
- JSON-LD (Organization, WebSite, plus page-type schema)
- Brand fact sheet (25/50/100-word boilerplate)
- Rewritten page sections: {{pages}}
- Content briefs: {{n}}

## 6. Off-site plan (90 days)
{{ranked source list with tactic, owner, effort}}

## 7. Measurement
KPIs, tracker location, cadence, analytics setup status, experiment design (treated vs control pages), next re-test date {{DATE+30}}.

## 8. Risks and open questions
{{decisions needed from the owner (training-crawler policy, review program, PR budget), unverified items, items needing legal or expert review}}
