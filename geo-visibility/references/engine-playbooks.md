# Engine playbooks

Behavior below reflects widely reported patterns as of late 2026 and is a starting hypothesis. Engines change constantly and published studies disagree. Re-check official docs and re-run the audit before committing effort. Cross-engine overlap in cited sources is low, so measure each engine separately.

## Contents
- ChatGPT
- Microsoft Copilot and Bing
- Claude (and Brave)
- Gemini and Google AI Overviews / AI Mode
- Perplexity
- Other assistants and regional engines
- Cross-engine truths

## ChatGPT
- Two modes: answers from model memory (training data, frozen at a cutoff) and answers with live search. Reports indicate the search layer uses a mix of Bing-class results and OpenAI's own crawl, with the weighting undisclosed and shifting toward OpenAI's index, so being indexed and healthy in Bing Webmaster Tools still matters (see `bing-copilot.md`) but is not sufficient on its own.
- OpenAI documents separate crawlers: one for training, one for search indexing, one for user-initiated fetches. Allow the search and user-fetch agents if you want citations. Verify names in OpenAI's current crawler documentation.
- Recommendations lean on brands with broad corroboration: review sites, "best of" listicles, Wikipedia, Reddit, news. For "best X" prompts, the cited listicles are often the real lever.
- Structured, scannable passages (short answers, bullets, FAQs, tables) get lifted more easily. Freshness helps; show real updated dates and actually update.
- Shopping/product prompts reward complete product data: clear specs, pricing, availability, reviews, Product schema, and a merchant feed where supported.

## Microsoft Copilot and Bing
- Copilot and Bing's AI summaries ground their answers in Bing's index and cite it. Strong Google rankings say nothing about Bing coverage: verify the site in Bing Webmaster Tools, submit sitemaps, enable IndexNow, allow Bingbot at robots and WAF, and make sure any prerender allowlist names Bingbot.
- Microsoft publishes a first-party **AI Performance report** in Bing Webmaster Tools (launched Feb 2026): citations in Copilot and Bing AI summaries, cited pages and grounding queries, CSV export. It is the only direct Copilot signal a site owner gets; export it monthly and feed the grounding queries into the prompt set.
- Bing documents `nocache`/`noarchive` meta directives that limit or exclude a page from Copilot answers (reported; verify). Check that no template adds them by accident.
- Test it as its own engine: run the frozen prompts in Copilot and log them as `Copilot` in the tracker. Full playbook, setup checklist and failure modes: `references/bing-copilot.md`.

## Claude (and Brave)
- Claude answers from training knowledge and, when web search is on, retrieves live pages. Anthropic publishes separate agents: one for training, one for search indexing, one for user-initiated fetches. Blocking the training agent does not by itself block citation from search/user fetch. Verify names in Anthropic's current crawler documentation and do not rely on retired agent names that older guides still list.
- Claude tends to cite fewer sources and reward depth, primary sources, clear definitions and well-attributed facts over thin listicles. Original data, methodology notes and direct quotes from named experts help.
- Because model memory matters, long-run presence in high-quality, widely-replicated sources (documentation, reputable publications, Wikipedia/Wikidata, GitHub, standards bodies) shapes what Claude "knows" about a brand even without search.
- For developer or B2B tools: excellent public docs, a clear llms.txt or markdown-accessible docs, and an MCP server or API listing help agentic use, where Claude acts on the brand's behalf rather than just citing it. Treat "agent readiness" (clear pricing, signup path, machine-readable catalog) as part of GEO.
- Claude's web search is reported to run on Brave Search (Anthropic lists Brave Search among its subprocessors; results have been observed to match Brave's). That makes **Brave's index** a retrieval dependency the Bing-and-Google advice misses: search the brand and its money queries on search.brave.com and check the pages appear. Brave does not offer a webmaster console comparable to Bing's (verify), so the levers are crawlable pages, links from sites Brave already indexes, and clean sitemaps.
- Claude-in-the-loop test: use WebSearch in this session for the target prompts and record what it surfaces. Treat it as a proxy, not a reading of consumer Claude: the search tool, region and result format can differ from the consumer product (the same rule as Phase 1 in `SKILL.md`).

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

## Other assistants and regional engines
Coverage here is thinner and mostly unverified; use it as a checklist of what to look into per market, not as a playbook.
- **Meta AI** (WhatsApp, Instagram, Facebook; very large in India): Meta documents `meta-externalagent` and `meta-externalfetcher` crawlers. Allow them if you want to appear; verify names in Meta's crawler documentation.
- **Apple (Siri, Spotlight, Apple Intelligence)**: `Applebot` for search; `Applebot-Extended` is a robots token that opts out of training use only.
- **Amazon (Alexa+)**: `Amazonbot`; verify its documented uses before blocking.
- **Mistral Le Chat**: `MistralAI-User` for user-triggered fetches. **DuckDuckGo AI answers**: `DuckAssistBot`; DuckDuckGo search is reported to be Bing-backed.
- **Grok, DeepSeek, You.com, Kagi and similar**: no stable site-owner controls to rely on. Run the frozen prompts there if your audience uses them, and log what is cited.
- **Regional**: Baidu (Ernie), Naver, Yandex (Alice), Doubao, Kimi and Qwen run on their own indexes and crawlers. If the brand sells in those markets, verify each engine's crawler and webmaster tools before allocating effort; Google-first advice does not transfer.
- `scripts/check_ai_readiness.py` reports robots rules for the documented tokens above as `info`; whether to allow them is a business choice.

## Cross-engine truths
1. **Retrievable**: not blocked, server-rendered key text, fast, in the relevant indexes (Bing, Google and, for Claude, Brave).
2. **Extractable**: one idea per passage, answer first, specific, self-contained so it still makes sense when quoted out of context.
3. **Corroborated**: the same facts about the brand appear on independent sites. Disagreement between sources lowers confidence and gets the brand omitted or described wrongly.
4. **Fresh where it matters**: pricing, comparisons, "best of 2026" content, stats. Evergreen definitions need less churn.
5. **Entity-clear**: unambiguous name, category, location, founders, official profiles (`sameAs`), consistent descriptions everywhere.
6. **Measured by prompt set**, not by gut: re-run the same prompts monthly and track share of voice.
