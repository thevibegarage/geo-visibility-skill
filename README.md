# GEO Visibility — a Claude Skill for Generative Engine Optimization

[![Release](https://img.shields.io/github/v/release/thevibegarage/geo-visibility-skill)](https://github.com/thevibegarage/geo-visibility-skill/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

Audit and improve how a brand is found, cited and recommended inside **ChatGPT, Claude, Gemini, Perplexity, Copilot and Google AI Overviews** — while keeping classic SEO strong.

**See what it produces → [sample audit report](examples/sample-report.md)** · Install in 30 seconds below.

Built and open-sourced by [Garage Labs Technologies](https://www.garagelabstech.com), an AI transformation partner headquartered in India.

## What it does

The skill works on one idea: **AI engines recommend what they can retrieve, understand and trust.** It runs a six-phase process:

1. **Baseline audit** — 25–50 buyer prompts run across engines, scored for mentions, citations, position and share of voice. The key output is the ranked list of domains the engines actually cite in your category.
2. **Technical readiness** — crawler access (robots.txt, WAF), rendering without JavaScript as each agent sees it (including Googlebot and Bingbot), Bing and Google indexing (Bing Webmaster Tools, IndexNow), snippet and archive controls, structured data, llms.txt.
3. **Entity and content** — a canonical brand fact sheet, answer-first page rewrites, content briefs for every prompt you lose.
4. **Off-site authority** — a ranked, ethical plan for review sites, "best of" lists, press and community presence.
5. **Engine-specific tuning** — per-engine playbooks with confidence levels, including a dedicated [Bing and Microsoft Copilot playbook](geo-visibility/references/bing-copilot.md).
6. **Measurement** — a frozen prompt set, tracker CSV, roll-up script, and a treated-vs-control page experiment.

It also includes two standard-library Python scripts:

- `scripts/check_ai_readiness.py <domain>` — checks robots.txt rules (wildcards, longest-match, group semantics) for AI and search agents, WAF behavior, llms.txt, sitemaps (indexes, gzip), JSON-LD, snippet/archive controls, Bing/Google verification hints, IndexNow, and whether key text survives without JavaScript for a browser, listed crawlers, user-fetch agents, Googlebot and Bingbot.
- `scripts/score_tracker.py tracker.csv` — rolls your prompt-run CSV into mention rate, citation rate, share of voice, sentiment mix and a cited-domain list, per engine and mode (search vs no-search), with `--by-stage`, `--domain` and month-over-month deltas via `--compare`. Accepts 1/0 or TRUE/FALSE from spreadsheets.

## Install

**Claude (web/desktop):** download `geo-visibility.skill` from [Releases](../../releases), attach it in a chat, and click **Save skill** (requires an org that allows custom skills). To build it yourself from a checkout: `python3 tools/build_skill.py` writes `dist/geo-visibility.skill`.

**Claude Code:** copy the `geo-visibility/` folder into `~/.claude/skills/`.

Then just ask: *"Why doesn't ChatGPT mention my brand?"* or *"Run an AI visibility audit on example.com."*

## Run it as a GitHub Action (no Claude needed)

The technical-readiness checker runs standalone. Fork this repo, enable Actions on the fork (GitHub does not run scheduled workflows on forks until you do, and pauses them after 60 days of inactivity), set a `GEO_DOMAIN` repository variable (Settings → Secrets and variables → Actions → Variables), and [the included workflow](.github/workflows/ai-readiness.yml) checks your site every Monday — robots.txt rules for AI crawlers and Bingbot, WAF behavior, rendering without JavaScript for each agent, schema, sitemap, llms.txt — and fails the run if something is blocking you. Optional variables: `GEO_PATHS` (detail pages to compare across agents) and `GEO_INDEXNOW_KEY`. If your WAF challenges GitHub's datacenter IPs, the run reports "homepage returned HTTP 403" and stops instead of inventing findings. Or run it locally:

```bash
python3 geo-visibility/scripts/check_ai_readiness.py yourdomain.com --paths /pricing /about --indexnow-key YOUR_KEY --fail-on fail
```

On macOS with a python.org Python, a `CERTIFICATE_VERIFY_FAILED` result means Python has no root certificates: run `Install Certificates.command` or set `SSL_CERT_FILE=/etc/ssl/cert.pem`.

## What has been tested (and what hasn't)

We believe in shipping honest software. Status as of 2026-10-06:

| Area | Status |
|---|---|
| Crawler/user-agent names (OpenAI, Anthropic, Perplexity, Google) | ✅ Verified against official vendor docs, 2026-10-05 |
| Crawler names and user-agent strings for Bing, Apple, Meta, Amazon, Mistral, DuckDuckGo, ByteDance | ⚠️ Added in v0.1.2 from memory of vendor docs; not verified against them. The script reports these rules as `info`, not failures |
| Bing/Copilot guidance (`bing-copilot.md`): AI Performance report, `nocache`/`noarchive`, IndexNow | ⚠️ Compiled from trade coverage on 2026-10-06; not re-verified against Microsoft's documentation |
| "Claude web search runs on Brave" | ⚠️ Reported (Anthropic subprocessor list; observed results match Brave's); not stated by Anthropic as the only source |
| Automated test suite (`python3 -m unittest discover -s tests`, stdlib only, about 2 seconds) | ✅ 131 tests: both scripts, the robots matcher, the shipped robots template, the workflow's exit-code pipeline, the skill build. Every v0.1.2 fix has a regression test, and those tests fail against v0.1.1 |
| Both scripts: happy path + malformed/empty input + mock-site behavior | ✅ Tested |
| Per-agent rendering comparison and soft-404 checks in `check_ai_readiness.py` | ✅ Tested on a local mock site that routes by user agent (broken and fixed). ✅ Run once against two live sites in v0.1.2 (example.com, garagelabstech.com), which surfaced a false "Organization schema missing" warning for `EducationalOrganization` (fixed). ❌ Not yet tested on third-party stacks (WordPress, Next.js, Shopify) |
| Full audit on a real brand (garagelabstech.com, plausible.io) | ✅ Run end-to-end |
| Refusal of manipulative tactics (fake reviews, hidden AI-directed text) | ✅ Tested with fresh agents |
| Head-to-head vs. Claude without the skill | ✅ Run once (see below) |
| New evals 6-11 (Bing/Copilot, snippet controls, robots groups, Brave, tracker, India/Japan) | ❌ Written, with checkable assertions, but not yet run against an agent |
| Per-engine behavioral claims (what each engine rewards) | ⚠️ Practitioner reports, hedged in the text — not controlled studies |
| Trigger reliability from natural phrasing | ❌ Not yet tested |
| Multi-month outcome data (does following the plan move citations?) | ❌ Not yet — run your own baseline and re-test monthly |

**Head-to-head result (one run, honestly reported):** on the same brand-visibility task, Claude *without* the skill produced a solid directional report. The skill's edge was process, not magic: a frozen, reproducible prompt set; an inaccuracy log that caught conflicting pricing claims across the web; explicit verified-vs-unverified labeling; a measurement plan with control pages; and ready-to-ship assets (robots.txt, schema, fact sheet). If you want a one-off opinion, any good model will do. If you want a repeatable program you can re-run monthly and defend to a client, that is what this skill adds.

## Engine and crawler coverage

| Surface | Playbook | Crawler / robots checks | Tracker | First-party data |
|---|---|---|---|---|
| ChatGPT | ✅ | ✅ OAI-SearchBot, ChatGPT-User, GPTBot | ✅ | — |
| Microsoft Copilot / Bing | ✅ [`bing-copilot.md`](geo-visibility/references/bing-copilot.md) | ✅ Bingbot: robots, WAF, Googlebot-vs-Bingbot parity, verification hint, IndexNow | ✅ | Bing Webmaster Tools AI Performance report |
| Claude | ✅ plus a Brave index note | ✅ Claude-SearchBot, Claude-User, ClaudeBot | ✅ | — |
| Gemini / Google AI Overviews | ✅ | ✅ Googlebot, Google-Extended; snippet controls | ✅ | Search Console |
| Perplexity | ✅ | ✅ PerplexityBot, Perplexity-User | ✅ | — |
| Meta AI, Apple, Amazon, Mistral, DuckDuckGo | ⚠️ checklist only | ⚠️ robots rows reported as `info` | add by name | — |
| Brave, Grok, DeepSeek, Baidu, Naver, Yandex | ⚠️ pointers only | ❌ | add by name | — |

## What this skill will not do

- Promise rankings or citations. AI answers vary by run, user, location and model version.
- Fabricate reviews, statistics or testimonials.
- Write hidden text or prompt-injection content aimed at AI crawlers.
- Undisclosed astroturfing or Wikipedia self-editing.

These refusals are part of the skill's instructions and have been tested.

## Repo layout

```
geo-visibility/
├── SKILL.md                  # entry point: workflow, rules, quick answers
├── references/               # 10 playbooks (engines, Bing/Copilot, prompts, technical,
│                             #   content, off-site, SEO, verticals, measurement, evidence)
├── scripts/                  # readiness checker + tracker roll-up (stdlib only)
├── assets/                   # robots.txt, llms.txt, JSON-LD templates,
│                             #   tracker CSV, report template
└── evals/                    # test prompts with expected outputs and assertions
tests/                        # stdlib unittest suite for the scripts and templates
tools/build_skill.py          # builds dist/geo-visibility.skill
```

## Roadmap

- **v0.2** — trigger-reliability testing; outcome data from real monthly re-tests; run evals 6-11 against an agent; verify the Bing, Apple, Meta and Amazon crawler details against vendor docs; optional API runners for prompt sets (OpenAI web search, Perplexity Sonar, Gemini grounding)
- **v0.3** — multi-language prompt-audit templates (starting with Hindi/Hinglish); more vertical playbooks from community PRs
- **Ongoing** — crawler and engine-behavior updates as vendors change (open an [engine-update issue](.github/ISSUE_TEMPLATE/engine-update.md) when you spot one)

If this repo saved you time, a ⭐ helps other people find it — which is, fittingly, exactly how GEO works.

## Contributing

PRs welcome — especially engine-behavior updates with sources, new vertical playbooks, and tracker results from real audits. See [CONTRIBUTING.md](CONTRIBUTING.md); run `python3 -m unittest discover -s tests` before opening one. Crawler names and engine behavior change fast; if you spot something stale, open an issue with a link to the vendor doc.

## License

[MIT](LICENSE) © 2026 Garage Labs Technologies — use it, fork it, build on it. Attribution appreciated but the license only requires keeping the copyright notice.
