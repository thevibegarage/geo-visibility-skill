# Technical readiness

If crawlers cannot fetch and read the content, nothing else matters. Check these in order.

## Contents
- Crawler access (robots.txt and firewalls)
- Rendering
- Indexes and discovery
- Structured data
- llms.txt
- Page-level hygiene
- Checklist table

## Crawler access
Three kinds of agents exist per vendor; treat them separately:
1. **Training crawlers** collect data for model training.
2. **Search/indexing crawlers** build the index used to retrieve and cite pages.
3. **User-initiated fetchers** load a page when a user asks about it or shares a URL.

Business decision for the owner: many brands opt out of training but stay open to search and user fetch so they can still be cited. Blocking only the training agent generally does not remove a site from AI search answers. Confirm exact user-agent strings in each vendor's current documentation before writing rules (OpenAI, Anthropic, Perplexity, Google, Microsoft/Bing, Apple, Common Crawl, Meta, ByteDance, Amazon). Agent names get added and retired.

As of October 2026, verified against vendor docs: OpenAI documents GPTBot (training), OAI-SearchBot (search indexing) and ChatGPT-User (user-initiated fetch); Anthropic documents ClaudeBot (training), Claude-SearchBot (search indexing) and Claude-User (user-initiated fetch), with crawler IPs published at claude.com/crawling/bots.json; Perplexity documents PerplexityBot (search indexing) and Perplexity-User (user fetch). Two caveats vendors state themselves: **user-fetch agents (ChatGPT-User, Perplexity-User) may not honor robots.txt**, since a live user triggers the request; and **Google-Extended** controls Gemini training and grounding only — Google states it does not affect Search inclusion or ranking.

Common failure modes to test:
- Blanket `Disallow: /` for unknown bots copied from a template.
- CDN/WAF bot protection (Cloudflare, Akamai, etc.) silently challenging or blocking AI agents while robots.txt says Allow. Check bot-management settings and server logs for 403/429 to AI agents.
- Login walls, cookie walls, or geo-blocks in front of public content.
- Rate limits that cut off retrieval bursts.

Use `assets/robots-ai-template.txt` as a starting point.

## Rendering
- Many AI crawlers do not execute JavaScript reliably. Key facts (what you sell, pricing, FAQs, comparisons) must be in the initial HTML response.
- **Test as each kind of agent, not as yourself.** Sites often detect crawlers by user agent (middleware, a prerender service, dynamic rendering) and serve them full HTML, while a default `curl`, browser or WebFetch gets the empty single-page-app shell. Fetch 3-5 detail pages (not just the homepage) as: (a) a browser, (b) a listed crawler such as GPTBot, (c) an unlisted user-fetch agent such as Claude-User or ChatGPT-User, each with a realistic user-agent string (`Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-User/1.0; +Claude-User@anthropic.com)`). `scripts/check_ai_readiness.py --paths ...` does this and compares word count, H1, title and JSON-LD.
- Reading the result: shell for everyone = a real rendering Fail. Content for listed crawlers but a shell for unlisted user-fetch agents = a routing gap (the allowlist is missing agents); these agents matter most for citations because they fire when a person asks about a URL. Content for crawlers but a shell for a browser fetch = dynamic rendering working as designed, so credit it as a pass.
- Confirm any rendering Fail with a second source before reporting it: the site's middleware or rewrite code, server logs showing what each agent received, a vendor-run fetch, or Search Console URL Inspection. One default fetch is not enough.
- An allowlist that matches substrings like "bot", "crawler" or "spider" will pass a monitoring probe that includes those words while real agents with other names (Claude-User, MistralAI-User, Meta-ExternalFetcher) still get the shell. Probe with realistic strings and review the agent list against vendor docs on a schedule.
- Avoid putting core text in images, PDFs-only, accordions that load via JS, or iframes. If PDFs matter, provide HTML equivalents.
- Use semantic HTML: one `<h1>`, ordered headings, real `<table>` for comparisons, `<ul>`/`<ol>` for lists, descriptive alt text.
- Fast TTFB and stable pages; time-outs reduce retrieval.

## Unknown URLs and soft 404s
- A nonexistent URL must return 404 or 410. Single-page apps and catch-all rewrites often return 200 with the homepage for every path, so crawlers index junk URLs and AI engines may quote pages that do not exist (/pricing, /contact and /services are common phantom requests).
- Test as crawler agents (people may legitimately see the app's own not-found view with a 200): request a random path and a few plausible-but-missing paths. Fix by returning 404 plus `noindex` to crawlers for paths outside the known routes, keeping the route list in sync with the router. Redirect retired URLs with a 301 to the nearest live page.

## Freshness of facts
- Dates, prices and names in schema, `llms.txt`, sitemaps and page copy must come from one source of truth (CMS or database), not hand-edited copies. Hand-edited files drift: renamed programmes keep old names, cohort start dates stay after they have passed.
- Never present a past start date as upcoming: emit `CourseInstance`/`Event` only for future dates, and omit date lines otherwise.
- Say whether prices include tax. Where GST/VAT is separate, show base plus tax plus total in visible text, and in schema use `priceSpecification` with `valueAddedTaxIncluded` set correctly.
- Time zones: a timestamp stored in UTC can be the next calendar day locally (2026-10-23T18:30Z is 24 October in India). Emit schema dates with the local offset (`2026-10-24T00:00:00+05:30`) or as a date, and format visible dates in the business's time zone.
- Sitemap `lastmod` must be a real edit date. Many identical dates, or today's date on every request, tell crawlers nothing. Omit it when unknown.

## Indexes and discovery
- **Bing**: verify the site in Bing Webmaster Tools, submit the sitemap, enable IndexNow. Several AI assistants lean on Bing's index.
- **Google**: Search Console verified, sitemap submitted, no accidental `noindex`, clean canonicals.
- Sitemap: accurate `lastmod` (only change when content actually changes), includes all money pages.
- Internal links: every important page reachable in 3 clicks; hub pages link to their cluster.
- Redirect chains and 404s on previously linked URLs: fix, since third-party mentions often point to old URLs.

## Structured data
JSON-LD in the initial HTML. Priorities:
1. `Organization` (name, url, logo, description, `sameAs` to official profiles, contact, founders) on the homepage/about page.
2. `WebSite`, `WebPage`/`Article` with `author`, `datePublished`, `dateModified` on content.
3. `Product`/`Offer`/`AggregateRating` (only with real, visible reviews), `SoftwareApplication`, `Service`, `LocalBusiness` as relevant.
4. `FAQPage` and `HowTo`: still useful as machine-readable structure even where Google limits rich results; content must match visible text.
5. `BreadcrumbList`.
Rules: markup must mirror visible content, no invented ratings, validate with Google Rich Results Test and Schema.org validator. Templates in `assets/schema-templates.md`.

## llms.txt
A proposed convention: a markdown file at `/llms.txt` that summarizes the site and links to the most useful pages (optionally `/llms-full.txt` with expanded content). Honest position: adoption by engines is unproven and no strong evidence shows it increases citations by itself. It is cheap, helps agent and developer use cases, and forces a useful content-curation exercise. Ship it after the basics, keep it accurate, and never claim it is a ranking factor. Generate its programme, product and price sections from the same source of truth as the site at build time (with a pointer to the live catalogue as the fallback if the source is unreachable) so it cannot go stale. Template in `assets/llms-txt-template.md`. Also consider clean markdown versions of key docs pages.

## Page-level hygiene
- Visible "Last updated" date that matches `dateModified`; do not bump dates without real changes.
- Named authors with bios and credentials; an About page with real company facts; contact details; policies.
- Canonical tag on every page; no duplicate near-identical pages competing.
- Meta title/description still matter for classic SEO and as a summary signal.
- HTTPS, mobile-friendly, accessible. Core Web Vitals in the green.

## Checklist table (use in the deliverable)
| Check | Pass criteria | How to test | Fix |
|---|---|---|---|
| AI agents not blocked in robots.txt | Search + user-fetch agents allowed | script / fetch robots.txt | edit robots |
| WAF not blocking AI agents | No 403/429 for those agents | server logs, CDN dashboard | allowlist |
| Key text in initial HTML, per agent | Browser, listed crawler and unlisted user-fetch agents all get product, pricing, FAQ without JS | `check_ai_readiness.py --paths`, curl -A, code/log cross-check | SSR/static render; add missing agents to the allowlist |
| Unknown URLs return 404 | Random and plausible-missing paths give 404/410 to crawlers | curl -A for each agent class | 404 + noindex to crawlers; 301 retired URLs |
| Facts fresh and consistent | Schema, llms.txt and pages match the CMS; no past dates shown as upcoming; tax stated | compare against the source of truth | generate from one source |
| Sitemap lastmod honest | Real edit dates or omitted | script warns on clustering | emit real dates |
| Bing indexed | Site verified, pages indexed | Bing Webmaster Tools | submit sitemap, IndexNow |
| Google indexed | Pages indexed, no noindex | Search Console | fix canonicals |
| Organization schema | Valid, sameAs complete | Rich Results Test | add JSON-LD |
| Article/Product schema | Valid, dates honest | validator | add JSON-LD |
| llms.txt | Exists, accurate | fetch /llms.txt | create from template |
| Dates and authors visible | Present on content pages | manual | add bylines |
