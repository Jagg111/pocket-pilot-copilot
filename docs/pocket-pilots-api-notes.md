# Pocket Pilots: API Notes

Tested 2026-11-06 against `https://pilots.nimblebit.com` (build 130 on the first pass, build 132 for everything else, channel `prod`).
The game's developer said in the game's Discord that there is rate limiting and to "just don't go crazy". There is no official documentation. Everything below was observed from the game's own client code, direct requests, and the network traffic of the game running in a browser, so endpoints may change without notice.

**Project decision (2026-11-06): public data only.** The bot uses endpoints that need no credentials. The credentialed endpoints (`/api/career`, `/api/here`) are documented only to record what sits behind them. See [Credentialed endpoints](#credentialed-endpoints-out-of-scope).

## Contents
1. [Your pilot](#your-pilot)
2. [Auth: what needs a secret](#auth-what-needs-a-secret)
3. [Public endpoints at a glance](#public-endpoints-at-a-glance)
4. [Public endpoint reference](#public-endpoint-reference)
5. [What we can derive](#what-we-can-derive)
6. [Game rules seen on screen](#game-rules-seen-on-screen)
7. [Credentialed endpoints (out of scope)](#credentialed-endpoints-out-of-scope)
8. [Open questions](#open-questions)
9. [Single-call test results](#single-call-test-results-no-credentials)
10. [Not called, and why](#not-called-and-why)
11. [Polling guidance](#polling-guidance-for-a-bot)
12. [How these notes were produced](#how-these-notes-were-produced)

## Your pilot

| Field | Value |
|---|---|
| Pilot ID (`pid`) | `<PILOT_ID>` |
| Callsign | `<CALLSIGN>` |
| Company ID (`co`) | `<COMPANY_ID>` (`<COMPANY_NAME>`, tag `<TAG>`) |

Confirmed against the public feed: `/api/air/{cell}` lists this pilot's active flight (`<REG>`, `<AIRCRAFT_TYPE>`, `<ORIGIN>` to `<DEST>`). The same flight can appear in more than one grid cell, so dedupe by `pid`.

The real values are kept in a local-only, git-ignored file (`docs/private/pilot-identifiers.md`) and are not part of this repo. Raw sample payloads containing real callsigns and IDs are in the git-ignored `docs/private/samples/`.

## Auth: what needs a secret

- The client sends every request with `credentials: 'omit'`. There are no cookies and no session tokens.
- **Public data endpoints need nothing at all.** That includes the airport leaderboards (`/api/standings`) and per-company feeds (`/api/air/co<id>`), which look account-like but are public.
- Account endpoints are keyed by secrets sent in the request:
  - `/api/career`: a 16-character **sync code** (`acct`) in the POST body. The client code uses `op: get`, `new`, `erase` and gameplay write ops with the same code. Treat the sync code as a password. It can also erase the career, and there is no known way to rotate it.
  - `/api/here`: a `code` plus a `pt` token in the **URL query string**. Keep these URLs out of logs.
  - `/api/pos`, `/api/postcard`: `pt` token in the POST body.
  - `/_f/pay/entitlements`: `x-flash-account` header.
- Never put secrets in logs, screenshots or Discord messages.
- **Caution when reading network logs:** the browser tool redacts any query parameter named `code`, even when it is not a secret. In `/api/standings` the `code` is an airport code. Test an endpoint without the parameter's value before assuming it is a secret.

## Public endpoints at a glance

Everything here was called with no credentials and returned 200.

| Endpoint | What it gives | Cache | Typical size | Calls needed |
|---|---|---|---|---|
| `/api/world?v=2` | Event standings, top-15 company table, bases, community projects, **company directory** (name, tag, paint), world counters | 20 s | ~16-54 KB | 1 |
| `/api/air/{cell}` | All flights, recent landings, and held airports in one 10-degree grid cell | 20 s | ~25-120 KB | per cell |
| `/api/air/co<COMPANY_ID>` | **One company's** flights, **all held airports with values**, recent landings, world-wide | 20 s | ~2 KB | 1 per company |
| `/api/standings?code=<ICAO>` | **Full airport leaderboard**: every company's dollar value, sorted, with names | 30 s | ~0.4 KB | 1 per airport |
| `/api/tables?region=<COUNTRY>` | Top-25 company table (country code, or `world`), weekly dollars | 60 s | ~1.3 KB | 1 per region |
| `/api/find/{callsign}` | One pilot's current flight and recent landings | 20 s | ~0.5 KB | 1 per lookup |
| `/api/filed/{pilotId}` | Track plus flight-plan snapshot (ATC center, phase, mode) | none | ~50 KB | 1 per flight, use sparingly |
| `/api/track/{pilotId}` | A flight's **entire planned path** (position and altitude over time) | 30 s | ~14 KB | 1 per flight |
| `/api/wx/{cell}` | Weather stations (METAR-style) | 120 s | ~1-5 KB | per cell |
| `/api/patrons` | Landmark patrons | 30 s | ~1-4 KB | 1 |
| `/api/flying` | Count of flying pilots | 30 s | 34 B | 1 |
| `/_f/v` | Current build number, channel | none | ~80 B | 1 (detects game updates) |
| `/api/changelog` | Build history | 300 s | ~3-8 KB | 1 |
| `/api/fires`, `/api/winds`, `/api/aurora` | Fire, wind and aurora overlays | 300-600 s | 3-114 KB | 1 each |

## Public endpoint reference

Placeholders such as `<COMPANY_ID>` stand for real values.

### `/api/world?v=2`
- `now`: server time in epoch ms.
- `event`: `{key, id, name, blurb, unit, goal, box[4], ends, units, pilots, top[10], locked, aces[10], mine}`. Sample: "Florida Snowbird Season", unit `passengers`, goal 140,000, 258,333 so far, 444 pilots.
  - `top`: top 10 teams, each as `{id, units}`.
  - `aces`: top 10 pilots, each as `{pid, cs, co, units}`.
  - `mine`: map of pilot ID to units contributed, one entry per participant (444 in the sample).
- `table`: 15 teams as `{id, value}` (overall weekly score).
- `bases`: 62 entries of `{code, lat, lon, co}` (team home bases).
- `projects`: community build projects as `{code, name, lat, lon, kind, need, have, by{teamId:amount}, co, t}` (1 in the second sample, 3 in the first).
- `cos`: company directory keyed by company ID, with `{id, name, tag, paint{body,trim,accent}, livery}` (267 companies).
- `explored`: fraction of the world explored (about 0.48). `up`: pilots currently up (870). `heldN`: held-airport count (8,277). `air`: map of grid cell to active flight count (317 cells).

### `/api/air/{lat}_{lon}` (10-degree grid cells, e.g. `40_-90`)
- `now`: server time.
- `flights[]`: `{pid, cs, type, reg, paint, co?, from{code,name,lat,lon}, to{code,name,lat,lon}, t0, eta, wx[], route[[lat,lon]…], tr, planned{cruise}}` plus optional keys `low`, `lv`, `wing` (see Open questions).
  - `co` is present on only some flights (63 of 83 in the sample). A flight without `co` has no company.
  - `eta` looks like total flight seconds at departure (it equals the track's `end`).
  - `wx` is a flat array of 26 numbers, apparently weather at origin and destination. Not decoded.
  - `route` holds only a few waypoints (2 to 3 in the samples). The full path is in `/api/track`.
- `landed[]`: recent landings as `{pid, cs, type, reg, paint, at{code,name,lat,lon}, t}`. It is a **rolling window** of about 12 to 13 events (about 4 hours in a quiet cell).
- `held`: map of airport code to `{co, v, lat, lon}`. **One entry per airport: the current holder and the holder's dollar value.** It has no runner-up. (Use `/api/standings` for that.) The `40_-90` cell had 496 held airports.
- Which cells have traffic is listed in `/api/world` under `air`.

### `/api/air/co<COMPANY_ID>` (public)
- The path is `/api/air/co` followed by the company ID.
- Same shape as the grid feed, `{now, flights[], held{}, landed[]}`, but scoped to **one company across the whole world**, with no grid cells.
- Sample for our company: 4 flights (one far from the others), **54 held airports**, and 0 landings in the rolling window. The 54 matches the in-game "Airports held · 54" list. The grid feed showed only 26 of them because they spread across cells.
- One call per company replaces scanning grid cells. Rival company IDs come from the `cos` of any standings or tables response.

### `/api/standings?code=<ICAO>` (public)
The `code` is the **airport code** (the response echoes it). The game also sends `co=<company id>`, but it is optional: the response is identical with or without it. Tested without credentials for several airports, all 200.
```json
{"code":"<ICAO>",
 "list":[{"id":"<COMPANY_ID>","value":24600},{"id":"<COMPANY_ID_2>","value":15900}, "... 5 to 6 seen"],
 "cos":{"<COMPANY_ID>":{"id":"...","name":"...","tag":"...","paint":{...},"livery":0}}}
```
- `list` is the airport leaderboard, sorted by dollar value. The first entry is the holder, and its value equals `held[ICAO].v` from the air feeds (confirmed in-game: 61,020 at one of our airports).
- `cos` carries name, tag and paint for every company in the list.
- This is the **runner-up and margin data**. Both numbers the game shows ("2nd is $8,700 behind", "need $8,701 more to take it") are computable from `list`.
- Example from the samples: at one airport we were 2nd, $8,700 behind a leader with $24,600. At another we were 1st with $61,020 against a runner-up with $7,005.

### `/api/tables?region=<COUNTRY>` (public)
```json
{"region":"US","list":[{"id":"<COMPANY_ID>","value":47231380}, "... 25 entries"],
 "cos":{"<COMPANY_ID>":{"id":"...","name":"...","tag":"...","paint":{...},"livery":0}}}
```
- A company table of **weekly value delivered in dollars**, sorted, **capped at 25 entries** (every request tested returned exactly 25).
- **Region values:** `US` and `CA` (country codes) work. `world`, and also no `region` at all, return the **world** table, whose #1 value matches the in-game world table (75.4 M in the sample). The game derives the region from the country of the airport the pilot is at, then shows the first 8 entries.
- The world table here has 25 entries, versus 15 in `/api/world` `table`.
- **The game never shows the player's own rank.** Its client code only slices the first 8 (regional) or 12 (world) rows, and no request carries a company ID. Our company was not in the US top 25 or the world top 25.
- **Regions are ISO country codes only.** The value is uppercased and stripped of non-alphanumerics, so `US-IL` becomes `USIL` and returns an empty list; `us`, `USA` and a numeric code return an empty list or fall back to the world table. `IL` (Israel) returns a short list (8 companies), so small countries show their whole table. **No state, city or DMA level exists.** The client only derives a country code from the airport's country.
- **No pagination.** Ten variants (`limit`, `n`, `count`, `offset`, `page`, `start`, `skip`, `top`, `all`, `size`) all returned the identical 25 rows. The cap appears fixed on the server.

### Estimating a company's table rank below the top 25 (no endpoint gives it)
Table value is not a sum of held-airport values. Calibration against `/api/air/co<id>` (sum of `held[].v`), same day:

| Company | Table value | Airports held | Sum of held `v` | Table / sum |
|---|---|---|---|---|
| World #1 | 75.4 M | 348 | 59.9 M | 1.26 |
| World #25 | 11.8 M | 58 | 3.8 M | 3.16 |
| US #25 | 4.8 M | 25 | 1.0 M | 4.62 |
| Ours | not in any top 25 | 54 | 0.42 M | unknown |

The ratio is not constant (1.26 to 4.62), because companies also earn value at airports they do not hold. So the sum of held `v` is only a rough proxy: it says we are well below the 25th company, but it cannot give an exact rank or reliably order companies close to us. Building a proxy table would take about one `/api/air/co<id>` call per company in `world.cos` (267 companies), once, then slow refreshes.

### More public endpoints found in the game's client code (tested 2026-11-06)
These appear in the game's JavaScript. Each was called once without credentials.

- **`/api/find/{callsign}`** (200, `max-age=20`, ~0.5 KB): look up a pilot by callsign. Returns `{now, flights[], landed[]}` in the same shape as the air feed (flights have `pid`, `co`, `from`, `to`, `eta`, and so on). Useful for a "where is <pilot>?" command. Callsign case handling not tested.
- **`/api/filed/{pilotId}`** (200, `no-store`, ~50 KB): the same `t0`, `trk`, `end`, `rev`, `rw` as `/api/track` (identical values in the test), **plus a `key` string** holding a JSON snapshot of the flight. Seen inside `key`: `f` (aircraft state at the snapshot: lat/lon, altitude, heading, speed, throttle, fuel, gear, autopilot), `plan` (departure and arrival airport with runway, elevation and length; `cruise`; `phase` such as "Cruise"; `mode` such as "SPD 116 · DCT · ALT 6,500 ft"; `toGo`; and **`atc`, which names the real ATC center the flight is with**, for example "Minneapolis Center"), `log`, and `ap` (an approach path). Heavy and not cacheable, so use sparingly. This is the likely source of the in-game ATC radio calls.
- **`/api/patrons/{landmark}`** (200, `max-age=30`): history of who has held a landmark patronage: `{log:[{n (callsign), pid, paid, t, to?}]}`, newest first. The plain `/api/patrons` gives only the current holder.
- **`/api/top/{x}?pid=<pilotId>`** (404 `{"error":"no such plane"}` for an airport code): the client reads `seats` from the result, so `{x}` is probably a plane (registration) identifier, not an airport. Not decoded.
- **`/api/seed/{kind}/{n}`**: `kind` is `board` or `shop` and `n` is the current time divided by a period (a day for `shop`). It looks like a shared random seed for job boards and the shop. Not called.
- **`/api/invites?code=<code>`**: invite-code check at sign-up. Skip.

### `/api/track/{pilotId}`
- The id is a **pilot ID** taken from the feed (any flight's `pid`), not necessarily the signed-in pilot.
- `t0`: start time in epoch ms, **identical to the flight's `t0`** in the air feed. `end`: total flight time in seconds (equals the flight's `eta` at departure). `rev`: revision timestamp. `rw`: bookkeeping, not decoded.
- `trk`: flat array of 4-number ticks, `[seconds_since_t0, lat, lon, altitude_m]`. Tick spacing is 2 to 10 seconds (average about 8.7). A 3-hour flight had about 1,340 to 1,465 ticks.
  - **The 4th number is altitude in metres, not heading.** It runs from the origin airport's elevation (about 191) to about 1,983 in cruise, matching `planned.cruise` of 1981 (about 6,500 ft).
- **The track is the entire planned flight**, from takeoff to the destination, not a trail of past positions. A plane's position at any moment is `(now - t0)/1000` seconds into the track, interpolated between ticks. One call per flight is enough.
- The game appends `?r=<rev>` when it polls.

### `/api/wx/{lat}_{lon}`
`{t, st[]}` where each station has 13 keys: `id, lat, lon, e (elevation), w[dir,speed,gust], v, t (temp), d (dewpoint), q (pressure), c[[cover,height,type]], x, r (raw METAR), o (observed time)`. 28 stations in one sample.

### `/api/patrons`
`{p: {<landmark name>: {n (callsign), pid, paid, t}}}`. 12 landmarks in the sample.

### Others
- `/api/flying`: `{flying: number, now: number}`.
- `/api/fires`: array of `{id, lat, lon, hdg, n, t}` (about 1,400 to 1,500 entries).
- `/api/changelog`: `{b: [{n (build), at (date), items[]}]}` (40 entries, latest build 132, 2026-11-06).
- `/api/aurora`, `/api/winds`: base64+zlib grids (`z`) with metadata (`obs`/`run`, `fh`, `w`, `h`).
- `/api/ghsl/dir`: index for building-density tiles. `/api/ghsl/{n}`: zlib-compressed tile (starts `78 9c`).
- `/api/invites`: `{open: boolean}`.
- `/_f/v`: `{build, number, channel, min}`. Useful to detect game updates (number 132, channel `prod`).
- `/_f/pay/products`: 7 products as `{id, name, description, price, min, max, currency, unlocks[], kind}`.
- `/_f/push/key`: web-push public key. `/_f/auth/providers`: `{providers: [apple, google, steam], mock, googleClientId}`. `/_f/apps`: `[]`.
- Static data (`/air/osm/{ICAO}.json`, `/bld/*.json`, `/marina/*.json`, `/sea/ports.json`, `/air|city|road|bld|marina/index.json`, `/_pub/pack/*.bin`): airport, building and terrain geometry. Cached for a year, so download once and keep locally. `/air/osm/{ICAO}.json` is `{v, t, a, b}`. `/marina/{cell}.json` is `{m, p}`.

## What we can derive

These are computed from the public endpoints, not served directly.

| Derived fact | How | Notes |
|---|---|---|
| **Takeover event** | Compare consecutive snapshots of `held[].co` (or each airport's `list[0]`) | Seen live: one airport changed holder within 7.5 minutes and its value changed from 7,745 to 10,720. The API never pushes events, so detection is after the fact, within the polling interval. |
| **Margin at an airport** | `list[0].value - list[1].value`, or our value against the leader's | The game shows the same figures. |
| **Thin-margin / at-risk airports** | Margin from `/api/standings` across the airports we hold | Needs a polling plan (see below). |
| **Our rivals** | Companies whose held airports sit near ours (about 0.5 degrees), or who appear in the same airports' `list` | In the sample, about 10 companies had airports beside ours. |
| **Company size / peer ranking** | Airports held per company and the sum of `v`, from `/api/air/co<id>` | The game exposes no company size or full rank. In one cell our company ranked 5th of 70 by airports held but 11th by summed value, so the metric matters. |
| **A plane's current position** | Interpolate `/api/track` using `(now - t0)` | No position polling needed. |
| **Departures board** | `/api/air/co<id>` `flights[]` joined with `/api/track` | Filter to our company. A flight without `co` has no company. |
| **Landing and first-visit events** | `landed[]` rolling window, stored by us | The window is only a few hours, so we must keep our own history. |
| **History and trends** | Store our own snapshots | The API shows only the present. History is the one thing the bot can add. |

## Game rules seen on screen

From the game's own panels (screen text, not API fields):
- An airport's standing is "value delivered here: **this week plus half of last**". Nothing goes back to zero on Monday: this week's value is added to half of last week's. The panel counts down to the new week (for example "new week in 2d 3h").
- The leader holds the airport from a **$2,000** minimum and takes **5% of other pilots' jobs** from or to it.
- The company table ranks companies by value delivered, and each pilot counts for up to **$250k an airport a week**.
- **Allies** pay no service fees at each other's airports. A company can have up to 3.
- The World screen shows "the sky right now" (flights up, airports held, bases, building projects), which match `up`, `heldN`, `bases` and `projects` from `/api/world`.

## Credentialed endpoints (out of scope)

Documented from the game's own traffic. Not called by us. The project uses public data only.

### `POST /api/career`
Returned the full account blob. Top-level keys seen: `career{pid, callsign, money, home, at, plane, fleet[], stats{flights, landings, hours, nm, earned, jobs, byKind…}, licenses[], visited{}, awards{}, sights[], co, rep{}, regs{}, flown[], jumps, checkin, finds, liveries, club, clubNext, duty[], explored, terms, licH, licJ}`, `trip{reg, type, from, dest, job, t0, id, route, planned, wx}` (the active job), and `company{id, name, tag, paint, livery, members{pid: {cs, rank, joined, jobs, earned, seen, at, gave, brought…}}, treasury, code, fleet[]}`. The company object includes an invite-style code, deliberately not recorded here. The output seen was truncated, so there may be more keys.

**Everything on the in-game company screen comes from this call:** treasury and bank balance, jobs flown, total earned, the "Lately" activity log (who put money in, bought a plane, was promoted or joined, and "taken by <pilot>" lines), the pilot roster, fleet, and bases. Opening the Company, Ledger, Pilots, Fleet, Bases and Airports tabs made **no further network calls**.

What a public-data bot **cannot** see because of this: the company's money, per-pilot earnings, who did what in the company, purchases and promotions.

### `GET /api/here?code=…&co=…&pid=…&cs=…&pt=…&lat=…&lon=…`
The **airport panel** for the airport at `lat`/`lon`. Response shape:
```json
{"level":3,"pts":379,"built":{},"project":null,"holder":"<COMPANY_ID>",
 "standings":[{"id":"<COMPANY_ID>","value":693940}, "... top 5"],
 "bases":["<COMPANY_ID>"],
 "cos":{"<COMPANY_ID>":{"id":"...","name":"...","tag":"...","paint":{...},"livery":0}},
 "seats":{"<ICAO>-<n>-G2":3},"contracts":[],"legs":[],
 "parked":[{"pid":"...","cs":"...","reg":"...","type":"...","paint":"...","lv":121,"cl":"<COMPANY_ID>","t":1793109584175}],
 "aurora":0}
```
- `standings` duplicates what `/api/standings` serves publicly.
- Only behind credentials: `level`, `pts`, `seats` (job slots), `parked` aircraft (callsign, plane, owner, last seen), `contracts`, `legs`, `built`.
- Tested twice without `code`/`pt` (including KMDW's exact coordinates): HTTP 200 but an empty shell (`level` 0, `standings` `[]`, `holder` `null`).
- The game calls it repeatedly with the origin's and destination's coordinates while a flight is active.

### Risk of using a personal sync code (decision: not doing this for now)
The code is the account: it reads the career and also erases it or performs write ops, and cannot be reset. Main risks: an accidental erase or write from a bug, leaking the code (repo, logs, Discord), exposing company finances in a shared channel, and drawing attention to the account as the API is unofficial. If this is ever reconsidered: local git-ignored file, a read-only wrapper that sends only `op: get`, run locally, slow polling, post aggregates only, log redacted URLs, and ask the developer first.

## Open questions

- **What changes `held[].v` between takeovers?** Over 7.5 minutes only one airport changed, at a takeover. Whether `v` also grows with landings or only moves at takeovers is unknown. It follows the weekly rule above (this week plus half of last), so it probably changes with deliveries. Needs a longer snapshot series (hours, across a Monday rollover).
- **What do the optional flight keys `low`, `lv` and `wing` mean?** `wing` most likely marks a wingman or formation flight (the flight carrying it flew the same route, about 100 seconds behind a company mate). Not confirmed. `lv` also appears on parked aircraft in the credentialed panel.
- **Beyond the top 25:** no region, state or pagination option found. A table position below 25th is only estimable (see the proxy section). Untried: authenticated variants, and whether the cap differs by country.
- **`/api/standings` for airports with no contest:** how many entries it can return, and what it returns for an airport nobody holds.
- **Polling cost:** one `/api/standings` call per airport. Our company alone holds about 54 airports. Polling all of them every 30 seconds is too much for the "don't go crazy" request, so we need a plan: check only airports where the gap is small, spread calls over time, and respect cache lifetimes.
- **Company size:** not exposed. Airports held and summed value are the best public proxies.
- **How many requests the server will tolerate:** the developer gave no number. Back off at the first 429.

## Single-call test results (no credentials)

First pass, build 130. One GET per endpoint, `credentials: 'omit'`. Time is for that single request.

| Endpoint | Status | Time | Size | Cache-Control | Cached at edge |
|---|---|---|---|---|---|
| `/api/world?v=2` | 200 | 62 ms | 53,557 B | public, max-age=20 | yes |
| `/api/flying` | 200 | 324 ms | 34 B | public, max-age=30 | no |
| `/api/air/40_-90` | 200 | 67 ms | 85,976 B | public, max-age=20 | yes |
| `/api/air/30_-90` | 200 | 63 ms | 119,839 B | public, max-age=20 | yes |
| `/api/track/{pilotId}` | 200 | 141 ms | 14,837 B | public, max-age=30 | no |
| `/api/wx/42_-93` | 200 | 57 ms | 5,246 B | public, max-age=120 | yes |
| `/api/aurora` | 200 | 116 ms | 2,795 B | public, max-age=300 | no |
| `/api/changelog` | 200 | 114 ms | 8,410 B | public, max-age=300 | no |
| `/api/fires` | 200 | 67 ms | 114,001 B | public, max-age=600 | yes |
| `/api/winds` | 200 | 65 ms | 74,947 B | public, max-age=600 | yes |
| `/api/patrons` | 200 | 66 ms | 3,589 B | public, max-age=30 | yes |
| `/api/ghsl/dir` | 200 | 83 ms | 143 B | public, max-age=86400 | yes |
| `/api/ghsl/23317` | 200 | 106 ms | 71,788 B | immutable, 1 year | yes |
| `/api/invites` | 200 | 70 ms | 13 B | public, max-age=60 | yes |
| `/_f/v` | 200 | 58 ms | 67 B | no-store | no |
| `/_f/apps` | 200 | 59 ms | 2 B | public, max-age=600 | no |
| `/_f/pay/products` | 200 | 93 ms | 1,405 B | no-store | no |
| `/_f/push/key` | 200 | 183 ms | 97 B | no-store | no |
| `/_f/auth/providers` | 200 | 138 ms | 145 B | no-store | no |
| `/air/index.json` | 200 | 93 ms | 8,743 B | s-maxage 1 year | yes |
| `/city/index.json` | 200 | 66 ms | 6,046 B | s-maxage 1 year | yes |
| `/road/index.json` | 200 | 58 ms | 7,785 B | s-maxage 1 year | yes |
| `/air/osm/KMDW.json` | 200 | 66 ms | 25,255 B | s-maxage 1 year | yes |
| `/bld/chicago.json` | 200 | 98 ms | 811,774 B | s-maxage 1 year | yes |
| `/marina/41_-88.json` | 200 | 60 ms | 69,538 B | s-maxage 1 year | yes |
| `/_pub/pack/cov/8/16/23.bin` | 200 | 92 ms | 398,168 B | immutable, 1 year | yes |
| `/_pub/pack/wat/8/16/24.bin` | 200 | 81 ms | 127,676 B | immutable, 1 year | yes |

Added later, build 132, also with no credentials: `/api/standings?code=<ICAO>` (200, 421 B, max-age=30), `/api/air/co<id>` (200, 1,722 B, max-age=20), `/api/tables?region=US` (200, 1,277 B, max-age=60).

JSON responses are zstd-compressed. Sizes above are decoded bytes.

## Not called, and why

| Endpoint | Reason |
|---|---|
| `/api/career` | Needs the sync code. Also supports `erase`. Only the game's own call was observed. |
| `/api/here` | Needs company code and `pt` token in the URL. Called only without credentials, which returns an empty shell. |
| `/api/pos` | Writes the pilot's position |
| `/api/postcard`, `/api/postcard/{id}` | Writes or needs an id from a posted card |
| `/_f/move`, `/_f/move/{code}`, `/_f/save/link` | Save transfer and linking |
| `/_f/pay/checkout`, `/claim`, `/native`, `/entitlements` | Purchases |
| `/_f/push/subscribe`, `/unsubscribe`, `/schedule`, `/cancel`, `/link` | Writes |
| `/_f/auth/start`, `/claim`, `/native` | Login flow |
| `/_f/e` | Analytics beacon |
| `/api/seed/{n}` | Purpose of `n` unknown; did not guess |

## Polling guidance for a bot
- Match the cache lifetimes. Polling faster than `max-age` returns the same cached response:
  - `/api/world`, `/api/air/{cell}`, `/api/air/co<id>`: every 20 seconds
  - `/api/standings`: every 30 seconds
  - `/api/flying`, `/api/patrons`, `/api/track`: every 30 seconds
  - `/api/tables`: every 60 seconds
  - `/api/wx`: every 2 minutes
  - `/api/aurora` and `/api/changelog`: every 5 minutes
  - `/api/fires` and `/api/winds`: every 10 minutes
- **Prefer the small endpoints.** `/api/air/co<id>` is about 2 KB per company, while a grid cell can be 25 to 120 KB. Use grid cells only to discover unknown companies.
- **Budget standings calls.** Take the airport list from `/api/air/co<id>` (one call), then poll `/api/standings` more often for airports where the gap to first or second is small, and rarely for the rest.
- Have one poller share its cache across all bot commands.
- Back off on 429 or 5xx responses.
- Use a descriptive User-Agent with a way to contact you.
- Don't post individual players' live locations without opt-in.
- Download static geometry once and keep it locally.

## How these notes were produced

- **Pass 1 (build 130):** one GET per public endpoint, shapes recorded from the responses and the game's client code.
- **Pass 2 (build 132):** one GET per public endpoint again, plus one `/api/track` call and repeated `/api/air/40_-90` snapshots over about 7.5 minutes to look for change.
- **Pass 3:** tests with our own pilot and company IDs against public endpoints.
- **Pass 4 (browser):** the user signed in themselves in the in-app browser. Only endpoint paths, query keys and the `/api/here`, `/api/standings` response bodies were read. The `/api/career` response body and all request bodies were deliberately not read or recorded. The user then opened panels in the game (map, an airport leaderboard, the company screen and all its tabs, the World leaderboard) while we watched which endpoints loaded, and each new endpoint was then tested directly with no credentials.
- Request etiquette throughout: sequential single requests, about one second apart, descriptive User-Agent, no loops.
