# Bing and Microsoft Copilot

Bing is not a side note. Its index grounds Microsoft Copilot and Bing's AI summaries, and ChatGPT search is reported to use Bing-class results alongside OpenAI's own index; DuckDuckGo and Yahoo are reported to lean on Bing too. A brand that is invisible to Bing is invisible to all of them, whatever its Google rankings say. Microsoft also gives site owners something no other assistant does: a first-party report of how often their pages are cited in AI answers.

Confidence labels follow `evidence-and-claims.md`. Facts marked "reported" come from trade coverage or practitioner testing, not from Microsoft's own documentation, and were not re-verified against Microsoft's docs in this session. Check Bing Webmaster Tools documentation before you ship anything that depends on them.

## Contents
- How Bing, Copilot and the other surfaces connect
- Setup in Bing Webmaster Tools (do this first)
- IndexNow
- Crawling: Bingbot, robots.txt, WAF and rendering
- Page-level controls (nocache, noarchive, nosnippet)
- The AI Performance report
- Content and entity signals
- Local: Bing Places
- Testing in Copilot
- Common failure modes
- Checklist

## How Bing, Copilot and the other surfaces connect
- **Copilot** (copilot.microsoft.com, Windows, Edge, Microsoft 365 surfaces) and **Bing's AI summaries** answer from Bing's index and cite it. The AI Performance report's "grounding queries" are the retrieval queries Copilot ran against that index (confidence: high that grounding is on Bing's index; the report documents it).
- **ChatGPT search** uses a mix of Bing-class results and OpenAI's own crawl (OAI-SearchBot); the weighting is not disclosed and has been shifting toward OpenAI's index (reported). Being healthy in Bing still matters; it is not the whole story.
- **DuckDuckGo, Yahoo and other Bing-syndicated search** (reported): one Bingbot policy governs them all.
- **Google is separate.** Strong Google rankings do not make a site indexed or fresh in Bing. Treat them as two programs sharing one technical foundation.

## Setup in Bing Webmaster Tools (do this first)
1. **Verify the site** at bing.com/webmasters. Methods: import from Google Search Console (fastest), an XML file (`BingSiteAuth.xml`), a meta tag (`msvalidate.01`), or a DNS CNAME record. `scripts/check_ai_readiness.py` looks for the meta tag and the XML file and reports `info` if it finds neither; that does not prove the site is unverified (a CNAME or an import leaves no trace on the page).
2. **Submit sitemaps** (sitemap index files are fine). Confirm the sitemap lists the money pages and carries honest `lastmod` dates.
3. **Enable IndexNow** (next section).
4. **Inspect key URLs** with URL Inspection: is the page indexed, what did Bingbot fetch, what does it render?
5. **Check crawl errors and blocked URLs** in the reports, and compare indexed-page counts with Google's.
6. **Open the AI Performance report** and export it (see below).
7. **Add every property** you own (apex and `www`, subdomains that host docs or the blog).

## IndexNow
IndexNow lets a site tell participating engines, including Bing, which URLs were added, changed or deleted, instead of waiting for a crawl. Bing recommends it over its older URL-submission APIs (reported).
- Generate a key and host it as a text file at the site root (`https://example.com/<key>.txt`, content = the key), or at a `keyLocation` you pass with each submission. `scripts/check_ai_readiness.py --indexnow-key <key>` verifies the root key file.
- Submit on real changes only: publish, update, delete. Pinging unchanged URLs wastes quota and signals nothing.
- Pair it with truthful `lastmod` values in the sitemap. Many CMS and CDN products ship an IndexNow plugin; prefer that to a hand-written cron job.
- IndexNow speeds up discovery. It does not make a page rank or get cited.

## Crawling: Bingbot, robots.txt, WAF and rendering
- **Allow Bingbot** in robots.txt. `assets/robots-ai-template.txt` does. One `Bingbot` rule governs Bing, Copilot and the Bing-syndicated surfaces above. Remember that a named robots group does not inherit the `*` group: repeat private-path rules inside the Bingbot group.
- **WAF and CDN.** Bot-protection products often challenge Bingbot. A user-agent-only probe (what `check_ai_readiness.py` does) cannot prove the real crawler is blocked, because WAFs that verify bots by IP reject spoofed user agents. Verify the real thing: Bing Webmaster Tools URL Inspection, server logs filtered by reverse-DNS-verified Bingbot IPs, and Microsoft's published Bingbot IP list (check Bing's documentation for the current URL).
- **Rendering.** Bingbot runs a modern, Edge-based renderer and can execute JavaScript, but rendering is slower and less reliable than reading static HTML (reported). Keep core facts in the initial HTML. Make sure any prerender or dynamic-rendering allowlist includes Bingbot: a site that serves Googlebot full HTML and Bingbot a shell is invisible to Copilot. `check_ai_readiness.py` fetches every `--paths` URL as Googlebot and as Bingbot and warns when they get different pages.
- **Verified user agent.** `Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)`; newer builds append a browser token. Verify against Microsoft's documentation; strings change.

## Page-level controls (nocache, noarchive, nosnippet)
Per Bing's documentation as reported in trade coverage (verify before relying on it):
- `noarchive`: the page is not linked in Copilot answers and is excluded from training Microsoft's generative models.
- `nocache`: Bing may use only the URL, title and snippet.
- `nosnippet` / `max-snippet`: limits what text can be quoted.
These apply to `<meta name="robots">` and to `<meta name="bingbot">`, and the equivalent `X-Robots-Tag` header. Teams add them for legitimate reasons (paywalls, licensing) and sometimes by accident through an SEO plugin default. `check_ai_readiness.py` flags them on the homepage as a warning so someone confirms the choice. See `technical-readiness.md` for the Google equivalents.

## The AI Performance report
Launched in Bing Webmaster Tools in February 2026 as a public preview (reported by Search Engine Land and others). Any verified site can open it.
- **What it shows:** total citations across Copilot, Bing's AI-generated summaries and select partner integrations; the average number of unique cited pages per day; per-page citation counts; and **grounding queries**, sample retrieval queries that led to citations.
- **Limits at launch:** CSV export from the dashboard, no API (Microsoft said an API is on the backlog), and no filter by single surface or by partner. Re-read the current report before you describe it to a client.
- **How to use it:**
  1. Export monthly and keep the files: you build your own history.
  2. Add the grounding queries to the prompt set as a separate cohort (they are the questions the engine actually asked about your content).
  3. Cross-check cited pages against the Phase 1 "top cited domains" list: pages cited often are your answer-first templates; pages never cited are rewrite candidates.
  4. Report it as citation counts, not as a ranking or as share of voice. It says nothing about competitors.
- Google Search Console does not show Copilot citations. This report is the only first-party Copilot signal.

## Content and entity signals
- Freshness: Bing pushes accurate `lastmod` and IndexNow (reported), and live-search engines favor current pages for time-sensitive topics (see `evidence-and-claims.md`). Use honest `lastmod`, IndexNow on real edits, and visible "last updated" dates that match the schema.
- Clear titles, descriptions and headings still matter to Bing's ranking and to passage extraction.
- Microsoft representatives have said schema markup helps their language models understand pages (reported; medium confidence). Ship valid `Organization`, `Article`/`Product` and `FAQPage` JSON-LD that mirrors visible text.
- Entity consistency (see `offsite-authority.md`): LinkedIn is a Microsoft property, so it is a plausible source for company and people questions in Copilot (hypothesis: check whether it shows up in your cited-domain list). Keep it complete and consistent with the fact sheet either way.
- The sources Copilot cites for "best X" prompts are the real target list. Run the prompts in Copilot and rank the cited domains like any other engine.

## Local: Bing Places
For location-bound businesses, claim and complete the listing in Bing Places for Business (it can import from Google Business Profile), keep name, address and phone identical to every other directory, and add photos, hours and categories. Apple Business Connect is a separate listing for Apple Maps and Siri.

## Testing in Copilot
- Run the frozen prompt set at copilot.microsoft.com, signed out where possible, with the mode noted in the `mode` column (`search` for answers that use web search, `no-search` if you can switch it off). Use the engine name `Copilot` in the tracker; `score_tracker.py` folds Bing Chat and Microsoft Copilot into it.
- Record cited URLs: Copilot shows its sources inline. Log factual errors verbatim.
- If the user cannot run Copilot, give them the prompt sheet and the tracker CSV and ask them to paste results back, as for any other engine. State in the report which engines were not run.

## Common failure modes
- Verified in Google Search Console but never added to Bing Webmaster Tools, so nobody ever looked at Bing's index.
- Bingbot challenged or blocked at the WAF while robots.txt says Allow.
- A prerender allowlist that names Googlebot and not Bingbot.
- Sitemap never submitted to Bing, or `lastmod` stamped with today's date on every request.
- Core content only in JavaScript.
- Accidental `nosnippet`, `noarchive` or `nocache` from a template or plugin.
- Different facts on the site, LinkedIn and Bing Places, so grounded answers contradict each other.

## Checklist
| Check | Pass criteria | How to test | Fix |
|---|---|---|---|
| Bing Webmaster Tools verified | Property verified, sitemap submitted | Bing Webmaster Tools; `check_ai_readiness.py` hint | verify, submit sitemap |
| IndexNow live | Key file served; submissions on real changes | `--indexnow-key`; BWT IndexNow report | add key file or CMS plugin |
| Bingbot not blocked | robots Allow; no WAF challenge | script (robots + WAF warn); URL Inspection; logs | allowlist verified Bingbot |
| Googlebot and Bingbot see the same page | Same word count and content per `--paths` URL | `check_ai_readiness.py --paths` | add Bingbot to prerender or allowlist rules |
| No accidental snippet/archive limits | No `nosnippet`, `max-snippet:0`, `noarchive`, `nocache` unless intended | script warning; view source; headers | remove or document |
| AI Performance report reviewed | Exported monthly; grounding queries added to the prompt set | Bing Webmaster Tools | schedule the export |
| Copilot in the tracker | Prompt set run in Copilot, results logged | `score_tracker.py` shows a Copilot row | run and log |
| Bing Places (local) | Listing complete and consistent | Bing Places | claim, complete, align NAP |
