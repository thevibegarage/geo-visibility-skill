# Technical readiness

If crawlers cannot fetch and read the content, nothing else matters. Check these in order.

## Contents
- Crawler access (robots.txt and firewalls)
- Rendering
- Indexes and discovery
- Structured data
- llms.txt
- Snippet, archive and indexing controls
- Page-level hygiene
- Checklist table

## Crawler access
Three kinds of agents exist per vendor; treat them separately:
1. **Training crawlers** collect data for model training.
2. **Search/indexing crawlers** build the index used to retrieve and cite pages.
3. **User-initiated fetchers** load a page when a user asks about it or shares a URL.

Business decision for the owner: many brands opt out of training but stay open to search and user fetch so they can still be cited. Blocking only the training agent generally does not remove a site from AI search answers. Confirm exact user-agent strings in each vendor's current documentation before writing rules (OpenAI, Anthropic, Perplexity, Google, Microsoft/Bing, Apple, Common Crawl, Meta, ByteDance, Amazon). Agent names get added and retired.

As of October 2026, verified against vendor docs: OpenAI documents GPTBot (training), OAI-SearchBot (search indexing) and ChatGPT-User (user-initiated fetch); Anthropic documents ClaudeBot (training), Claude-SearchBot (search indexing) and Claude-User (user-initiated fetch), with crawler IPs published at claude.com/crawling/bots.json; Perplexity documents PerplexityBot (search indexing) and Perplexity-User (user fetch). Two caveats vendors state themselves: **user-fetch agents (ChatGPT-User, Perplexity-User) may not honor robots.txt**, since a live user triggers the request; and **Google-Extended** controls Gemini training and grounding only — Google states it does not affect Search inclusion or ranking.

Other assistants and search surfaces with documented crawlers (verify each name before writing rules): Applebot and Applebot-Extended (Apple), Amazonbot, meta-externalagent and meta-externalfetcher (Meta), MistralAI-User, DuckAssistBot, Bytespider (ByteDance). `scripts/check_ai_readiness.py` reports rules for these as `info`: allowing or blocking them is a business decision, not a defect. Brave Search (reported to power Claude's web search) does not publish a robots token the script can test: check indexing on search.brave.com instead.

**How robots.txt groups work (a common cause of silent mistakes):** a crawler obeys only the most specific group that names it and does not also apply the `User-agent: *` group. Naming `Googlebot` or `GPTBot` with just `Allow: /` therefore opens every path the `*` group disallowed (`/admin/`, `/cart/`, `/checkout/`). Repeat private-path rules inside every named group, or list several `User-agent:` lines above one shared block. Paths support `*` and a trailing `$`, and the longest matching rule wins (Allow wins a tie): `Disallow: /blog` plus `Allow: /blog/public` allows `/blog/public/x`. A missing robots.txt (4xx) means allow-all; a persistent 5xx is treated by Google as disallow-all, so a flaky robots.txt can pause crawling of the whole site.

Common failure modes to test:
- Blanket `Disallow: /` for unknown bots copied from a template.
- CDN/WAF bot protection (Cloudflare, Akamai, etc.) silently challenging or blocking AI agents while robots.txt says Allow. Check bot-management settings and server logs for 403/429 to AI agents.
- Login walls, cookie walls, or geo-blocks in front of public content.
- Rate limits that cut off retrieval bursts.

Use `assets/robots-ai-template.txt` as a starting point.

## Rendering
- Many AI crawlers do not execute JavaScript reliably. Key facts (what you sell, pricing, FAQs, comparisons) must be in the initial HTML response.
- **Test as each kind of agent, not as yourself.** Sites often detect crawlers by user agent (middleware, a prerender service, dynamic rendering) and serve them full HTML, while a default `curl`, browser or WebFetch gets the empty single-page-app shell. Fetch 3-5 detail pages (not just the homepage) as: (a) a browser, (b) a listed crawler such as GPTBot, (c) an unlisted user-fetch agent such as Claude-User or ChatGPT-User, (d) Googlebot and (e) Bingbot, each with a realistic user-agent string (`Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-User/1.0; +Claude-User@anthropic.com)`). `scripts/check_ai_readiness.py --paths ...` does this and compares word count, H1, title and JSON-LD. Googlebot and Bingbot run JavaScript, so a thin raw page is not a failure for them; what the script flags is a refusal (HTTP 4xx/5xx), or Googlebot and Bingbot receiving different pages (a prerender allowlist that names one and not the other leaves Bing, and Copilot with it, on a shell). A 403 for a spoofed Googlebot or Bingbot is weak evidence, since WAFs that verify bots by IP reject spoofed copies: confirm in Search Console or Bing Webmaster Tools URL Inspection.
- Reading the result: shell for everyone = a real rendering Fail. Content for listed crawlers but a shell for unlisted user-fetch agents = a routing gap (the allowlist is missing agents); these agents matter most for citations because they fire when a person asks about a URL. Content for crawlers but a shell for a browser fetch = dynamic rendering working as designed, so credit it as a pass.
- Confirm any rendering Fail with a second source before reporting it: the site's middleware or rewrite code, server logs showing what each agent received, a vendor-run fetch, or Search Console URL Inspection. One default fetch is not enough.
- An allowlist that matches substrings like "bot", "crawler" or "spider" will pass a monitoring probe that includes those words while real agents with other names (Claude-User, MistralAI-User, Meta-ExternalFetcher) still get the shell. Probe with realistic strings and review the agent list against vendor docs on a schedule.
- Pages in languages without spaces (Chinese, Japanese, Korean, Thai) are measured by characters; the script's word counts are an approximation there.
- A short page is not automatically a shell: the script warns rather than fails when a page has an H1 and a few dozen words for every agent. Judge by what the page should say.
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
- **Bing**: verify the site in Bing Webmaster Tools, submit the sitemap, enable IndexNow, allow Bingbot at robots and WAF, and read the AI Performance report (Copilot and Bing AI-summary citations). Copilot and Bing's AI summaries ground on Bing's index, and ChatGPT search is reported to use Bing-class results. Full checklist: `bing-copilot.md`. `check_ai_readiness.py` reports a verification hint and, with `--indexnow-key`, verifies the key file.
- **Google**: Search Console verified, sitemap submitted, no accidental `noindex`, clean canonicals.
- **Brave**: Claude's web search is reported to run on Brave Search. Search the brand and money queries on search.brave.com; if pages are missing, fix crawlability and earn links from sites Brave already indexes. No verification console is known to exist (verify).
- Sitemap: accurate `lastmod` (only change when content actually changes), includes all money pages. The script follows sitemap indexes (first 5 children), reads `.xml.gz`, and warns when `--paths` URLs are missing from the sitemap.
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

## Snippet, archive and indexing controls
These directives, set in `<meta name="robots">`, bot-specific metas (`googlebot`, `bingbot`) or an `X-Robots-Tag` header, decide whether a page can be indexed and how much of it AI answers may quote. They are often set by accident, by an SEO plugin default or a staging template that reached production.

| Directive | Effect (verify against current docs) |
|---|---|
| `noindex` / `none` | Page is dropped from the index; it cannot be retrieved or cited |
| `nosnippet`, `max-snippet:0` | No text snippet; Google states these also limit AI Overviews and AI Mode, and they limit quoting in Bing/Copilot |
| `max-snippet:N` | Caps the quoted length; a very low N starves AI answers |
| `data-nosnippet` (HTML attribute, Google) | Excludes that element from snippets and AI features |
| `noarchive` | Bing: page is not linked in Copilot answers, per Bing docs as reported; Google: no cached link only |
| `nocache` (Bing) | Bing may use only URL, title and snippet |
| `Google-Extended` (robots.txt token) | Controls Gemini training and grounding only; per Google it does not affect Search inclusion or AI Overviews |

Two points teams get wrong: robots.txt blocks crawling, not indexing (a blocked URL can still be indexed from links, and a crawler that cannot fetch the page cannot see its `noindex`); and there is no separate AI Overviews opt-out beyond the snippet controls above. If a brand deliberately opts out (paywalled publisher, licensing), record it as an owner decision. `check_ai_readiness.py` reports `noindex` as a failure and snippet/archive restrictions as a warning on the homepage; check key templates too.

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
| Googlebot and Bingbot get the same page | Same word count and content for each `--paths` URL | `check_ai_readiness.py --paths` | add Bingbot to the prerender or allowlist rules |
| Bing indexed | Site verified, pages indexed | Bing Webmaster Tools | submit sitemap, IndexNow |
| IndexNow | Key file served at the root; submissions on real changes | `--indexnow-key`, Bing Webmaster Tools | add key file or CMS plugin |
| Bing AI Performance report | Reviewed and exported monthly | Bing Webmaster Tools | schedule the export; see `bing-copilot.md` |
| Brave indexed | Brand and money pages appear on search.brave.com | manual `site:` and brand searches | crawlability, links from indexed sites |
| Snippet/archive controls | No unintended `nosnippet`, `max-snippet:0`, `noarchive`, `nocache`, `noindex` | script, view source, response headers | remove or record as an owner decision |
| robots.txt groups | Private paths disallowed inside every named group; no 5xx | script, `assets/robots-ai-template.txt` | repeat rules per group; fix server errors |
| Google indexed | Pages indexed, no noindex | Search Console | fix canonicals |
| Organization schema | Valid, sameAs complete | Rich Results Test | add JSON-LD |
| Article/Product schema | Valid, dates honest | validator | add JSON-LD |
| llms.txt | Exists, accurate | fetch /llms.txt | create from template |
| Dates and authors visible | Present on content pages | manual | add bylines |
