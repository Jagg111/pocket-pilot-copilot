---
id: SPEC-our-airports-panel-poc
companions:
  - ../../../docs/pocket-pilots-api-notes.md   # adopted: endpoint shapes, cache lifetimes, polling guidance
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Our-Airports Panel (POC)

## Why

A vision and opportunity: our small company in Pocket Pilots sees mostly us-vs-us stats, so it can't tell which of its held airports a rival is about to take. A quick proof of concept proves that public data alone (`/api/air/co<id>` plus `/api/standings`) yields the one view pilots need to defend: every airport we hold, how safe each lead is, thinnest first. It is the first Must slice of a Discord copilot bot.

## Capabilities

- **CAP-1**
  - **intent:** The system lists every airport our company currently holds.
  - **success:** Against the live game, the listed count equals the in-game "Airports held" figure (54 in the sample) and every code appears in `/api/air/co<id>` `held`.
- **CAP-2**
  - **intent:** For each held airport the system shows the holder, holder value, runner-up, and margin to the runner-up.
  - **success:** For a sampled airport, margin equals `list[0].value - list[1].value` from `/api/standings` and matches the in-game "2nd is $X behind" or "need $X more" figure.
- **CAP-3**
  - **intent:** The panel orders airports by risk: lost, urgent (margin under $10,000) and at-risk (under $20,000) airports first, highest dollar value first, then the rest thinnest lead first; only the top 20 airports by value are monitored.
  - **success:** Given fixture standings, needs-attention airports are ordered by descending value, then the remainder by ascending margin; an airport where we are no longer first is flagged lost and listed above all held ones; an airport with no competitor shows our full value as margin and counts as Secure, with no separate status.
- **CAP-4**
  - **intent:** A pilot can view the whole panel as one readable local HTML page with holder name and tag, value, margin, and data age, refreshed on demand.
  - **success:** Opening the page and triggering a refresh renders all rows plus a "data as of" timestamp, using company names from `cos` rather than raw IDs; a refresh issues fresh API calls only when the user requests it.

## Constraints

- Public endpoints only; no sync code, `pt` token, `/api/career` or `/api/here`. Rules out any credentialed data.
- Respect cache lifetimes (`co` 20 s, `standings` 30 s), make requests sequentially (about 1 s apart), back off on 429/5xx, send a descriptive User-Agent. Rules out parallel fan-out and refresh loops faster than cache.
- Company ID comes from config/env; real company and pilot IDs and raw samples stay in git-ignored `docs/private/`, never in the repo.
- The API shows only the present; the POC computes everything from the current fetch and keeps no history.

## Non-goals

- Takeover and thin-margin alerts or any push messaging (airport war feed).
- Departures board, rivals list, weekly recap, `/where`, milestones.
- Snapshot storage or trend history.
- Any credentialed endpoint, treasury, earnings, or per-pilot data.
- Individual pilot live locations.
- Alert thresholds, polling schedules by risk, background caching or auto-refresh, hosting beyond localhost, production hardening.

## Success signal

Running the POC against the live game shows all our held airports sorted by margin, and a pilot can name the single most at-risk airport and the dollars needed to secure it, matching what the in-game airport screen reports.

## Assumptions

- Airports in the `co` feed's `held` are ours; the standings holder is re-checked in case it flipped between calls.
- Risk means dollar margin to the runner-up only; uncontested airports sort last.
- A refresh takes about a minute (about 54 sequential standings calls); acceptable because refresh is on demand.
