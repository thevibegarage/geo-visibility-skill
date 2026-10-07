# AI visibility tracker

Brand: {{BRAND}}   Competitors: {{C1, C2, C3}}   Prompt set version: v1   Run date: {{YYYY-MM-DD}}

## Run log (one row per prompt x engine x run)
| ID | Stage | Prompt | Engine | Mode (search on/off) | Run # | Mentioned (0/1) | Cited (0/1) | Position | Sentiment | Accuracy errors | Competitors named | Cited domains |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P01 | Category | | ChatGPT | on | 1 | | | | | | | |
| P01 | Category | | Claude | on | 1 | | | | | | | |
| P01 | Category | | Gemini | on | 1 | | | | | | | |
| P01 | Category | | Copilot | on | 1 | | | | | | | |
| P01 | Category | | Perplexity | on | 1 | | | | | | | |
| P01 | Category | | AI Overviews | on | 1 | | | | | | | |

Tip: copy this table into a spreadsheet for formulas, or paste results back into chat and ask for the roll-up.
Export to CSV (`assets/visibility-tracker.csv` has the header) and run `scripts/score_tracker.py tracker.csv --brand "<Brand>" --domain <brand-domain> --by-stage`.
Use 1/0 or TRUE/FALSE (spreadsheet checkboxes export as TRUE/FALSE). Mode is `search` or `no-search`; the two are reported separately.
Engine names: ChatGPT, Claude, Gemini, Copilot, Perplexity, AI Overviews (Bing Chat and Microsoft Copilot are folded into Copilot). Add any other assistant that matters in the market.

## Roll-up (per engine, per stage)
| Engine | Mention rate | Citation rate | Avg position | Share of voice | Accuracy rate |
|---|---|---|---|---|---|
| ChatGPT | | | | | |
| Claude | | | | | |
| Gemini | | | | | |
| Copilot | | | | | |
| Perplexity | | | | | |
| AI Overviews | | | | | |

## Top cited domains
| Rank | Domain | Type | Times cited | Brand present? | Competitor present? | Action |
|---|---|---|---|---|---|---|

## Inaccuracy log
| Engine | Prompt | What it said | Truth | Likely source | Fix |
|---|---|---|---|---|---|

## Month-over-month
| KPI | Baseline | Month 1 | Month 2 | Month 3 |
|---|---|---|---|---|
| AI share of voice | | | | |
| Mention rate | | | | |
| Citation rate | | | | |
| AI referral sessions | | | | |
| Branded search clicks | | | | |
