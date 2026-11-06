# Pocket Pilots: API Notes

Tested 2026-11-06 against `https://pilots.nimblebit.com` (build 130, channel `prod`).
The game's developer said in the game's Discord that there is rate limiting and to "just don't go crazy". There is no official documentation. Everything below was observed from the game's own client code and network traffic, so endpoints may change without notice.

## Your pilot

| Field | Value |
|---|---|
| Pilot ID (`pid`) | `<PILOT_ID>` |
| Callsign | `<CALLSIGN>` |
| Company ID (`co`) | `<COMPANY_ID>` (`<COMPANY_NAME>`, tag `<TAG>`) |

Source: the game's own `POST /api/career` response. Confirmed against the public feed: `/api/air/{cell}` lists this pilot's active flight (`<REG>`, `<AIRCRAFT_TYPE>`, `<ORIGIN>` to `<DEST>`). The same flight can appear in more than one grid cell, so dedupe by `pid`.

The real values are kept in a local-only, git-ignored file (`docs/private/pilot-identifiers.md`) and are not part of this repo.

## How auth works

- The client sends every request with `credentials: 'omit'`. There are no cookies and no session tokens.
- Public data endpoints need nothing at all.
- Account endpoints are keyed by secrets sent in the request:
  - `/api/career`: a 16-character **sync code** (`acct`) in the POST body. The client code uses `op: get`, `new`, `erase` and gameplay write ops with the same code. Treat the sync code as a password. It can also erase the career.
  - `/api/here`: a `code` plus a `pt` token in the **URL query string** (the code looks like the company code). Keep these URLs out of logs.
  - `/api/pos`, `/api/postcard`: `pt` token in the POST body.
  - `/_f/pay/entitlements`: `x-flash-account` header.
- Never put secrets in logs, screenshots or Discord messages.

## Single-call test results (no credentials)

One GET per endpoint, `credentials: 'omit'`. Time is for that single request.

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

JSON responses are zstd-compressed. Sizes above are decoded bytes.

## Response shapes

### `/api/world?v=2`
- `now`: server time in epoch ms.
- `event`: `{key, id, name, blurb, unit, goal, box[4], ends, units, pilots, top[10], locked, aces[10], mine}`
  - `top`: top 10 teams, each as `{id, units}`.
  - `aces`: top 10 pilots, each as `{pid, cs, co, units}`.
  - `mine`: map of pilot ID to units contributed, one entry per participant (440 entries when sampled).
- `table`: 15 teams as `{id, value}` (overall score).
- `bases`: 62 entries of `{code, lat, lon, co}` (team home bases).
- `projects`: 3 community build projects as `{code, name, lat, lon, kind, need, have, by{teamId:amount}, co, t}`.
- `cos`: team directory keyed by team ID, with `{id, name, tag, paint{body,trim,accent}, livery}` (264 teams).
- `explored`: fraction of the world explored (about 0.48), `up`: pilots currently up, `heldN`: held-airport count, `air`: map of grid cell to active flight count (310 cells).

### `/api/flying`
`{flying: number, now: number}`

### `/api/air/{lat}_{lon}` (10-degree grid cells, e.g. `40_-90`)
- `now`: server time.
- `flights[]`: `{pid, cs, type, reg, paint, co?, from{code,name,lat,lon}, to{code,name,lat,lon}, t0, eta, wx[], route[[lat,lon]…], tr, planned{cruise}}`. Some flights carry one extra key that I did not identify.
- `landed[]`: recent landings as `{pid, cs, type, reg, paint, at{code,name,lat,lon}, t}`.
- `held`: map of airport code to `{co, v, lat, lon}` (team-held airports).
- Which cells have traffic is listed in `/api/world` under `air`.

### `/api/track/{pilotId}`
- `t0`: start time in epoch ms. `end`, `rev`, `rw`: bookkeeping fields I did not decode.
- `trk`: flat array of 4-number ticks: `[seconds_since_t0, lat, lon, heading]`, one tick about every 2 seconds. The test call returned 2,108 numbers, about 527 ticks.
- The game appends `?r=<rev>` (the flight's revision timestamp) when it polls.

### `/api/wx/{lat}_{lon}`
`{t, st[]}` where each station has 13 keys: `id, lat, lon, e (elevation), w[dir,speed,gust], v, t (temp), d (dewpoint), q (pressure), c[[cover,height,type]], x, r (raw METAR), o (observed time)`.

### `/api/patrons`
`{p: {<landmark name>: {n (callsign), pid, paid, t}}}`

### Others
- `/api/fires`: array of `{id, lat, lon, hdg, n, t}` (about 1,400 entries).
- `/api/changelog`: `{b: [{n (build), at (date), items[]}]}` (40 entries).
- `/api/aurora`, `/api/winds`: base64+zlib grids (`z`) with metadata (`obs`/`run`, `fh`, `w`, `h`).
- `/api/ghsl/dir`: index for building-density tiles. `/api/ghsl/{n}`: zlib-compressed tile (starts `78 9c`).
- `/api/invites`: `{open: boolean}`.
- `/_f/v`: `{build, number, channel, min}`.
- `/_f/pay/products`: 7 products as `{id, name, description, price, min, max, currency, unlocks[], kind}`.
- `/_f/push/key`: web-push public key. `/_f/auth/providers`: `{providers: [apple, google, steam], mock, googleClientId}`.
- Static data (`/air/osm/{ICAO}.json`, `/bld/*.json`, `/marina/*.json`, `/air|city|road/index.json`, `/_pub/pack/*.bin`): airport, building and terrain geometry. Cached for a year, so download once and keep locally.

## Account endpoints (observed from the game's own traffic, not called by us)

### `POST /api/career` (200 in the game's own call)
Returned the full account blob. Top-level keys seen: `career{pid, callsign, money, home, at, plane, fleet[], stats{flights, landings, hours, nm, earned, jobs, byKind…}, licenses[], visited{}, awards{}, sights[], co, rep{}, regs{}, flown[], jumps, checkin, finds, liveries, club, clubNext, duty[], explored, terms, licH, licJ}`, `trip{reg, type, from, dest, job, t0, id, route, planned, wx}` (the active job), and `company{id, name, tag, paint, livery, members{pid: {cs, rank, joined, jobs, earned, seen, at, gave, brought…}}, treasury, code, fleet[]}`. The company object includes an invite-style code, deliberately not recorded here. The output I saw was truncated, so there may be more keys.

### `GET /api/here` (200 in the game's own call)
Called with `code`, `co`, `pid`, `cs`, `pt`, `lat`, `lon` in the query string. Body not readable from the network log. Looks like a presence ping that returns company-mate status.

## Not called, and why

| Endpoint | Reason |
|---|---|
| `/api/career` | Needs the sync code. Also supports `erase`. Only the game's own call was observed. |
| `/api/here` | Needs company code and `pt` token in the URL |
| `/api/pos` | Writes the pilot's position |
| `/api/postcard`, `/api/postcard/{id}` | Writes or needs an id from a posted card |
| `/_f/move`, `/_f/move/{code}`, `/_f/save/link` | Save transfer and linking |
| `/_f/pay/checkout`, `/claim`, `/native`, `/entitlements` | Purchases |
| `/_f/push/subscribe`, `/unsubscribe`, `/schedule`, `/cancel`, `/link` | Writes |
| `/_f/auth/start`, `/claim`, `/native` | Login flow |
| `/_f/e` | Analytics beacon |
| `/api/seed/{n}` | Purpose of `n` unknown; did not guess |

## Suggested polling for a bot
- Match the cache lifetimes. Polling faster than `max-age` returns the same cached response:
  - `/api/world` and `/api/air`: every 20 seconds
  - `/api/flying`, `/api/patrons`, `/api/track`: every 30 seconds
  - `/api/wx`: every 2 minutes
  - `/api/aurora` and `/api/changelog`: every 5 minutes
  - `/api/fires` and `/api/winds`: every 10 minutes
- Have one poller share its cache across all bot commands.
- Back off on 429 or 5xx responses.
- Use a descriptive User-Agent with a way to contact you.
- Don't post individual players' live locations without opt-in.
