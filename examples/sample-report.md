# Sample output: AI Search Visibility Report

> **This is an illustrative example** using a fictional brand ("Meridian CRM") so no real company's data is exposed. Structure and depth match what the skill produces on a real engagement. Numbers are invented.

---

# AI Search Visibility Report: Meridian CRM

Prepared 2026-10-05 · Domain: meridiancrm.example · Category: CRM for mid-size agencies · Engines tested: ChatGPT, Claude, Perplexity, Gemini

**Assumptions and limits:** 32 prompts, 1–3 runs each, search mode on, tested from one location. AI answers vary by run, user, location and model version; this is a point-in-time baseline, not a verdict.

## 1. Executive summary
- **Where you stand:** mentioned in 22% of prompts (competitors: BrightPipe 61%, Foldr 48%); cited (own domain linked) in 6%.
- **Biggest 3 gaps:** (1) absent from 4 of the 5 listicles engines cite most · (2) pricing described wrongly in 3 of 7 brand-prompt answers · (3) key pages render client-side, thin HTML for crawlers.
- **Fastest wins (week 1):** fix rendering on /pricing and /features, correct the stale Capterra profile, publish the brand fact sheet.
- **Effort:** ~4 dev-days + ongoing PR. **Time to movement:** live-search engines, weeks after recrawl. No guarantees.

## 2. Baseline
| Engine | Prompts | Mention % | Citation % | Avg pos | Share of voice % |
|---|---|---|---|---|---|
| ChatGPT | 32 | 19 | 6 | 3.2 | 14 |
| Claude | 32 | 25 | 6 | 2.8 | 17 |
| Perplexity | 32 | 28 | 9 | 2.5 | 19 |
| Gemini | 32 | 16 | 3 | 3.6 | 11 |

**Top cited domains in the category** (the off-site target list):
| Rank | Domain | Type | Cited | You present? | Action |
|---|---|---|---|---|---|
| 1 | g2.com | Reviews | 18× | Yes, 12 reviews (stale) | Review program |
| 2 | agencytoolreview.example | Listicle | 11× | **No** | Pitch factual inclusion |
| 3 | reddit.com/r/agencies | Community | 9× | 1 old thread | Transparent participation |
| 4 | capterra.com | Reviews | 8× | Yes, wrong pricing | Correct profile |
| 5 | martechweekly.example | Press | 6× | No | Original-data pitch |

**Inaccuracy log:**
| Engine | What it said | Truth | Likely source | Fix |
|---|---|---|---|---|
| ChatGPT | "Starts at $49/user" | $29/user since Jan 2026 | Stale Capterra entry | Update profile |
| Gemini | "No API access" | Full REST API on all tiers | Old comparison post | Request correction + publish API page |

## 3. Technical readiness — 68%, 3 failures
| Check | Status | Fix |
|---|---|---|
| robots.txt allows search/user-fetch agents | ✅ pass | — |
| Key text in initial HTML | ❌ fail | SSR /pricing, /features |
| Organization schema | ❌ fail | Add JSON-LD (template in assets/) |
| Bing indexed | ⚠️ partial | Submit sitemap, enable IndexNow |
| Visible dates + authors on content | ❌ fail | Add bylines |

## 4. 30-day action plan (excerpt)
| # | Action | Owner | Effort | Due |
|---|---|---|---|---|
| 1 | SSR the money pages | Dev | 2d | Day 7 |
| 2 | Correct Capterra + G2 profiles to fact-sheet wording | Marketing | 2h | Day 3 |
| 3 | Brand fact sheet + Organization/Product schema | Marketing+Dev | 1d | Day 7 |
| 4 | "Meridian vs BrightPipe" answer-first comparison page | Content | 2d | Day 14 |
| 5 | Pitch agencytoolreview.example with real data | PR | 0.5d | Day 21 |
| 6 | Re-run frozen prompt set, compare | Marketing | 3h | Day 30 |

*(Sections 5–8 — ready-to-ship assets, off-site plan, measurement, risks — omitted here for brevity; the skill produces them in full.)*

---

Want this for your brand? Install the skill (see the [README](../README.md)) and ask Claude: *"Run an AI visibility audit on mydomain.com."*
