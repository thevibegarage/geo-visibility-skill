# Measurement

AI visibility is noisy. Good measurement means a frozen prompt set, repeat runs, and trend lines, not single screenshots.

## Contents
- KPIs
- Prompt-set tracking
- Analytics setup
- Cadence and reporting
- Reading the results
- Tooling options

## KPIs
| KPI | Definition | Why |
|---|---|---|
| AI share of voice | Brand mentions / total brand mentions across the prompt set | Core visibility measure vs. competitors |
| Mention rate | % of prompts where the brand is named | Awareness |
| Citation rate | % of prompts where the brand's domain is linked | Traffic and trust potential |
| Average position | Mean rank when listed | Strength of recommendation |
| Accuracy rate | % of brand facts correct | Brand safety |
| Sentiment mix | Positive/neutral/negative share | Reputation |
| AI referral sessions | Sessions from AI referrers | Direct traffic |
| Assisted conversions | Conversions from AI-referred or AI-influenced visits | Business impact |
| Branded search lift | Growth in branded queries and direct traffic | AI exposure often shows up as brand searches |
| Source coverage | % of top-cited sources where the brand is present | Leading indicator |

## Prompt-set tracking
Use `assets/visibility-tracker-template.md` to store results (copy into Sheets/Excel if the user prefers; offer to build a spreadsheet). Freeze the prompt list and add new prompts as a separate cohort so trends stay comparable. Record engine, mode (search on/off), date, location, run number, brand mentioned/cited, position, sentiment, accuracy errors, cited domains.

## Analytics setup
- In GA4 (or equivalent) create a channel group for AI referrals using referrer matching for chatgpt.com, chat.openai.com, perplexity.ai, gemini.google.com, copilot.microsoft.com, claude.ai, and similar. Referrer domains change; review quarterly.
- Many AI visits arrive with no referrer (shown as direct). Track branded and direct lift alongside referrals and add a "How did you hear about us?" free-text field with "ChatGPT/AI assistant" as an option.
- Server logs: count requests from AI user-agents (search indexers and user fetchers) to see which pages are being retrieved and whether any are blocked. Bursts of user-fetch hits indicate real users asking about those pages.
- Search Console and Bing Webmaster Tools: watch impressions, clicks, and queries; Bing's reporting on AI-related performance, where available, is worth checking.
- Tag landing pages built for GEO so you can attribute lift.

## Cadence and reporting
- Weekly (light): server-log check for blocked AI agents, new errors, spot-check 5 money prompts.
- Monthly: full prompt-set re-run, KPI table, changes shipped, what moved, next experiments.
- Quarterly: refresh the prompt set (keep the frozen core), review engine changes, revisit the target source list.

Monthly report format: 1) headline movement, 2) KPI table with deltas, 3) wins and losses by engine, 4) accuracy fixes, 5) shipped work, 6) next 30 days.

## Reading the results
- Expect variance: treat changes under roughly 10 percentage points on small sets as noise until confirmed across two cycles.
- Content changes can show up within weeks on live-search engines; model-memory changes take far longer (tied to training cycles).
- If mentions rise but citations do not, strengthen first-party answer pages. If citations rise but sentiment is poor, fix reputation sources.
- Attribute cautiously: correlation is the norm. Use before/after on a specific page or prompt cohort when possible.

## Tooling options
Dedicated AI-visibility trackers exist and can automate prompt runs at scale; evaluate current options and their sampling methods before recommending one. A manual tracker plus Claude-assisted analysis is enough to start and is transparent about methodology. Never present vendor "visibility scores" without knowing how prompts were sampled.
