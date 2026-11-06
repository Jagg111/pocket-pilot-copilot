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


class Risk(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual([core.risk_level(m) for m in (0, 1999, 2000, 4999, 5000)],
                         ["urgent", "urgent", "at_risk", "at_risk", "ok"])

    def test_summary_counts(self):
        rows = [core.build_row("A", ME, st(("1", 1500), ("2", 100))),    # margin 1400 urgent
                core.build_row("B", ME, st(("1", 4000), ("2", 100))),    # 3900 at_risk
                core.build_row("C", ME, st(("1", 9000), ("2", 100))),    # ok
                core.build_row("D", ME, st(("1", 100))),                 # safe
                core.build_row("E", ME, st(("2", 100), ("1", 50))),      # lost
                {"code": "F", "status": "error", "risk": "error", "note": "x"}]
        self.assertEqual(core.summarize(rows),
                         {"lost": 1, "urgent": 1, "at_risk": 1, "ok": 1, "safe": 1, "error": 1})

    def test_runner_up_has_no_value(self):
        self.assertNotIn("runner_up_value", core.build_row("A", ME, st(("1", 500), ("2", 100))))


class Cache(unittest.TestCase):
    def test_roundtrip_and_company_mismatch(self):
        import tempfile
        import server
        with tempfile.TemporaryDirectory() as d:
            server.CACHE_FILE = Path(d) / ".cache" / "panel.json"
            self.assertIsNone(server.load_cache(ME))
            panel = core.build_panel(ME, fetch=lambda p: {"held": {"A": {"co": "1"}}} if "/co" in p
                                     else st(("1", 300), ("2", 100)), sleep=lambda s: None)
            server.save_cache(panel)
            self.assertEqual(server.load_cache(ME)["held_count"], 1)
            self.assertIsNone(server.load_cache("other"))


class Rivals(unittest.TestCase):
    def test_rival_ranking_and_holds(self):
        feeds = {"/api/air/co2": {"held": {"X": {}, "Y": {}, "Z": {}}}, "/api/air/co3": {"held": {"Q": {}}}}

        def fetch(path):
            if path == "/api/air/co1":
                return {"held": {c: {"co": "1"} for c in "ABCD"},
                        "flights": [{"from": {"code": "A", "name": "Alpha Field"}, "to": {}}]}
            if path in feeds:
                return feeds[path]
            code = path.split("=")[1]
            return {"A": st(("1", 1000), ("2", 100)), "B": st(("1", 3000), ("2", 100)),
                    "C": st(("1", 9000), ("3", 100)), "D": st(("3", 500), ("1", 100))}[code]
        names = {}
        p = core.build_panel(ME, fetch=fetch, sleep=lambda s: None, names=names)
        r2, r3 = p["rivals"]
        self.assertEqual((r2["id"], r2["runner_up"], r2["urgent"], r2["at_risk"], r2["holds"]), ("2", 2, 1, 1, 3))
        self.assertEqual((r3["id"], r3["runner_up"], r3["took"], r3["holds"]), ("3", 1, 1, 1))
        self.assertEqual(next(r for r in p["rows"] if r["code"] == "A")["name"], "Alpha Field")

    def test_rival_fetch_failure_leaves_holds_unknown(self):
        def fetch(path):
            if path == "/api/air/co1":
                return {"held": {"A": {"co": "1"}}}
            if path.startswith("/api/standings"):
                return st(("1", 1000), ("2", 100))
            raise OSError("down")
        p = core.build_panel(ME, fetch=fetch, sleep=lambda s: None)
        self.assertIsNone(p["rivals"][0]["holds"])


class AirportNames(unittest.TestCase):
    def test_csv_ident_wins_over_alternate_codes(self):
        import fetch_airport_names as f
        csv_text = "\n".join(["ident,name,gps_code,local_code",
                              "KAAA,First Field,,",
                              "ZZZ1,Other Field,KAAA,LCL1", ""])
        names = f.build(csv_text)
        self.assertEqual((names["KAAA"], names["LCL1"], names["ZZZ1"]), ("First Field", "Other Field", "Other Field"))

    def test_base_names_fill_rows_and_game_names_win(self):
        def fetch(path):
            if path == "/api/air/co1":
                return {"held": {"A": {"co": "1"}, "B": {"co": "1"}},
                        "flights": [{"from": {"code": "A", "name": "Game Name"}, "to": {}}]}
            return st(("1", 1000), ("2", 100))
        p = core.build_panel(ME, fetch=fetch, sleep=lambda s: None, base_names={"A": "Base A", "B": "Base B"})
        got = {r["code"]: r["name"] for r in p["rows"]}
        self.assertEqual(got, {"A": "Game Name", "B": "Base B"})


if __name__ == "__main__":
    unittest.main()
