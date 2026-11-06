"""Local server for the our-airports panel. Refresh is on demand only.

Usage: PP_COMPANY_ID=<id> [PP_CONTACT=you@example.com] python panel/server.py
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core  # noqa: E402

HERE = Path(__file__).parent
STATE = {"panel": None, "running": False, "progress": [0, 0], "error": None}
LOCK = threading.Lock()


def refresh(company_id):
    def prog(i, n):
        STATE["progress"] = [i, n]
    try:
        panel = core.build_panel(company_id, progress=prog)
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
        else:
            self._send(404, "not found", "text/plain")

    def log_message(self, *a):
        pass


def main():
    cid = os.environ.get("PP_COMPANY_ID", "").strip()
    if not cid:
        sys.exit("Set PP_COMPANY_ID to your company id (see docs/private/pilot-identifiers.md).")
    Handler.company_id = cid
    port = int(os.environ.get("PP_PORT", "8765"))
    print(f"Panel at http://127.0.0.1:{port}/  (press Refresh on the page to fetch)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
