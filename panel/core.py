"""Pure logic + polite fetching for the our-airports panel POC. Public endpoints only."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://pilots.nimblebit.com"
REQUEST_SPACING_S = 1.0
MAX_TRIES = 3
MAX_CONSECUTIVE_FAILURES = 3


def user_agent():
    contact = os.environ.get("PP_CONTACT", "contact-not-set")
    return f"pocket-pilots-copilot-poc/0.1 (personal hobby project; {contact})"


def fetch_json(path, sleep=time.sleep):
    """GET a public endpoint; back off on 429/5xx. No credentials ever sent."""
    req = urllib.request.Request(BASE + path, headers={"User-Agent": user_agent()})
    delay = 2.0
    for attempt in range(MAX_TRIES):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and attempt < MAX_TRIES - 1:
                retry_after = e.headers.get("Retry-After") if e.headers else None
                try:
                    wait = float(retry_after) if retry_after else delay
                except ValueError:
                    wait = delay
                if not wait >= 0:  # negative or NaN
                    wait = delay
                sleep(min(wait, 60))
                delay *= 2
                continue
            raise
        except urllib.error.URLError:
            if attempt < MAX_TRIES - 1:
                sleep(delay)
                delay *= 2
                continue
            raise


def describe_error(e):
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    return type(e).__name__


def held_codes(co_feed, company_id):
    """Airport codes held by our company from the /api/air/co<id> payload."""
    held = co_feed.get("held") or {}
    cid = str(company_id)
    return sorted(c for c, h in held.items() if str(h.get("co", cid)) == cid)


def build_row(code, company_id, standings):
    """One panel row from a /api/standings payload."""
    cid = str(company_id)
    entries = standings.get("list") or []
    cos = standings.get("cos") or {}

    def name(i):
        c = cos.get(str(i)) or {}
        return c.get("name") or str(i), c.get("tag") or ""

    if not entries:
        return {"code": code, "status": "error", "note": "no standings returned"}
    top = entries[0]
    holder_name, holder_tag = name(top["id"])
    row = {"code": code, "holder": holder_name, "holder_tag": holder_tag, "value": top["value"]}
    if str(top["id"]) == cid:
        if len(entries) > 1:
            ru = entries[1]
            ru_name, ru_tag = name(ru["id"])
            row.update(status="held", margin=top["value"] - ru["value"],
                       runner_up=ru_name, runner_up_tag=ru_tag, runner_up_value=ru["value"])
        else:
            row.update(status="safe", margin=top["value"], note="no competitors")
    else:
        ours = next((e["value"] for e in entries if str(e["id"]) == cid), 0)
        row.update(status="lost", margin=top["value"] - ours, our_value=ours,
                   note="no longer the holder")
    return row


_ORDER = {"lost": 0, "held": 1, "safe": 2, "error": 3}


def sort_rows(rows):
    """Risk order: lost first, then contested by ascending margin, then safe, then errors."""
    return sorted(rows, key=lambda r: (_ORDER[r["status"]], r.get("margin", 0), r["code"]))


def build_panel(company_id, fetch=fetch_json, sleep=time.sleep, progress=None):
    co_feed = fetch(f"/api/air/co{urllib.parse.quote(str(company_id), safe='')}")
    codes = held_codes(co_feed, company_id)
    rows = []
    failures = 0
    for i, code in enumerate(codes):
        if progress:
            progress(i, len(codes))
        sleep(REQUEST_SPACING_S)
        try:
            standings = fetch("/api/standings?code=" + urllib.parse.quote(code, safe=""))
            rows.append(build_row(code, company_id, standings))
            failures = 0
        except Exception as e:  # keep the panel useful if one airport fails
            rows.append({"code": code, "status": "error", "note": describe_error(e)})
            failures += 1
            if failures >= MAX_CONSECUTIVE_FAILURES:  # upstream unhappy: stop hitting it
                raise RuntimeError(f"aborted after {failures} consecutive failures ({describe_error(e)})")
    if progress:
        progress(len(codes), len(codes))
    return {"as_of": time.time(), "held_count": len(codes), "rows": sort_rows(rows)}
