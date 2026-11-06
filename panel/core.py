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
TOP_COMPETITORS = 3  # extra /api/air/co<id> calls per refresh
URGENT_BELOW = 2000
AT_RISK_BELOW = 5000


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


def risk_level(margin):
    """urgent below $2,000, at_risk below $5,000, else ok."""
    if margin < URGENT_BELOW:
        return "urgent"
    if margin < AT_RISK_BELOW:
        return "at_risk"
    return "ok"


def summarize(rows):
    counts = {"lost": 0, "urgent": 0, "at_risk": 0, "ok": 0, "safe": 0, "error": 0}
    for r in rows:
        counts[r.get("risk") or "error"] += 1
    return counts


def collect_names(feed, names):
    """Harvest airport names (code -> name) seen in a /api/air/* payload. No extra calls."""
    def take(a):
        if isinstance(a, dict) and a.get("code") and a.get("name"):
            names[a["code"]] = a["name"]
    for f in feed.get("flights") or []:
        take(f.get("from"))
        take(f.get("to"))
    for l in feed.get("landed") or []:
        take(l.get("at"))


def competitors(rows):
    """Rivals ranked by pressure on us: our airports where they are runner-up, plus ones they took."""
    tally = {}

    def entry(i, name, tag):
        return tally.setdefault(i, {"id": i, "name": name, "tag": tag, "runner_up": 0,
                                    "urgent": 0, "at_risk": 0, "took": 0, "holds": None})
    for r in rows:
        if r["status"] == "held":
            c = entry(r["runner_up_id"], r["runner_up"], r["runner_up_tag"])
            c["runner_up"] += 1
            if r["risk"] in ("urgent", "at_risk"):
                c[r["risk"]] += 1
        elif r["status"] == "lost":
            entry(r["holder_id"], r["holder"], r["holder_tag"])["took"] += 1
    return sorted(tally.values(), key=lambda c: (-(c["runner_up"] + c["took"]), -(c["urgent"] + c["took"]), c["name"]))


def build_row(code, company_id, standings):
    """One panel row from a /api/standings payload."""
    cid = str(company_id)
    entries = standings.get("list") or []
    cos = standings.get("cos") or {}

    def name(i):
        c = cos.get(str(i)) or {}
        return c.get("name") or str(i), c.get("tag") or ""

    if not entries:
        return {"code": code, "status": "error", "risk": "error", "note": "no standings returned"}
    top = entries[0]
    holder_name, holder_tag = name(top["id"])
    row = {"code": code, "holder": holder_name, "holder_tag": holder_tag, "holder_id": str(top["id"]),
           "value": top["value"]}
    if str(top["id"]) == cid:
        if len(entries) > 1:
            ru = entries[1]
            ru_name, ru_tag = name(ru["id"])
            margin = top["value"] - ru["value"]
            row.update(status="held", margin=margin, risk=risk_level(margin),
                       runner_up=ru_name, runner_up_tag=ru_tag, runner_up_id=str(ru["id"]))
        else:
            row.update(status="safe", risk="safe", margin=top["value"], note="no competitors")
    else:
        ours = next((e["value"] for e in entries if str(e["id"]) == cid), 0)
        row.update(status="lost", risk="lost", margin=top["value"] - ours, our_value=ours,
                   note="no longer the holder")
    return row


_ORDER = {"lost": 0, "held": 1, "safe": 2, "error": 3}


def sort_rows(rows):
    """Risk order: lost first, then contested by ascending margin, then safe, then errors."""
    return sorted(rows, key=lambda r: (_ORDER[r["status"]], r.get("margin", 0), r["code"]))


def build_panel(company_id, fetch=fetch_json, sleep=time.sleep, progress=None, names=None,
                base_names=None):
    names = {} if names is None else names
    base_names = base_names or {}
    co_feed = fetch(f"/api/air/co{urllib.parse.quote(str(company_id), safe='')}")
    collect_names(co_feed, names)
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
            rows.append({"code": code, "status": "error", "risk": "error", "note": describe_error(e)})
            failures += 1
            if failures >= MAX_CONSECUTIVE_FAILURES:  # upstream unhappy: stop hitting it
                raise RuntimeError(f"aborted after {failures} consecutive failures ({describe_error(e)})")
    if progress:
        progress(len(codes), len(codes))
    rows = sort_rows(rows)
    rivals = competitors(rows)[:TOP_COMPETITORS]
    for c in rivals:  # one small call per top rival: how many airports they hold
        sleep(REQUEST_SPACING_S)
        try:
            feed = fetch("/api/air/co" + urllib.parse.quote(c["id"], safe=""))
            c["holds"] = len(feed.get("held") or {})
            collect_names(feed, names)
        except Exception:
            c["holds"] = None
    for r in rows:
        name = names.get(r["code"]) or base_names.get(r["code"])
        if name:
            r["name"] = name
    return {"as_of": time.time(), "company_id": str(company_id), "held_count": len(codes),
            "summary": summarize(rows), "rivals": rivals, "rows": rows}
