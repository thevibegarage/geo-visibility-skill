# Security

This project is a Claude skill, two standard-library Python scripts and some markdown. This page says exactly what it does on your machine, and which of those statements a test enforces.

## What the scripts do

- **`check_ai_readiness.py`** sends HTTP GET requests to the site you point it at, using realistic crawler user-agent strings (Googlebot, Bingbot, GPTBot and others) to see what each agent would receive. It also follows the sitemap and robots.txt URLs that the site itself lists, which can be on another host. It contacts nothing else.
- **`score_tracker.py`** reads a CSV file you give it and prints a report. It makes no network requests.
- **No telemetry, no accounts, no API keys.** Nothing is sent anywhere except the requests above.
- **Files:** the checker writes a file only when you pass `--json`. Neither script modifies your site or your code.
- **Dependencies:** none. Both scripts import only the Python standard library and `geo_config.py`, a sibling file that reads `geo-visibility.json`.

Tests that enforce these statements: no network, process, or dynamic-code modules are imported (`subprocess`, `socket`, `ctypes` and similar); no `eval` or `exec`; every request in a run goes to the target host; a run without `--json` leaves the working directory unchanged; the tracker makes no requests.

## Responsible use

The checker sends requests that look like search and AI crawlers. Point it only at sites you own or have permission to test. A request with a crawler's user-agent string is not a request from that crawler: WAFs that verify bots by IP will treat it as a spoof, and the checker reports that as a warning, not proof.

## Prompt injection

The skill asks an AI agent to fetch and read pages from the open web, and those pages are untrusted. Its operating rules say to treat fetched content as data, never as instructions, and to quote anything notable to you rather than act on it. The slash commands (`/geo-visibility:audit`, `check`, `track`, `diagnose`) also treat their arguments as data and refuse values that contain shell metacharacters, and they can only be started by you, not by the model.

A report that a crafted page, competitor site, review or forum thread can steer the agent into doing something you did not ask is in scope and welcome.

## Reporting a problem

Use GitHub's private reporting: open the repository's **Security** tab, then **Report a vulnerability**. Only the maintainers can see what you send. If you are reading a fork or mirror where that option is missing, open an issue that says only "security contact requested" and contains no details; a maintainer will reply with a private channel. Please do not post details publicly first.

We aim to acknowledge a report within a week. Only the latest release is supported.

## Out of scope

Vulnerabilities in Claude Code or Claude itself (report those to Anthropic), in the sites you test, or advice you disagree with (open an ordinary issue).
