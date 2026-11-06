"""One-off: download OurAirports (public domain) and build panel/.cache/airport_names.json.

Source: https://davidmegginson.github.io/ourairports-data/airports.csv (about 12 MB).
Run:  python panel/fetch_airport_names.py
Only airport codes -> names are kept; the CSV itself is not stored.
"""
import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OUT = Path(__file__).parent / ".cache" / "airport_names.json"


def build(text):
    rows = [r for r in csv.DictReader(io.StringIO(text)) if (r.get("name") or "").strip()]
    names = {}
    # ident wins everywhere; alternate codes the game might use only fill gaps
    for key in ("ident", "gps_code", "local_code"):
        for row in rows:
            code = (row.get(key) or "").strip()
            if code and code not in names:
                names[code] = row["name"].strip()
    return names


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "pocket-pilots-copilot-poc/0.1 (personal hobby project)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8", "replace")
    names = build(text)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(names)} code->name entries to {OUT}")


if __name__ == "__main__":
    sys.exit(main())
