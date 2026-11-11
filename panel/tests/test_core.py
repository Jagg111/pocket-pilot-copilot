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
        self.assertEqual((r["status"], r["margin"], r["note"]), ("held", 3000, "no competitors"))

    def test_empty_is_error(self):
        self.assertEqual(core.build_row("KDDD", ME, {"list": []})["status"], "error")


class Order(unittest.TestCase):
    def test_risk_order(self):
        rows = [core.build_row("S", ME, st(("1", 100))),
                core.build_row("B", ME, st(("1", 500), ("2", 100))),
                core.build_row("A", ME, st(("1", 150), ("2", 100))),
                core.build_row("L", ME, st(("2", 900), ("1", 10))),
                {"code": "E", "status": "error", "note": "x"}]
        # attention tier by value desc: L(900), B(500), A(150); then secure, error
        self.assertEqual([r["code"] for r in core.sort_rows(rows)], ["L", "B", "A", "S", "E"])

    def test_high_value_at_risk_outranks_tiny_one_and_ok_follow_by_margin(self):
        rows = [core.build_row("small", ME, st(("1", 1500), ("2", 1000))),     # urgent, value 1500
                core.build_row("big", ME, st(("1", 90000), ("2", 87000))),     # at_risk, value 90000
                core.build_row("ok2", ME, st(("1", 90000), ("2", 50000))),     # ok, margin 40000
                core.build_row("ok1", ME, st(("1", 80000), ("2", 50000)))]     # ok, margin 30000
        self.assertEqual([r["code"] for r in core.sort_rows(rows)], ["big", "small", "ok1", "ok2"])


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
        self.assertEqual([core.risk_level(m) for m in (0, 9999, 10000, 19999, 20000)],
                         ["urgent", "urgent", "at_risk", "at_risk", "ok"])

    def test_summary_counts(self):
        rows = [core.build_row("A", ME, st(("1", 1500), ("2", 100))),    # margin 1400 urgent
                core.build_row("B", ME, st(("1", 15000), ("2", 100))),   # 14900 at_risk
                core.build_row("C", ME, st(("1", 50000), ("2", 100))),   # ok
                core.build_row("D", ME, st(("1", 100))),                 # uncontested -> secure
                core.build_row("E", ME, st(("2", 100), ("1", 50))),      # lost
                {"code": "F", "status": "error", "risk": "error", "note": "x"}]
        self.assertEqual(core.summarize(rows),
                         {"lost": 1, "urgent": 1, "at_risk": 1, "ok": 2, "error": 1})

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


class Reclassify(unittest.TestCase):
    def test_cached_panel_is_reclassified_with_current_thresholds(self):
        rows = [core.build_row("A", ME, st(("1", 18000), ("2", 1000))),   # margin 17000
                core.build_row("B", ME, st(("1", 60000), ("2", 1000)))]   # margin 59000
        rows[0]["risk"] = rows[1]["risk"] = "ok"  # as an older threshold set would have left them
        panel = {"rows": rows, "summary": {}, "rivals": [{"id": "2", "urgent": 9, "at_risk": 9}]}
        out = core.reclassify(panel)
        self.assertEqual([r["risk"] for r in out["rows"]], ["at_risk", "ok"])
        self.assertEqual((out["summary"]["at_risk"], out["summary"]["ok"]), (1, 1))
        self.assertEqual((out["rivals"][0]["urgent"], out["rivals"][0]["at_risk"]), (0, 1))


    def test_reclassify_trims_cached_panel_to_top_n_by_value(self):
        orig = core.TOP_AIRPORTS
        core.TOP_AIRPORTS = 1
        try:
            rows = [core.build_row("small", ME, st(("1", 1500), ("2", 100))),
                    core.build_row("big", ME, st(("1", 90000), ("2", 75000)))]
            panel = {"rows": rows, "summary": {}, "rivals": [{"id": "2"}]}
            out = core.reclassify(panel)
        finally:
            core.TOP_AIRPORTS = orig
        self.assertEqual([r["code"] for r in out["rows"]], ["big"])
        self.assertEqual((out["checked_count"], out["summary"]["at_risk"], out["summary"]["urgent"]), (1, 1, 0))
        self.assertEqual(out["rivals"][0]["runner_up"], 1)


    def test_uncontested_is_secure_and_old_cache_migrates(self):
        r = core.build_row("U", ME, st(("1", 3000)))
        self.assertEqual((r["status"], r["risk"]), ("held", "ok"))
        old = {"code": "O", "status": "safe", "risk": "safe", "margin": 800, "value": 800}
        out = core.reclassify({"rows": [old], "summary": {}})
        self.assertEqual((out["rows"][0]["status"], out["rows"][0]["risk"], out["summary"]["ok"]), ("held", "ok", 1))
        # a small uncontested airport must not be reclassified as urgent by its tiny "margin"
        out = core.reclassify({"rows": [r], "summary": {}})
        self.assertEqual(out["rows"][0]["risk"], "ok")


class Flights(unittest.TestCase):
    FEED = {"now": 1000000, "flights": [
        {"pid": "secret-pid", "cs": "ABC1", "type": "shire", "reg": "N1", "co": "1", "t0": 900000, "eta": 600,
         "from": {"code": "KAAA", "name": "A Field"}, "to": {"code": "KBBB", "name": "B Field"},
         "planned": {"cruise": 1067}},
        {"pid": "p2", "cs": "OTHER", "co": "2", "from": {}, "to": {}}]}

    def test_only_our_flights_and_no_pilot_id(self):
        fl = core.flights_from_feed(self.FEED, ME)
        self.assertEqual([f["cs"] for f in fl], ["ABC1"])
        self.assertNotIn("pid", fl[0])
        self.assertEqual((fl[0]["from_code"], fl[0]["to_name"], fl[0]["eta"]), ("KAAA", "B Field", 600))
        self.assertNotIn("cruise_m", fl[0])

    def test_panel_includes_flights_at_no_extra_cost(self):
        calls = []

        def fetch(path):
            calls.append(path)
            if path == "/api/air/co1":
                return dict(self.FEED, held={"A": {"co": "1", "v": 5}})
            return st(("1", 1000), ("2", 100))
        p = core.build_panel(ME, fetch=fetch, sleep=lambda s: None)
        self.assertEqual(len(p["flights"]), 1)
        self.assertEqual(p["flights_now"], 1000000)
        self.assertEqual(calls.count("/api/air/co1"), 1)


class CompanyPlanes(unittest.TestCase):
    PAINT = {"body": "#112233", "trim": "#445566", "accent": "#778899"}

    def test_paint_key_and_exact_match_only(self):
        self.assertEqual(core.paint_key(self.PAINT), "112233445566778899")
        fl = [{"paint": "112233445566778899"}, {"paint": "112233445566112233"}, {"paint": None}]
        core.mark_company_planes(fl, self.PAINT)
        self.assertEqual([f["company_plane"] for f in fl], [True, False, False])

    def test_unknown_company_paint_marks_nothing(self):
        fl = core.mark_company_planes([{"paint": "112233445566778899"}], None)
        self.assertFalse(fl[0]["company_plane"])

    def test_build_panel_marks_company_plane_and_keeps_reg_and_paint(self):
        def fetch(path):
            if path == "/api/air/co1":
                return {"now": 1, "held": {"A": {"co": "1", "v": 5}}, "flights": [
                    {"cs": "X", "co": "1", "type": "monarch", "reg": "N123AB", "paint": "112233445566778899",
                     "from": {}, "to": {}}]}
            d = st(("1", 1000), ("2", 100))
            d["cos"]["1"] = dict(COS["1"], paint=self.PAINT)
            return d
        f = core.build_panel(ME, fetch=fetch, sleep=lambda s: None)["flights"][0]
        self.assertTrue(f["company_plane"])
        self.assertEqual((f["reg"], f["paint"]), ("N123AB", "112233445566778899"))


class TopN(unittest.TestCase):
    def test_only_top_n_by_value_get_standings_calls(self):
        calls = []

        def fetch(path):
            calls.append(path)
            if path == "/api/air/co1":
                return {"held": {"A": {"co": "1", "v": 100}, "B": {"co": "1", "v": 900},
                                 "C": {"co": "1", "v": 500}, "D": {"co": "1", "v": 50}}}
            return st(("1", 1000), ("2", 100))
        p = core.build_panel(ME, fetch=fetch, sleep=lambda s: None, top_n=2)
        self.assertEqual(sorted(r["code"] for r in p["rows"]), ["B", "C"])
        self.assertEqual((p["held_count"], p["checked_count"]), (4, 2))
        standings = [c for c in calls if c.startswith("/api/standings")]
        self.assertEqual(sorted(standings), ["/api/standings?code=B", "/api/standings?code=C"])


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
            return {"A": st(("1", 1000), ("2", 100)), "B": st(("1", 15000), ("2", 100)),
                    "C": st(("1", 50000), ("3", 100)), "D": st(("3", 500), ("1", 100))}[code]
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
