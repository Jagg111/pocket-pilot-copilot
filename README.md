# Pocket Pilot's Copilot

A local dashboard for your company in the mobile game **Pocket Pilots** by Nimblebit. It shows every airport your company holds and ranks them by how likely a rival is to take them, so you know what to defend first.

> Unofficial fan project. Not affiliated with or endorsed by Nimblebit.

This is a proof of concept (the "our-airports panel"). It is the first slice of a planned Discord copilot bot.

## What it does

You give it your company ID. It reads the game's public data and shows one web page on your own machine:

- **Status tiles**: airports held, and how many are urgent (lead under $10,000), at risk (under $20,000) or already lost. Click a tile to filter.
- **Most at risk**: the urgent, at-risk and lost airports, highest dollar value first, with holder, runner-up and the margin between you.
- **All airports**: every monitored airport, thinnest lead first.
- **Pilots in the air**: your company's flights right now, with time left. It has its own Refresh flights button, which makes just one small call.
- **Biggest rivals**: rival companies ranked by the pressure they put on your airports.

Only your top 20 airports by value are monitored, to keep the number of requests down. Everything comes from the current moment, and no history is kept.

## Requirements

- Python 3 (developed on 3.14). It uses only the standard library, so there is nothing to `pip install`.
- An internet connection.
- Your Pocket Pilots company ID (see below).

## Quick start

1. Clone the repo and open a terminal in its folder.
2. Find your company ID (next section).
3. Set it and start the server.

   Windows (PowerShell):

   ```powershell
   $env:PP_COMPANY_ID = "your-company-id"
   python panel/server.py
   ```

   macOS / Linux:

   ```bash
   PP_COMPANY_ID=your-company-id python3 panel/server.py
   ```

4. Open <http://127.0.0.1:8765/> and press **Refresh**.

The first Refresh takes about a minute, because it makes one request per monitored airport, one second apart. Press Ctrl+C in the terminal to stop the server.

## Finding your company ID

Company IDs are public. This looks up a company by part of its name, or by its exact tag, and prints the ID, name and tag of each match:

```bash
python -c "import json,sys,urllib.request as u; q=sys.argv[1].lower(); r=u.Request('https://pilots.nimblebit.com/api/world?v=2',headers={'User-Agent':'pocket-pilots-copilot-poc/0.1 (company id lookup)'}); [print(c['id'],c['name'],c['tag']) for c in json.load(u.urlopen(r))['cos'].values() if q in c['name'].lower() or q==c['tag'].lower()]" "your company name"
```

It works the same in PowerShell, bash and zsh (use `python3` if `python` isn't found). Names match case-insensitively and may match several companies, so check the tag.

## Configuration

All settings are environment variables.

| Variable | Default | Purpose |
|---|---|---|
| `PP_COMPANY_ID` | none, required | Your company ID. |
| `PP_PORT` | `8765` | Local port for the page. |
| `PP_TOP_AIRPORTS` | `20` | How many of your highest-value airports to monitor. Each one costs one request per Refresh. |
| `PP_CONTACT` | `contact-not-set` | Optional email or handle, added to the User-Agent so the game's developers can reach you if needed. |

## Optional: real airport names

Out of the box airports show as their codes. To show names too, run this once. It downloads the public-domain [OurAirports](https://ourairports.com/data/) list (about 12 MB) and keeps only the code-to-name pairs:

```bash
python panel/fetch_airport_names.py
```

## Running the tests

```bash
python -m unittest discover -s panel/tests
```

## Good to know

- **Be polite to the API.** It is unofficial and undocumented, and the game's developer has asked people to "just don't go crazy". The app respects the cache lifetimes, spaces requests out, and backs off on 429 and 5xx errors. Please don't change that to refresh faster.
- **Public data only.** There is no login, sync code or token, and none is ever sent.
- **Local only.** The server listens on 127.0.0.1 and rejects other hosts.
- **The API may change.** If the game updates, the panel could break. Details are in [`docs/pocket-pilots-api-notes.md`](docs/pocket-pilots-api-notes.md).
- **Cached data.** The last Refresh is saved in `panel/.cache/` and loads when the server starts. Delete that folder to start fresh.
- **Keep private data private.** `docs/private/` is git-ignored. Put your own IDs and raw samples there, not in commits.

## Project layout

- `panel/` – the app: `server.py` (local server), `core.py` (fetching and risk logic), `index.html` (the page), `fetch_airport_names.py`, `tests/`
- `docs/` – [API notes](docs/pocket-pilots-api-notes.md) and a [capture of the in-game wiki](docs/pocket-pilots-wiki.md)
- `_bmad-output/` – the [spec for this proof of concept](_bmad-output/specs/spec-our-airports-panel-poc/SPEC.md) and other planning artifacts

## Contributing with BMAD

The project is planned and built with the [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD). Its skills are installed for Claude Code (`.claude/skills`) and Codex (`.agents/skills`), with configuration in `_bmad/`. From the project folder, launch your agent and invoke the `bmad-help` skill to see what to do next.

## License

Released under the [MIT License](LICENSE). Bundled BMAD Method files are
MIT-licensed by BMad Code, LLC; see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
