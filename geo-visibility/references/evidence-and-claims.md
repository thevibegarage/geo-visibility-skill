# Evidence and confidence

GEO advice online is full of confident claims from small samples and vendors selling tools. Use this file to calibrate what the skill says and to stay honest with the user.

## Contents
- Confidence tiers
- Claims to treat carefully
- How to run a real test
- Wording rules for client-facing output

## Confidence tiers
**High (mechanism is clear or consistently replicated)**
- Blocked or unrenderable content cannot be retrieved or cited.
- Engines with live search depend on the web indexes they use; being absent from them removes you from retrieval.
- Consistent, specific, corroborated facts across independent sources improve accuracy and inclusion.
- Pages with direct, specific, well-sourced answers are easier to extract than vague marketing copy.
- Wrong third-party information produces wrong AI answers; fixing the source fixes the answer over time.

**Medium (plausible, supported by studies or practitioner testing, but variable)**
- Question-style headings with immediate answers improve passage matching.
- Original data and citations to primary sources increase citation likelihood.
- Freshness matters more on live-search engines and time-sensitive topics.
- Review platforms, listicles and Reddit-type sources carry disproportionate weight for "best X" prompts.
- Schema helps machines parse entities even where direct citation lift is unproven.

**Low (unproven, treat as experiments)**
- llms.txt as a ranking or citation factor.
- Specific numeric lifts ("+40% citations") from blog posts or vendor studies.
- Any claim that one tactic works the same across engines.
- "Prompt injection" style hidden text for AI crawlers: unethical, brittle, and risky; never recommend.

## Claims to treat carefully
- Market-share and usage figures for AI assistants differ widely by source and date; cite the source and date or leave them out.
- Single-vendor datasets (for example "X million citations analyzed") reflect that vendor's prompt sampling. Useful as direction, not as law.
- Statements about which crawler or index an engine uses can be outdated within months; verify in official documentation.
- Averages hide huge category differences. Test in the brand's own category.

## How to run a real test
1. Pick 10-20 target prompts and freeze them; record baseline across engines (3 runs for top prompts).
2. Change one thing per cohort of pages (for example answer-first rewrite on 5 pages, leave 5 similar pages untouched as control).
3. Wait for recrawl (typically weeks for live-search surfaces; much longer for model memory).
4. Re-run the same prompts; compare cited URLs and mention rates between treated and control cohorts.
5. Log the change, date, expected effect, and result in a change log. Keep what works for the brand's category.

## Wording rules for client-facing output
- Say "likely", "tends to", "in our testing" for medium/low items; reserve plain statements for high-confidence items.
- State the date of the audit and that AI answers vary by run, user, location and model version.
- Never promise a position, citation, or timeline. Promise the process, the baseline and the measurement.
- Separate what was verified in this session (fetched pages, run prompts) from what comes from general knowledge.
