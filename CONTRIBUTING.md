# Contributing

Thanks for helping keep this skill sharp. The fastest-decaying parts are crawler names and engine behavior, so contributions there matter most.

## What we want

- **Engine updates with sources.** If OpenAI, Anthropic, Perplexity, Google or Microsoft change a crawler, an index dependency or citation behavior, open a PR against `references/engine-playbooks.md` or `references/technical-readiness.md` with a link to the vendor doc and the date you verified it.
- **Real audit results.** Anonymized tracker CSVs and what moved (or didn't) after changes. These turn hedged claims into evidence.
- **New vertical playbooks** for `references/verticals.md` (e.g. healthcare, real estate, D2C in specific markets).
- **Script fixes** — both scripts are standard-library-only on purpose and must stay Python 3.8-compatible; keep them that way.
- **Translations** of the prompt-audit templates for non-English markets.

## What we'll reject

- Manipulation tactics: fake reviews, hidden text for AI crawlers, undisclosed astroturfing, sockpuppets. The skill refuses these by design and that is not negotiable.
- Unsourced claims of the form "engine X rewards Y" — practitioner experience is welcome, but label it as such and say how you tested.
- Specific numeric promises ("+40% citations").

## How

1. Fork, branch, edit.
2. If you change the skill's `description` in `geo-visibility/SKILL.md` (it decides when the skill loads), re-run the simulated activation test and record the result: `python3 tools/trigger_sim.py prepare --competitors <clone of a rival plugin> --out <dir>`, give each job file in `<dir>/jobs` to a fresh model, then `python3 tools/trigger_sim.py score --out <dir>`. Tune using the `dev` prompts only; `test` is the held-out half (see `geo-visibility/evals/results-triggers-2026-10-09.md`).
3. If you touch a script, template or reference map, run the suite: `python3 -m unittest discover -s tests` (standard library only; `pip install pyyaml` adds the workflow-syntax test). Add a regression test for every bug you fix, and prove it fails on the old code. Tests run against a local mock site, so they need no network.
4. If you touch `SKILL.md`, keep it under ~500 lines and keep the reference map accurate.
5. Note in your PR what you verified and on what date.

## Building on this

You do not need permission to build on this project. MIT lets you use, modify and redistribute it, including inside a commercial product or service, as long as you keep the copyright and license notice. Attribution is appreciated, and telling us what you built is welcome but never required. If you change the behavior, please do not present our test results or verification dates as yours: they describe this repository's code, not a fork's.

## Releasing

A release moves four things together, and tests fail if they drift:

1. In `CHANGELOG.md`, rename the `Unreleased` heading to `## vX.Y.Z — date`.
2. Set `version` in `.claude-plugin/plugin.json` to `X.Y.Z`. Setting a version pins plugin users until it changes, so forgetting this means nobody receives the release.
3. Run `claude plugin validate --strict .` and `claude plugin validate --strict .claude-plugin/plugin.json` (a clean run prints `Validation passed`), then `python3 -m unittest discover -s tests`.
4. Build `python3 tools/build_skill.py`, publish a GitHub release tagged `vX.Y.Z` with `dist/geo-visibility.skill` attached, and use the changelog entry as the notes.

## Evidence standards

The skill grades claims into high / medium / low confidence (`references/evidence-and-claims.md`). PRs that move a claim up a tier need a source: a vendor doc, a controlled test, or a replicated study. PRs that move a claim down just need a good argument.
