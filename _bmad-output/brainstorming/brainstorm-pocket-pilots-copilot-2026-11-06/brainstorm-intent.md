# Pocket Pilot's Copilot: Brainstorm Intent

Source: brainstorming session of 2026-11-06 (Creative Partner mode). Input for `bmad-spec` or `bmad-product-brief`.
Technical ground truth: [docs/pocket-pilots-api-notes.md](../../../docs/pocket-pilots-api-notes.md).

## The idea
A **Discord bot** for our own company's Discord that turns Pocket Pilots (Nimblebit's browser and phone multiplayer flying game) public data into a shared "us vs. them" game. Our company is a small company in a game whose leaderboards favor the biggest companies. The bot makes the local rivalry visible and gives the company shared things to defend and chase.

## Why
- Weekly goals: maximize company income, hold as many airports as possible, climb the leaderboards.
- The game surfaces mostly **us vs. us** stats (pilots inside the company). We want **us vs. them**.
- Global leaderboards show only the top, so a small company can't see its standing among similar companies.
- Gamers like to compete, and a shared, visible contest gives pilots a reason to log on and fly somewhere specific.

## Hard constraints (decided)
1. **Public data only.** Every feature must come from endpoints that need no credentials. No sync code, no `pt` token, nothing from `/api/career` or `/api/here`. This drops the treasury, money goals, per-pilot earnings, and the company ledger.
2. **Be polite to the API.** The developer said "don't go crazy". Respect cache lifetimes, share one poller, back off on 429 or 5xx, send a descriptive User-Agent.
3. **No individual live locations without opt-in.** Pilot privacy.
4. **Secrets never in the repo or the bot.** Real IDs stay in git-ignored `docs/private/`.

## Scope (MoSCoW, accepted)

**Must: the core**
- **Airport war feed.** Push messages for takeovers ("X just took Joliet") and thin-margin warnings ("Joliet: 2nd is $8,700 behind").
- **Our-airports panel.** Every airport we hold, with holder, value, and margin to the runner-up, sorted by risk.

**Should**
- **Departures board.** Company flights written as ATC radio calls ("Bushmaster 30 Bravo, Milwaukee Center, maintain 6,500"). Position comes from the flight's track, with no position polling.
- **Rivals list.** Companies sharing our airports, ranked against us, built from airport leaderboards.
- **Weekly recap.** Airports gained and lost, biggest margin swings, a post around the Monday rollover.

**Could**
- **`/where`.** "Which airport should I fly toward right now?" from margin and distance.
- **Rally cry with a live countdown.** The Joliet message updating as the lead moves.
- **Milestone shout-outs.** First landing at a new airport, from our own landing history.

**Won't this time**
- Anything credentialed (savings goals, contribution attribution, earnings, ledger events).
- A "similar-size companies" peer table, because company size isn't exposed.

## Form factor (decided)
**Discord bot first.** The Must features are push by nature (alerts, recaps). A web page with the always-open panel and board can follow later, using the same data and history.

## Data toolkit (verified 2026-11-06, all public)
| Need | Endpoint | Cost |
|---|---|---|
| Our airports, flights, landings | `/api/air/co<COMPANY_ID>` | 1 call, 20 s cache |
| Airport leaderboard and margin | `/api/standings?code=<ICAO>` | 1 call per airport, 30 s cache |
| Company names, tags, colours | `cos` in `/api/world`, `/api/standings`, `/api/tables` | free with the above |
| Flight path and position | `/api/track/{pilotId}` | 1 call per flight |
| Regional company table | `/api/tables?region=US` | 1 call, 60 s cache (we are not in the US top 25) |
| Game update detection | `/_f/v` | 1 call |

Key facts:
- `held[].v` is the holder's dollar value at that airport. It equals the first entry of the airport's standings list.
- The API only shows the present, so takeovers are found by **comparing our own snapshots**. The API never pushes events.
- `landed[]` is a rolling window of a few hours, so landing history must be stored by us.
- A track is the entire planned flight; the altitude field is in metres.

## Game rules that shape the features
- Airport standing is "this week plus half of last week". Nothing resets to zero on Monday.
- The leader holds an airport from $2,000 and takes 5% of other pilots' jobs to or from it.
- Company tables count each pilot for up to $250k an airport a week.

## Insights to carry into the spec
1. **Our own snapshot history is the one thing the bot adds that the game doesn't have.** Every Must and Should feature depends on it. The POC should record snapshots from the first day, even before any Discord feature works.
2. **The rivals list can come from airport leaderboards** (who appears next to us at our airports), which sidesteps the missing company-size data.
3. **The weekly rule suggests an end-of-week "last call" push.** This is a hypothesis to test once there is history.

## Open questions for the POC
- What drives `v` between takeovers (deliveries, time, both)? It needs hours of snapshots, ideally across a Monday.
- What is a good polling plan for about 54 airports? Idea: poll `/api/standings` often only where the gap is small, and rarely elsewhere.
- What does `/api/standings` return for airports nobody holds, and how many entries can it return?
- Which other `/api/tables` regions exist?
- Which thresholds make a "thin margin" or "about to flip" alert useful, not noisy?
- What do the optional flight keys `low`, `lv` and `wing` mean?

## Suggested POC slice
1. Poller: `/api/air/co<id>` every 20 s, and `/api/standings` for our airports on a risk-based schedule. Store snapshots (SQLite or JSON files).
2. Detector: takeover and thin-margin events from snapshot diffs.
3. Discord: post those events to one channel through a webhook, with no slash commands yet.
4. Then the our-airports panel as a command, then the departures board.

## Where this goes next in BMad
`bmad-spec` (condense this into SPEC.md) or `bmad-product-brief`, then `bmad-architecture` and the build flow.
