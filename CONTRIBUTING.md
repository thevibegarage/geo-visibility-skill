# Contributing

Thanks for helping keep this skill sharp. The fastest-decaying parts are crawler names and engine behavior, so contributions there matter most.

## What we want

- **Engine updates with sources.** If OpenAI, Anthropic, Perplexity, Google or Microsoft change a crawler, an index dependency or citation behavior, open a PR against `references/engine-playbooks.md` or `references/technical-readiness.md` with a link to the vendor doc and the date you verified it.
- **Real audit results.** Anonymized tracker CSVs and what moved (or didn't) after changes. These turn hedged claims into evidence.
- **New vertical playbooks** for `references/verticals.md` (e.g. healthcare, real estate, D2C in specific markets).
- **Script fixes** — both scripts are standard-library-only on purpose; keep them that way.
- **Translations** of the prompt-audit templates for non-English markets.

## What we'll reject

- Manipulation tactics: fake reviews, hidden text for AI crawlers, undisclosed astroturfing, sockpuppets. The skill refuses these by design and that is not negotiable.
- Unsourced claims of the form "engine X rewards Y" — practitioner experience is welcome, but label it as such and say how you tested.
- Specific numeric promises ("+40% citations").

## How

1. Fork, branch, edit.
2. If you touch a script, run it against good, empty and malformed input (see `assets/visibility-tracker.csv` for the expected header).
3. If you touch `SKILL.md`, keep it under ~500 lines and keep the reference map accurate.
4. Note in your PR what you verified and on what date.

## Evidence standards

The skill grades claims into high / medium / low confidence (`references/evidence-and-claims.md`). PRs that move a claim up a tier need a source: a vendor doc, a controlled test, or a replicated study. PRs that move a claim down just need a good argument.
