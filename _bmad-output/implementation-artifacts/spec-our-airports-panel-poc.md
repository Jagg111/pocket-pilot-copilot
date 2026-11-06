---
title: 'Our-airports panel POC'
type: 'feature'
created: '2026-11-06'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/specs/spec-our-airports-panel-poc/SPEC.md', '{project-root}/docs/pocket-pilots-api-notes.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Our company can't see which held airports a rival is about to take; the game shows mostly us-vs-us stats.

**Approach:** A local, on-demand HTML page (Python stdlib) lists every airport we hold from `/api/air/co<id>`, enriched from `/api/standings?code=` with holder, value, runner-up and margin, sorted thinnest-lead first. Lost airports sort first; uncontested ones show full value as "no competitors (safe)" and sort last. Public data only, polite polling, company ID from env, no history.

</frozen-after-approval>

## Implementation Notes

- Python stdlib only. Files: `panel/core.py` (fetch, backoff, rows, sort), `panel/server.py` (localhost server, refresh on demand), `panel/index.html`, `panel/tests/test_core.py`.
- Run: `PP_COMPANY_ID=<id> [PP_CONTACT=<email>] python panel/server.py`, open http://127.0.0.1:8765/, press Refresh (~1 min).
- Live check: 54 held airports (matches in-game count); margins returned.
- Tests: `python -m unittest discover -s panel/tests` (11 pass).

## Review Triage Log

- medium, patched: no abort on repeated 429/5xx. Now aborts after 3 consecutive failures.
- low, patched: Retry-After negative/NaN. Clamped.
- medium, patched: UI stuck on fetch failure; stale data hid its age. Fixed.
- low, patched: error notes lost HTTP status. Added.
- low, patched: localhost CSRF/DNS rebinding. Host check plus X-Panel header on POST.
- low, patched: test gaps and brittle backoff test. Added tests, real header object.
- rejected: urgency thresholds, change indicator, cancel button (spec non-goals or out of POC scope).
- rejected low: held_codes default owner (feed is company-scoped), sorting standings (documented sorted), progress lock, PP_PORT validation, no-store header, state leak (localhost only).

