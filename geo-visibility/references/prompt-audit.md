# Prompt audit method

The audit turns "are we visible in AI?" into numbers you can track. Build the prompt set once, freeze it, and re-run it monthly.

## Contents
- Building the prompt set
- Prompt templates by funnel stage
- Running the prompts
- Scoring
- Analysis outputs

## Building the prompt set
Aim for 25-50 prompts. Sample how real buyers talk to assistants: longer, conversational, with context ("I run a 20-person agency in Pune and need..."). Cover:

| Stage | Share of set | Purpose |
|---|---|---|
| Category / discovery | 25% | "What is the best X for Y?" Where new buyers first meet brands |
| Comparison / alternatives | 25% | "X vs Y", "alternatives to Z" |
| Problem / how-to | 20% | Informational prompts the brand can answer authoritatively |
| Brand / reputation | 15% | "Is BrandName good?", "BrandName pricing", "BrandName reviews" |
| Local / segment-specific | 10% | City, industry, company-size qualifiers |
| Agentic / transactional | 5% | "Find and book...", "Compare plans and pick one" |

Source prompts from: sales call questions, support tickets, People Also Ask, Search Console queries, Reddit/Quora threads, competitor page headings. Add 2-3 phrasing variants for the top 10 money prompts because small wording changes can change answers.

## Prompt templates
- Category: "What are the best [category] tools for [persona] in [year]? Give me a shortlist with pros and cons."
- Constraint: "I need [category] that [constraint 1] and [constraint 2], budget [range]. What do you recommend?"
- Comparison: "[Brand A] vs [Brand B]: which is better for [use case]?"
- Alternatives: "What are alternatives to [competitor] that are cheaper or simpler?"
- Problem: "How do I [job to be done]? Which tools help?"
- Brand: "What is [Brand]? Who is it for? What does it cost? What do people complain about?"
- Local: "[Category] in [city] that [qualifier]."
- Trust: "Is [Brand] legit? Any red flags?"

## Running the prompts
- Run each prompt fresh (new chat, no memory, logged out or neutral profile where possible) and with web search on, since that is when citations appear. Also run a no-search pass for the top 10 to see model-memory awareness.
- Record the date, engine, model/mode, location, and the full answer plus cited URLs. Answers vary run to run: for the top 10 prompts, run 3 times and use the majority.
- Do not use logged-in personalization for the baseline. Note it if unavoidable.
- If you cannot access an engine, generate the prompt sheet and the tracker for the user to run and paste back.

## Scoring (per prompt, per engine)
- **Mentioned** (0/1): brand named in the answer.
- **Cited** (0/1): brand's own domain linked as a source.
- **Position**: 1 = first recommended, 2 = second, ... blank if absent.
- **Sentiment**: positive / neutral / negative / inaccurate.
- **Accuracy**: are facts about the brand (pricing, features, location) right? Log each error verbatim.
- **Competitors present**: list.
- **Cited sources**: every domain cited, with type (review site, listicle, Reddit, Wikipedia, publisher, brand, video).

Roll up: mention rate, citation rate, average position, share of voice (brand mentions / all brand mentions in the set), per engine and per funnel stage.

## Analysis outputs
1. Share-of-voice table vs. competitors.
2. **Top cited domains** across the set, ranked. This is the off-site target list.
3. Prompts the brand loses where a competitor wins, with the competitor's winning source.
4. Inaccuracy log: wrong facts to fix at the source (usually an outdated third-party page or an unclear brand page).
5. Quick wins vs. structural gaps.
