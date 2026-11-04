"""
Smoke + correctness tests.  Run from the project root:  python -m pytest tests -q
(or `python tests/test_app.py`). Needs `python setup.py` to have been run.
"""
import os
import sys
import time
import unittest

os.environ["TRAFFIC_DISABLE_WEATHER"] = "1"  # tests must not depend on the network
os.environ["TRAFFIC_DISABLE_LIVE"] = "1"     # ...nor spend TomTom quota
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from app import app, service  # noqa: E402
from service import rush_windows  # noqa: E402


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)

    def test_health_and_spa_fallback(self):
        self.assertEqual(self.c.get("/healthz").json()["zones"], len(service.zones))
        # client-side routes return the app shell (200) when built, or a clear 503 hint when not
        self.assertIn(self.c.get("/city/Delhi").status_code, (200, 503))
        self.assertEqual(self.c.get("/api/nope").status_code, 404)

    def test_unknown_city_404(self):
        self.assertEqual(self.c.get("/api/city/Atlantis").status_code, 404)
        self.assertEqual(self.c.get("/api/city/Port%20Blair").status_code, 200)

    def test_path_traversal_blocked(self):
        r = self.c.get("/..%2f..%2fconfig.py")
        self.assertNotIn(b"TOMTOM_API_KEY", r.content)

    def test_overview_covers_india(self):
        d = self.c.get("/api/overview").json()
        self.assertGreaterEqual(d["national"]["n_cities"], 100)
        self.assertGreater(len(d["zones"]), 500)
        for z in d["zones"]:
            self.assertTrue(0 <= z["score"] <= 100)
            self.assertIn(z["level"], ["Low", "Moderate", "Heavy", "Severe"])
            self.assertTrue(6 < z["lat"] < 38 and 67 < z["lon"] < 98, z["name"])

    def test_overview_is_fast_when_warm(self):
        self.c.get("/api/overview")
        t = time.time()
        for _ in range(20):
            self.c.get("/api/overview")
        self.assertLess((time.time() - t) / 20, 0.15)

    def test_rush_hour_shape(self):
        # Mondays in a non-holiday week: CBD must peak in the evening/morning, not at 3am
        d = self.c.get("/api/predict?city=Bengaluru&datetime=2026-11-16T03:00&weather=dry").json()
        d2 = self.c.get("/api/predict?city=Bengaluru&datetime=2026-11-16T18:30&weather=dry").json()
        self.assertLess(d["score"], d2["score"] - 20)
        self.assertTrue(d2["is_rush_hour"])
        self.assertFalse(d["is_rush_hour"])

    def test_rain_increases_congestion(self):
        base = self.c.get("/api/predict?city=Mumbai&datetime=2026-11-17T09:00&weather=dry").json()["score"]
        rain = self.c.get("/api/predict?city=Mumbai&datetime=2026-11-17T09:00&weather=heavy").json()["score"]
        self.assertGreater(rain, base)

    def test_weekend_lighter_for_business_zone(self):
        wd = self.c.get("/api/predict?city=Hyderabad&zone_id=%d&datetime=2026-11-17T09:00&weather=dry" % self._zone("Hyderabad", "IT / Business Park")).json()
        we = self.c.get("/api/predict?city=Hyderabad&zone_id=%d&datetime=2026-11-22T09:00&weather=dry" % self._zone("Hyderabad", "IT / Business Park")).json()
        self.assertGreater(wd["score"], we["score"] + 15)

    def test_big_city_busier_than_small(self):
        a = self.c.get("/api/predict?city=Bengaluru&datetime=2026-11-17T18:30&weather=dry").json()["score"]
        b = self.c.get("/api/predict?city=Gangtok&datetime=2026-11-17T18:30&weather=dry").json()["score"]
        self.assertGreater(a, b)

    def test_interval_brackets_score(self):
        d = self.c.get("/api/predict?city=Pune&datetime=2026-11-17T12:00").json()
        self.assertLessEqual(d["low"], d["score"])
        self.assertGreaterEqual(d["high"], d["score"])

    def test_interpolation_is_continuous(self):
        a = self.c.get("/api/predict?city=Delhi&datetime=2026-11-17T08:59&weather=dry").json()["score"]
        b = self.c.get("/api/predict?city=Delhi&datetime=2026-11-17T09:00&weather=dry").json()["score"]
        self.assertLess(abs(a - b), 3)

    def test_midnight_wrap(self):
        d = self.c.get("/api/predict?city=Delhi&datetime=2026-11-17T23:30&weather=dry")
        self.assertEqual(d.status_code, 200)

    def test_validation(self):
        self.assertEqual(self.c.get("/api/predict").status_code, 400)
        self.assertEqual(self.c.get("/api/predict?city=Delhi&datetime=garbage").status_code, 400)
        self.assertEqual(self.c.get("/api/predict?city=Delhi&datetime=2026-11-17T09:00%2B05:30").status_code, 400)
        self.assertEqual(self.c.get("/api/predict?city=Delhi&datetime=1999-01-01T09:00").status_code, 400)
        self.assertEqual(self.c.get("/api/predict?city=Delhi&weather=snow").status_code, 400)
        self.assertEqual(self.c.get("/api/predict?city=Delhi&zone_id=abc").status_code, 400)
        mumbai_zone = self._zone("Mumbai", "CBD")
        self.assertEqual(self.c.get(f"/api/predict?city=Delhi&zone_id={mumbai_zone}").status_code, 400)
        self.assertEqual(self.c.post("/api/predict", json=[1, 2]).status_code, 400)
        self.assertEqual(self.c.get("/api/city/Delhi?date=2026-13-45").status_code, 400)
        self.assertEqual(self.c.get("/api/nearest?lat=x&lon=1").status_code, 400)

    def test_post_predict(self):
        r = self.c.post("/api/predict", json={"city": "Delhi", "datetime": "2026-11-17T09:00", "weather": "dry"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.json()["level"], ["Low", "Moderate", "Heavy", "Severe"])

    def test_city_detail_and_zone(self):
        d = self.c.get("/api/city/Chennai").json()
        self.assertEqual(len(d["curve"]["mean"]), 24)
        self.assertEqual(len(d["weekly"]), 7)
        self.assertTrue(all(len(r) == 24 for r in d["weekly"]))
        z = self.c.get(f"/api/zone/{d['zones'][0]['id']}").json()
        self.assertEqual(len(z["curve"]["mean"]), 24)
        self.assertEqual(self.c.get("/api/zone/999999").status_code, 404)

    def test_rush_table_and_nearest(self):
        t = self.c.get("/api/rush-hours?date=2026-11-17").json()
        self.assertGreaterEqual(len(t["cities"]), 100)
        n = self.c.get("/api/nearest?lat=28.62&lon=77.2").json()
        self.assertEqual(n["city"], "Delhi")
        self.assertEqual(self.c.get("/api/nearest?lat=0&lon=0").status_code, 404)

    @staticmethod
    def _zone(city, kind):
        return next(z["location_id"] for z in service.zones if z["city"] == city and z["zone_kind"] == kind)


class RushWindowTests(unittest.TestCase):
    def test_double_peak(self):
        c = [10] * 24
        for h in (9, 10):
            c[h] = 70
        for h in (18, 19, 20):
            c[h] = 85
        w = rush_windows(c)
        self.assertEqual([(x["start"], x["end"]) for x in w], [(9, 11), (18, 21)])

    def test_flat_day_has_no_rush(self):
        self.assertEqual(rush_windows([20] * 24), [])
        self.assertEqual(rush_windows([55 + (i % 2) for i in range(24)]), [])

    def test_quiet_day_has_no_rush(self):
        self.assertEqual(rush_windows([5 + (h in (9, 18)) * 15 for h in range(24)]), [])


if __name__ == "__main__":
    unittest.main()
