# Engine playbooks

Behavior below reflects widely reported patterns as of late 2026 and is a starting hypothesis. Engines change constantly and published studies disagree. Re-check official docs and re-run the audit before committing effort. Cross-engine overlap in cited sources is low, so measure each engine separately.

## Contents
- ChatGPT (and Copilot)
- Claude
- Gemini and Google AI Overviews / AI Mode
- Perplexity
- Cross-engine truths

## ChatGPT (and Microsoft Copilot)
- Two modes: answers from model memory (training data, frozen at a cutoff) and answers with live search. Reports indicate the search layer relies heavily on Bing's index plus OpenAI's own retrieval, so being indexed and healthy in Bing Webmaster Tools matters (submit sitemap, use IndexNow).
- OpenAI documents separate crawlers: one for training, one for search indexing, one for user-initiated fetches. Allow the search and user-fetch agents if you want citations. Verify names in OpenAI's current crawler documentation.
- Recommendations lean on brands with broad corroboration: review sites, "best of" listicles, Wikipedia, Reddit, news. For "best X" prompts, the cited listicles are often the real lever.
- Structured, scannable passages (short answers, bullets, FAQs, tables) get lifted more easily. Freshness helps; show real updated dates and actually update.
- Shopping/product prompts reward complete product data: clear specs, pricing, availability, reviews, Product schema, and a merchant feed where supported.

## Claude
- Claude answers from training knowledge and, when web search is on, retrieves live pages. Anthropic publishes separate agents: one for training, one for search indexing, one for user-initiated fetches. Blocking the training agent does not by itself block citation from search/user fetch. Verify names in Anthropic's current crawler documentation and do not rely on retired agent names that older guides still list.
- Claude tends to cite fewer sources and reward depth, primary sources, clear definitions and well-attributed facts over thin listicles. Original data, methodology notes and direct quotes from named experts help.
- Because model memory matters, long-run presence in high-quality, widely-replicated sources (documentation, reputable publications, Wikipedia/Wikidata, GitHub, standards bodies) shapes what Claude "knows" about a brand even without search.
- For developer or B2B tools: excellent public docs, a clear llms.txt or markdown-accessible docs, and an MCP server or API listing help agentic use, where Claude acts on the brand's behalf rather than just citing it. Treat "agent readiness" (clear pricing, signup path, machine-readable catalog) as part of GEO.
- Claude-in-the-loop test: use WebSearch in this session for the target prompts and record what it surfaces. That is a direct reading, not a proxy.

## Gemini, Google AI Overviews, AI Mode
- Built on Google's index and ranking systems, so classic SEO fundamentals transfer most directly here: crawlable, indexed, helpful, authoritative pages; strong E-E-A-T signals; Core Web Vitals; internal linking.
- Keep Googlebot able to crawl and render. Google-Extended controls use for Gemini training and grounding; Google states it does not affect Search inclusion or ranking (verified October 2026). Do not confuse it with Googlebot.
- Structured data (Organization, Product, FAQ where still eligible, Article, LocalBusiness, Review) and a complete, verified Google Business Profile matter for local and commercial prompts. YouTube content is a frequent source; transcripts and clear titles/descriptions help.
- Reddit and forum threads are cited often for opinion and comparison queries, so monitor and contribute transparently where the brand's experts are genuinely useful.
- Use Search Console to watch impressions and clicks on queries that show AI features; expect lower click-through even with visibility.

## Perplexity
- Always shows citations, uses its own crawler plus search partners, and tends to cite more sources per answer with less brand bias than other engines, so newer or niche sites can win.
- Rewards: direct answers near the top, specific facts and numbers, clear sourcing, recent dates, primary research. Keep `dateModified` honest and current on evolving pages.
- Allow its crawler and its user-fetch agent. Verify names in its current docs.
- Reddit, review sites, and editorial roundups are common citations; Perplexity's Pages and Spaces can surface curated sources, so being a clean primary source helps.

## Cross-engine truths
1. **Retrievable**: not blocked, server-rendered key text, fast, in the relevant indexes (Bing and Google both).
2. **Extractable**: one idea per passage, answer first, specific, self-contained so it still makes sense when quoted out of context.
3. **Corroborated**: the same facts about the brand appear on independent sites. Disagreement between sources lowers confidence and gets the brand omitted or described wrongly.
4. **Fresh where it matters**: pricing, comparisons, "best of 2026" content, stats. Evergreen definitions need less churn.
5. **Entity-clear**: unambiguous name, category, location, founders, official profiles (`sameAs`), consistent descriptions everywhere.
6. **Measured by prompt set**, not by gut: re-run the same prompts monthly and track share of voice.
