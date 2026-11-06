import email.message
import io
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import core  # noqa: E402

ME = "1"
COS = {"1": {"name": "Us", "tag": "US"}, "2": {"name": "Rival", "tag": "RV"}, "3": {"name": "Third", "tag": "T3"}}


def st(*entries):
    return {"list": [{"id": i, "value": v} for i, v in entries], "cos": COS}


class Rows(unittest.TestCase):
    def test_held_margin(self):
        r = core.build_row("KAAA", ME, st(("1", 61020), ("2", 7005)))
        self.assertEqual((r["status"], r["margin"], r["runner_up"]), ("held", 54015, "Rival"))

    def test_lost(self):
        r = core.build_row("KBBB", ME, st(("2", 24600), ("1", 15900)))
        self.assertEqual((r["status"], r["margin"]), ("lost", 8700))

    def test_lost_not_listed(self):
        r = core.build_row("KBBB", ME, st(("2", 24600)))
        self.assertEqual((r["status"], r["margin"]), ("lost", 24600))

    def test_uncontested(self):
        r = core.build_row("KCCC", ME, st(("1", 3000)))
        self.assertEqual((r["status"], r["margin"], r["note"]), ("safe", 3000, "no competitors"))

    def test_empty_is_error(self):
        self.assertEqual(core.build_row("KDDD", ME, {"list": []})["status"], "error")


class Order(unittest.TestCase):
    def test_risk_order(self):
        rows = [core.build_row("S", ME, st(("1", 100))),
                core.build_row("B", ME, st(("1", 500), ("2", 100))),
                core.build_row("A", ME, st(("1", 150), ("2", 100))),
                core.build_row("L", ME, st(("2", 900), ("1", 10))),
                {"code": "E", "status": "error", "note": "x"}]
        self.assertEqual([r["code"] for r in core.sort_rows(rows)], ["L", "A", "B", "S", "E"])


class Panel(unittest.TestCase):
    def test_build_panel_with_fixtures_and_one_failure(self):
        def fetch(path):
            if path.startswith("/api/air/co"):
                return {"held": {"KAAA": {"co": "1", "v": 5}, "KBBB": {"co": "1", "v": 5}, "KXXX": {"co": "9", "v": 1}}}
            if "KBBB" in path:
                raise OSError("boom")
            return st(("1", 200), ("2", 50))
        p = core.build_panel(ME, fetch=fetch, sleep=lambda s: None)
        self.assertEqual(p["held_count"], 2)
        self.assertEqual([r["code"] for r in p["rows"]], ["KAAA", "KBBB"])
        self.assertEqual(p["rows"][1]["status"], "error")


class Backoff(unittest.TestCase):
    def test_retries_on_429_then_succeeds(self):
        calls = []

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake(req, timeout=0):
            calls.append(1)
            if len(calls) == 1:
                hdr = email.message.Message()
                hdr["Retry-After"] = "-5"
                raise urllib.error.HTTPError("u", 429, "x", hdr, None)
            return R(b'{"ok":1}')

        orig = urllib.request.urlopen
        urllib.request.urlopen = fake
        try:
            self.assertEqual(core.fetch_json("/x", sleep=lambda s: None), {"ok": 1})
        finally:
            urllib.request.urlopen = orig
        self.assertEqual(len(calls), 2)


class Guards(unittest.TestCase):
    def test_held_codes_filters_other_companies_and_empty(self):
        feed = {"held": {"A": {"co": "1"}, "B": {"co": "2"}}}
        self.assertEqual(core.held_codes(feed, ME), ["A"])
        self.assertEqual(core.held_codes({}, ME), [])

    def test_aborts_after_consecutive_failures(self):
        calls = []

        def fetch(path):
            calls.append(path)
            if path.startswith("/api/air/co"):
                return {"held": {c: {"co": "1"} for c in "ABCDEF"}}
            raise urllib.error.HTTPError("u", 429, "x", None, None)

        with self.assertRaises(RuntimeError):
            core.build_panel(ME, fetch=fetch, sleep=lambda s: None)
        self.assertEqual(len(calls), 1 + core.MAX_CONSECUTIVE_FAILURES)

    def test_error_note_has_status(self):
        self.assertEqual(core.describe_error(urllib.error.HTTPError("u", 404, "x", None, None)), "HTTP 404")


if __name__ == "__main__":
    unittest.main()
