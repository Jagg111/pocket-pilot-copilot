"""Local server for the our-airports panel. Refresh is on demand only.

Usage: PP_COMPANY_ID=<id> [PP_CONTACT=you@example.com] python panel/server.py
"""
import json
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core  # noqa: E402

HERE = Path(__file__).parent
CACHE_FILE = HERE / ".cache" / "panel.json"
NAMES_FILE = HERE / ".cache" / "names.json"
AIRPORTS_FILE = HERE / ".cache" / "airport_names.json"  # built by fetch_airport_names.py
STATE = {"panel": None, "running": False, "flights_running": False, "progress": [0, 0], "error": None}
LOCK = threading.Lock()


def load_cache(company_id):
    """Last good panel from disk, only if it belongs to this company."""
    try:
        panel = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if panel.get("company_id") == str(company_id) and "summary" in panel:
            return core.reclassify(panel)  # pick up threshold/ordering changes
    except (OSError, ValueError):
        pass
    return None


def save_cache(panel):
    try:
        CACHE_FILE.parent.mkdir(exist_ok=True)
        tmp = CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(panel), encoding="utf-8")
        tmp.replace(CACHE_FILE)
    except OSError:
        pass  # cache is a convenience; the in-memory copy still works


def load_names():
    try:
        d = json.loads(NAMES_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_names(names):
    try:
        NAMES_FILE.parent.mkdir(exist_ok=True)
        NAMES_FILE.write_text(json.dumps(names), encoding="utf-8")
    except OSError:
        pass


def load_airport_names():
    try:
        d = json.loads(AIRPORTS_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def refresh_flights(company_id):
    """One small call: update just the flight board in the current panel."""
    try:
        with LOCK:
            panel = STATE["panel"]
            paint = panel.get("company_paint") if panel else None
            first_code = panel["rows"][0]["code"] if panel and panel["rows"] else None
        if panel is None:
            with LOCK:
                STATE["error"] = "Press Refresh first to load the airports."
            return
        feed = core.fetch_json("/api/air/co" + urllib.parse.quote(str(company_id), safe=""))
        if not paint and first_code:  # one extra call, only if we never saw our paint
            st = core.fetch_json("/api/standings?code=" + urllib.parse.quote(first_code, safe=""))
            paint = ((st.get("cos") or {}).get(str(company_id)) or {}).get("paint")
        flights = core.mark_company_planes(core.flights_from_feed(feed, company_id), paint)
        with LOCK:
            panel.update(flights=flights, company_paint=paint, flights_now=feed.get("now"),
                         flights_as_of=time.time())
            STATE["error"] = None
        save_cache(panel)
    except Exception as e:
        with LOCK:
            STATE["error"] = f"{type(e).__name__}: {e}"
    finally:
        with LOCK:
            STATE["flights_running"] = False


def refresh(company_id):
    def prog(i, n):
        STATE["progress"] = [i, n]
    try:
        names = load_names()  # grows with every refresh
        panel = core.build_panel(company_id, progress=prog, names=names,
                                 base_names=load_airport_names())
        save_names(names)
        save_cache(panel)
        with LOCK:
            STATE.update(panel=panel, error=None)
    except Exception as e:
        with LOCK:
            STATE["error"] = f"{type(e).__name__}: {e}"
    finally:
        with LOCK:
            STATE["running"] = False


class Handler(BaseHTTPRequestHandler):
    company_id = ""

    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if host in ("127.0.0.1", "localhost"):
            return True
        self._send(403, "forbidden", "text/plain")
        return False

    def do_GET(self):
        if not self._host_ok():
            return
        if self.path == "/":
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/panel":
            with LOCK:
                self._send(200, json.dumps(STATE), "application/json")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if not self._host_ok():
            return
        if self.headers.get("X-Panel") != "1":
            self._send(403, "forbidden", "text/plain")
            return
        if self.path == "/api/refresh":
            with LOCK:
                start = not STATE["running"]
                if start:
                    STATE.update(running=True, progress=[0, 0], error=None)
            if start:
                threading.Thread(target=refresh, args=(self.company_id,), daemon=True).start()
            self._send(202, "{}", "application/json")
        elif self.path == "/api/refresh-flights":
            with LOCK:
                start = not STATE["flights_running"]
                if start:
                    STATE["flights_running"] = True
            if start:
                threading.Thread(target=refresh_flights, args=(self.company_id,), daemon=True).start()
            self._send(202, "{}", "application/json")
        else:
            self._send(404, "not found", "text/plain")

    def log_message(self, *a):
        pass


def main():
    cid = os.environ.get("PP_COMPANY_ID", "").strip()
    if not cid:
        sys.exit("Set PP_COMPANY_ID to your company id (see docs/private/pilot-identifiers.md).")
    Handler.company_id = cid
    STATE["panel"] = load_cache(cid)
    port = int(os.environ.get("PP_PORT", "8765"))
    print(f"Panel at http://127.0.0.1:{port}/  (cached data loads automatically; Refresh re-fetches)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
