# SEO foundation (the part GEO stands on)

The user's goal is for SEO and GEO to reinforce each other. Retrieval layers lean on classic indexes and authority signals, so weak SEO caps GEO. Audit these before spending effort on AI-specific tactics.

## Contents
- Where SEO and GEO overlap vs diverge
- SEO baseline checklist
- Keyword to prompt translation
- Topical authority
- Local and ecommerce additions
- Prioritization

## Where SEO and GEO overlap vs diverge
| Area | Classic SEO | GEO | Do both by |
|---|---|---|---|
| Unit of competition | Page ranks for a keyword | Passage gets quoted for a prompt | Page that ranks, with extractable passages inside |
| Query shape | 2-5 keywords | Long conversational prompts with context | Cover head terms and the long-form questions behind them |
| Authority | Backlinks, brand | Corroboration across independent sources, mentions without links count | Digital PR that earns both links and mentions |
| Success | Rank and click | Mention, citation, recommendation, sometimes no click | Track both; expect clicks to shift to branded search |
| Freshness | Mild, topic dependent | Strong on live-search engines for time-sensitive topics | Honest update cycles on money pages |
| Technical | Crawl, index, speed | Same plus agent access, rendering without JS, markdown-friendly docs | One technical program |

## SEO baseline checklist
Run these before anything exotic (use `scripts/check_ai_readiness.py` for the automatable ones):
1. Indexation: Search Console coverage, no accidental noindex, canonical correct, sitemap clean.
2. Crawl efficiency: no redirect chains, orphan pages, or parameter bloat; internal links to money pages.
3. Core Web Vitals and mobile usability.
4. Intent-matched pages for each money keyword (one primary page per intent; merge cannibalizing duplicates).
5. Titles and meta descriptions that state the offer; headings mirror questions.
6. Backlink profile: gap vs competitors, toxic spikes, reclaim lost links, fix broken inbound URLs.
7. E-E-A-T: named expert authors, About and editorial pages, real contact info, first-hand experience and original data.
8. Hreflang and canonical logic for multi-country or multi-language sites.
9. Brand SERP: what appears for "[brand]" (knowledge panel, profiles, reviews, news). It predicts what AI will say.

## Keyword to prompt translation
Take the top 50-100 queries from Search Console and the paid/organic keyword set, then expand each money keyword into 3-5 realistic prompts:
- Add persona ("for a 10-person fintech startup in Bengaluru").
- Add constraints (budget, integrations, compliance).
- Add comparison framing ("X vs Y", "alternatives to").
- Add decision framing ("is it worth it", "what should I pick").
Use these as the Phase 1 audit prompts and as the heading questions for content.

## Topical authority
- Build topic clusters: one comprehensive hub plus supporting pages answering each sub-question, interlinked.
- Prefer depth on fewer topics over thin coverage of many. Engines and rankers reward demonstrated expertise on a subject.
- Maintain a content inventory with last-updated dates, owner, target prompts, and performance; prune or merge decayed pages.

## Local and ecommerce additions
- Local: Google Business Profile complete and active, consistent NAP across directories, review velocity and replies, local landing pages with real local proof, LocalBusiness schema.
- Ecommerce: complete Product schema, accurate price/stock, unique descriptions, buying guides, review content, merchant feed freshness. Agentic shopping is emerging; keep catalog data clean, machine-readable and consistent. Check current platform docs for merchant programs and checkout protocols before advising on them.

## Prioritization
Score each opportunity: impact (1-5) x confidence (1-5) / effort (1-5). Always put "blocked from retrieval" and "wrong or missing facts about the brand" first; they cost little and block everything else.
