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
TOP_AIRPORTS = int(os.environ.get("PP_TOP_AIRPORTS", "20"))  # standings calls per refresh
TOP_COMPETITORS = 3  # extra /api/air/co<id> calls per refresh
URGENT_BELOW = 10000
AT_RISK_BELOW = 20000


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
    """urgent below $10,000, at_risk below $20,000, else ok."""
    if margin < URGENT_BELOW:
        return "urgent"
    if margin < AT_RISK_BELOW:
        return "at_risk"
    return "ok"


def summarize(rows):
    counts = {"lost": 0, "urgent": 0, "at_risk": 0, "ok": 0, "error": 0}
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
        if r["status"] == "held" and r.get("runner_up_id"):
            c = entry(r["runner_up_id"], r["runner_up"], r["runner_up_tag"])
            c["runner_up"] += 1
            if r["risk"] in ("urgent", "at_risk"):
                c[r["risk"]] += 1
        elif r["status"] == "lost":
            entry(r["holder_id"], r["holder"], r["holder_tag"])["took"] += 1
    return sorted(tally.values(), key=lambda c: (-(c["runner_up"] + c["took"]), -(c["urgent"] + c["took"]), c["name"]))


def flights_from_feed(feed, company_id):
    """Our pilots' active flights. Callsign, plane, route, timing; no pilot IDs kept."""
    cid = str(company_id)
    out = []
    for f in feed.get("flights") or []:
        if str(f.get("co", cid)) != cid:
            continue
        a, b = f.get("from") or {}, f.get("to") or {}
        out.append({"cs": f.get("cs"), "type": f.get("type"), "reg": f.get("reg"),
                    "from_code": a.get("code"), "from_name": a.get("name"),
                    "to_code": b.get("code"), "to_name": b.get("name"),
                    "t0": f.get("t0"), "eta": f.get("eta"), "paint": f.get("paint")})
    return out


def paint_key(paint):
    """Company paint dict {body,trim,accent} -> the flight feed's 18-hex-char paint string."""
    try:
        return "".join(paint[k].lstrip("#") for k in ("body", "trim", "accent")).lower()
    except (KeyError, TypeError, AttributeError):
        return None


def mark_company_planes(flights, company_paint):
    """Flag flights painted in exactly our company livery. A strong hint, not proof of ownership."""
    key = paint_key(company_paint)
    for f in flights:
        f["company_plane"] = bool(key) and (f.get("paint") or "").lower() == key
    return flights


def top_held(co_feed, company_id, n):
    """Our n highest-value held airports (value is in the co feed, so no extra calls)."""
    held = co_feed.get("held") or {}
    cid = str(company_id)
    mine = [(c, h.get("v") or 0) for c, h in held.items() if str(h.get("co", cid)) == cid]
    mine.sort(key=lambda x: (-x[1], x[0]))
    return [c for c, _ in mine[:n]], len(mine)


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
            # uncontested: nothing to lose, counts as secure
            row.update(status="held", risk="ok", margin=top["value"], note="no competitors")
    else:
        ours = next((e["value"] for e in entries if str(e["id"]) == cid), 0)
        row.update(status="lost", risk="lost", margin=top["value"] - ours, our_value=ours,
                   note="no longer the holder")
    return row


_ATTENTION = ("lost", "urgent", "at_risk")


def reclassify(panel):
    """Re-apply current thresholds, top-N scope and ordering to a panel built earlier (cache)."""
    rows = sorted(panel["rows"], key=lambda r: (-r.get("value", 0), r["code"]))[:TOP_AIRPORTS]
    for r in rows:
        if r["status"] == "safe":  # old caches: uncontested is now just secure
            r["status"], r["risk"] = "held", "ok"
        elif r["status"] == "held" and r.get("runner_up_id"):
            r["risk"] = risk_level(r["margin"])
    panel["rows"] = sort_rows(rows)
    panel["checked_count"] = len(rows)
    panel["summary"] = summarize(rows)
    fresh = {c["id"]: c for c in competitors(rows)}
    for c in panel.get("rivals") or []:
        f = fresh.get(c["id"], {})
        for k in ("runner_up", "urgent", "at_risk", "took"):
            c[k] = f.get(k, 0)
    return panel


def sort_rows(rows):
    """Needs-attention airports (lost, urgent, at risk) first, biggest dollar value first;
    then the rest by thinnest margin, errors last."""
    def key(r):
        if r.get("risk") in _ATTENTION:
            return (0, -r.get("value", 0), r["code"])
        return (1 if r["status"] == "held" else 2, r.get("margin", 0), r["code"])
    return sorted(rows, key=key)


def build_panel(company_id, fetch=fetch_json, sleep=time.sleep, progress=None, names=None,
                base_names=None, top_n=None):
    names = {} if names is None else names
    base_names = base_names or {}
    co_feed = fetch(f"/api/air/co{urllib.parse.quote(str(company_id), safe='')}")
    collect_names(co_feed, names)
    flights = flights_from_feed(co_feed, company_id)
    codes, total_held = top_held(co_feed, company_id, TOP_AIRPORTS if top_n is None else top_n)
    rows = []
    failures = 0
    company_paint = None
    for i, code in enumerate(codes):
        if progress:
            progress(i, len(codes))
        sleep(REQUEST_SPACING_S)
        try:
            standings = fetch("/api/standings?code=" + urllib.parse.quote(code, safe=""))
            rows.append(build_row(code, company_id, standings))
            company_paint = company_paint or ((standings.get("cos") or {}).get(str(company_id)) or {}).get("paint")
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
    return {"as_of": time.time(), "company_id": str(company_id), "held_count": total_held, "checked_count": len(codes),
            "summary": summarize(rows), "rivals": rivals, "rows": rows,
            "flights": mark_company_planes(flights, company_paint), "company_paint": company_paint,
            "flights_now": co_feed.get("now"), "flights_as_of": time.time()}
