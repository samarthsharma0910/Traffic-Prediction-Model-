"""
TrafficService: everything the web layer needs, computed in-memory and cached.

Speed design: all 664 zones x 24 hours are predicted in ONE vectorised call
(~16k rows) and cached per (date, weather-version). "Live" status, city
summaries and rush-hour windows are then cheap slices/interpolations of that
cache, so page loads never run SQL aggregations or per-zone model calls.
"""
import threading
from datetime import date as date_cls, datetime, timedelta

import numpy as np
import pandas as pd

import live_provider
from cities import CITIES
from config import LEVEL_THRESHOLDS, level_for, now_ist
from database import load_zones
from features import holiday_dates, holiday_name, make_features, zone_columns
from ml_model import load_bundle, predict
from weather import WeatherService

WEATHER_MM = {"dry": 0.0, "light": 2.0, "heavy": 10.0}
FREE_FLOW_KMPH = {"Highway Bypass": 70, "Ring Road": 55, "Airport Corridor": 55}
MIN_DATE, MAX_DATE = date_cls(2023, 1, 1), date_cls(2031, 12, 31)
_HOL = None


def _fmt_hour(h):
    return f"{int(h) % 24:02d}:00"


def rush_windows(curve):
    """
    Rush hour = contiguous hours whose predicted score is in the top 40% of the
    day's range AND at least 'Moderate'. Needs a real daily swing (>=12 pts),
    otherwise there is no distinct rush (e.g. a uniformly quiet or jammed day).
    """
    c = np.asarray(curve, dtype=float)
    lo, hi = c.min(), c.max()
    if hi < LEVEL_THRESHOLDS[0] or hi - lo < 12:
        return []
    thr = max(lo + 0.6 * (hi - lo), LEVEL_THRESHOLDS[0])
    runs = []
    for i in np.where(c >= thr)[0]:
        if runs and i - runs[-1][1] <= 2:  # bridge a single dip hour
            runs[-1][1] = i
        else:
            runs.append([i, i])
    out = []
    for s, e in runs:
        pk = int(s + np.argmax(c[s:e + 1]))
        out.append({"start": int(s), "end": int(e) + 1, "label": f"{_fmt_hour(s)}-{_fmt_hour(e + 1)}",
                    "peak_hour": pk, "peak_score": round(float(c[pk]), 1), "peak_level": level_for(c[pk])})
    return out


class TrafficService:
    def __init__(self):
        self.bundle = load_bundle()
        self.zones = load_zones()
        self.zone_idx = {z["location_id"]: i for i, z in enumerate(self.zones)}
        try:
            self.static = zone_columns(self.zones, self.bundle["city_index"], self.bundle["kind_index"])
        except KeyError as exc:
            raise RuntimeError(f"Database has zones the model never saw ({exc}). Run: python setup.py") from exc
        centres = {c[0]: (c[2], c[3]) for c in CITIES}
        self.city_zones, self.city_meta = {}, {}
        for i, z in enumerate(self.zones):
            self.city_zones.setdefault(z["city"], []).append(i)
        for city, idx in self.city_zones.items():
            z0 = self.zones[idx[0]]
            lat, lon = centres.get(city, (z0["latitude"], z0["longitude"]))
            self.city_meta[city] = {"city": city, "state": z0["state"], "lat": lat, "lon": lon,
                                    "population_m": z0["population_m"], "n_zones": len(idx)}
        self.city_idx = {c: np.array(v) for c, v in self.city_zones.items()}
        self.zone_city = [z["city"] for z in self.zones]
        self.weather = WeatherService([(c, m["lat"], m["lon"]) for c, m in self.city_meta.items()],
                                      on_refresh=self.warm)
        self._cache, self._lock = {}, threading.Lock()
        self._overview, self._overview_key = None, None
        self._weekly_cache = {}

    def start(self):
        self.weather.start()  # its first refresh triggers warm()

    def warm(self):
        """Pre-compute today's and tomorrow's national curves so the first visitor isn't slow."""
        self.overview()

    # ---------------------------------------------------------------- core prediction
    def _predict_zones(self, idx, d, override):
        """Hourly (len(idx), 24) mean/lo/hi/precip for date `d`."""
        idx = np.asarray(idx)
        n = len(idx)
        ts = pd.DatetimeIndex(np.tile(pd.date_range(pd.Timestamp(d), periods=24, freq="h").to_numpy(), n))
        per_city, known = {}, False
        for city in {self.zone_city[i] for i in idx}:
            if override is not None:
                per_city[city] = np.full(24, WEATHER_MM[override], dtype=np.float32)
            else:
                vals = [self.weather.precip(city, datetime(d.year, d.month, d.day, h)) for h in range(24)]
                per_city[city] = np.array([v for v, _ in vals], dtype=np.float32)
                known = known or any(k for _, k in vals)
        precip = np.stack([per_city[self.zone_city[i]] for i in idx])  # (n, 24)
        static = self.static.iloc[np.repeat(idx, 24)].reset_index(drop=True)
        X = make_features(static, ts, precip.reshape(-1))
        m, lo, hi = predict(self.bundle, X)
        return {"mean": m.reshape(n, 24), "lo": lo.reshape(n, 24), "hi": hi.reshape(n, 24),
                "precip": precip, "weather_known": known if override is None else True}

    def _all_curves(self, d, override=None):
        key = (d, override, self.weather.version)
        with self._lock:
            hit = self._cache.get(key)
            if hit is None:
                hit = self._predict_zones(np.arange(len(self.zones)), d, override)
                if len(self._cache) > 40:
                    self._cache.pop(next(iter(self._cache)))
                self._cache[key] = hit
            return hit

    def _at(self, curves_today, curves_next, dt):
        """Linear interpolation between the hourly predictions around `dt`."""
        h, f = dt.hour, dt.minute / 60.0
        out = {}
        for k in ("mean", "lo", "hi"):
            a = curves_today[k][:, h]
            b = curves_today[k][:, h + 1] if h < 23 else curves_next[k][:, 0]
            out[k] = a + (b - a) * f
        out["precip"] = curves_today["precip"][:, h]
        return out

    def _point(self, dt, override=None):
        d = dt.date()
        today = self._all_curves(d, override)
        nxt = self._all_curves(d + timedelta(days=1), override) if dt.hour == 23 and dt.minute else today
        return self._at(today, nxt, dt)

    # ---------------------------------------------------------------- helpers
    def _speed(self, kind, score):
        ff = FREE_FLOW_KMPH.get(kind, 35)
        return round(ff * (1 - 0.8 * score / 100), 1), ff

    def _zone_row(self, i, score, lo, hi, live=None, basis="now"):
        z = self.zones[i]
        if live:
            score = live["score"]
        if live:
            speed, ff = live["current_speed"], live["free_flow_speed"]
        else:
            speed, ff = self._speed(z["zone_kind"], score)
        return {"id": z["location_id"], "city": z["city"], "state": z["state"], "name": z["location_name"],
                "kind": z["zone_kind"], "road": z["road_name"], "lat": z["latitude"], "lon": z["longitude"],
                "score": round(score, 1), "level": level_for(score),
                # a measured value has no model uncertainty band
                "low": round(float(score if live else min(lo, score)), 1),
                "high": round(float(score if live else max(hi, score)), 1), "basis": basis,
                "speed_kmph": round(speed, 1), "free_flow_kmph": ff,
                "source": "tomtom" if live else "ml_estimate"}

    def _city_curve(self, city, curves):
        idx = self.city_idx[city]
        return {k: curves[k][idx].mean(0) for k in ("mean", "lo", "hi")}

    def _next_rush(self, city, now):
        today = rush_windows(self._city_curve(city, self._all_curves(now.date()))["mean"])
        nowh = now.hour + now.minute / 60.0
        for w in today:
            if w["start"] <= nowh < w["end"]:
                return {"state": "in_rush", "label": w["label"], "until": _fmt_hour(w["end"]),
                        "minutes": int((w["end"] - nowh) * 60)}
        for w in today:
            if w["start"] > nowh:
                return {"state": "upcoming", "label": w["label"], "starts": _fmt_hour(w["start"]),
                        "minutes": int((w["start"] - nowh) * 60)}
        tmr = now.date() + timedelta(days=1)
        nxt = rush_windows(self._city_curve(city, self._all_curves(tmr))["mean"])
        if nxt:
            w = nxt[0]
            return {"state": "upcoming", "label": w["label"], "starts": _fmt_hour(w["start"]) + " (tomorrow)",
                    "minutes": int((24 + w["start"] - nowh) * 60)}
        return {"state": "none"}

    def _live_overrides(self, zone_ids):
        if not live_provider.enabled():
            return {}
        return {zid: live_provider.cached(zid) for zid in zone_ids if live_provider.cached(zid)}

    # ---------------------------------------------------------------- public API
    def overview(self):
        now = now_ist()
        key = (now.strftime("%Y%m%d%H%M"), self.weather.version, live_provider.version())
        if self._overview is not None and self._overview_key == key:
            return self._overview
        p = self._point(now)
        live = self._live_overrides([z["location_id"] for z in self.zones])
        zrows = [self._zone_row(i, p["mean"][i], p["lo"][i], p["hi"][i], live.get(z["location_id"]))
                 for i, z in enumerate(self.zones)]
        cities = []
        for city, meta in self.city_meta.items():
            rows = [zrows[i] for i in self.city_zones[city]]
            scores = [r["score"] for r in rows]
            worst = max(rows, key=lambda r: r["score"])
            cur = self.weather.current(city)
            avg = float(np.mean(scores))
            cities.append({**meta, "score": round(avg, 1), "level": level_for(avg), "max_score": worst["score"],
                           "live_zones": sum(r["source"] == "tomtom" for r in rows),
                           "worst_zone": worst["name"], "rush": self._next_rush(city, now),
                           "temp": cur["temp"], "precip": cur["precip"]})
        cities.sort(key=lambda c: -c["score"])
        avgs = [c["score"] for c in cities]
        payload = {
            "as_of": now.strftime("%Y-%m-%d %H:%M"), "tz": "IST",
            "source": "tomtom+ml" if live else "ml_estimate",
            "weather_live": self.weather.available,
            "national": {"avg": round(float(np.mean(avgs)), 1), "level": level_for(float(np.mean(avgs))),
                         "cities_in_rush": sum(c["rush"]["state"] == "in_rush" for c in cities),
                         "severe_zones": sum(r["level"] == "Severe" for r in zrows),
                         "heavy_zones": sum(r["level"] == "Heavy" for r in zrows),
                         "n_cities": len(cities), "n_zones": len(zrows),
                         "live_zones": sum(r["source"] == "tomtom" for r in zrows)},
            "cities": cities,
            "zones": [{k: r[k] for k in ("id", "city", "name", "kind", "lat", "lon", "score", "level",
                                         "speed_kmph", "source")} for r in zrows],
        }
        self._overview, self._overview_key = payload, key
        return payload

    def refresh_live(self, city):
        """Fetch measured TomTom speeds for a city's zones (cached 5 min, budgeted). Returns #zones live."""
        idx = self.city_idx[city]
        got = live_provider.refresh_zones([self.zones[i] for i in idx])
        return len(got)

    def city_detail(self, city, d=None, override=None):
        if city not in self.city_idx:
            return None
        now = now_ist()
        d = d or now.date()
        idx = self.city_idx[city]
        zone_ids = [self.zones[i]["location_id"] for i in idx]
        if live_provider.enabled() and d == now.date():
            live_provider.refresh_zones([self.zones[i] for i in idx])
        curves = self._all_curves(d, override)
        cc = self._city_curve(city, curves)
        if d == now.date() and override is None:
            p = self._point(now)
            live = self._live_overrides(zone_ids)
            zones = [self._zone_row(i, p["mean"][i], p["lo"][i], p["hi"][i], live.get(self.zones[i]["location_id"]))
                     for i in idx]
        else:  # other dates / what-if weather: show each zone's peak for that day
            pk = curves["mean"].argmax(1)
            zones = [self._zone_row(i, curves["mean"][i, pk[i]], curves["lo"][i, pk[i]], curves["hi"][i, pk[i]],
                                    basis="day_peak") for i in idx]
        zones.sort(key=lambda r: -r["score"])
        day = np.arange(24)
        busy = day[(day >= 6) & (day <= 22)]
        best = int(busy[np.argmin(cc["mean"][busy])])
        worst = int(busy[np.argmax(cc["mean"][busy])])
        cur = self.weather.current(city)
        return {
            "city": city, "state": self.city_meta[city]["state"], "date": d.isoformat(),
            "is_today": d == now.date(), "as_of": now.strftime("%Y-%m-%d %H:%M"),
            "holiday": holiday_name(d),
            "weather": {"temp": cur["temp"], "precip_now": cur["precip"], "live": self.weather.available,
                        "forecast_known": bool(curves["weather_known"]), "override": override,
                        "rain_hours": int((curves["precip"][idx].mean(0) > 0.1).sum())},
            "score": round(float(np.mean([z["score"] for z in zones])), 1),
            "level": level_for(float(np.mean([z["score"] for z in zones]))),
            "zones": zones,
            "curve": {k: [round(float(v), 1) for v in cc[k]] for k in ("mean", "lo", "hi")},
            "rush": rush_windows(cc["mean"]),
            "next_rush": self._next_rush(city, now) if d == now.date() else None,
            "best_hour": {"hour": best, "label": _fmt_hour(best), "score": round(float(cc["mean"][best]), 1)},
            "worst_hour": {"hour": worst, "label": _fmt_hour(worst), "score": round(float(cc["mean"][worst]), 1)},
            "weekly": self._weekly(idx, d),
            "source": "tomtom+ml" if live_provider.enabled() and any(z["source"] == "tomtom" for z in zones) else "ml_estimate",
        }

    def _typical_date(self, dow, ref):
        global _HOL
        if _HOL is None:
            _HOL = set(holiday_dates().date)
        for k in range(0, 70):
            c = ref + timedelta(days=k)
            if c.weekday() == dow and c not in _HOL:
                return c
        return ref

    def _weekly(self, idx, ref):
        """7x24 'typical dry day' average congestion for the given zones (Mon..Sun)."""
        dates = tuple(self._typical_date(dow, ref) for dow in range(7))
        key = (tuple(int(i) for i in idx), dates)
        hit = self._weekly_cache.get(key)
        if hit is None:
            hit = [[round(float(v), 1) for v in self._predict_zones(idx, d, "dry")["mean"].mean(0)] for d in dates]
            if len(self._weekly_cache) > 300:
                self._weekly_cache.clear()
            self._weekly_cache[key] = hit
        return hit

    def zone_detail(self, zone_id, d=None, override=None):
        i = self.zone_idx.get(zone_id)
        if i is None:
            return None
        now = now_ist()
        d = d or now.date()
        c = self._predict_zones([i], d, override)
        if d == now.date() and override is None:
            live = self._live_overrides([zone_id])
            p = self._point(now)
            row = self._zone_row(i, p["mean"][i], p["lo"][i], p["hi"][i], live.get(zone_id))
        else:
            pk = int(c["mean"][0].argmax())
            row = self._zone_row(i, c["mean"][0, pk], c["lo"][0, pk], c["hi"][0, pk], basis="day_peak")
        curve = c["mean"][0]
        return {**row, "date": d.isoformat(), "holiday": holiday_name(d),
                "curve": {k: [round(float(v), 1) for v in c[k][0]] for k in ("mean", "lo", "hi")},
                "rush": rush_windows(curve), "weekly": self._weekly([i], d),
                "weather": {"forecast_known": bool(c["weather_known"]), "override": override,
                            "rain_hours": int((c["precip"][0] > 0.1).sum())}}

    def predict_at(self, city, zone_id, dt, override):
        """Forecast for a city (or one zone) at a specific IST datetime."""
        idx = np.array([self.zone_idx[zone_id]]) if zone_id else self.city_idx[city]
        d = dt.date()
        today = self._predict_zones(idx, d, override)
        nxt = self._predict_zones(idx, d + timedelta(days=1), override) if dt.hour == 23 and dt.minute else today
        # reuse interpolation (works on any row count)
        at = self._at(today, nxt, dt)
        score, lo, hi = float(at["mean"].mean()), float(at["lo"].mean()), float(at["hi"].mean())
        day_curve = today["mean"].mean(0)
        windows = rush_windows(day_curve)
        h = dt.hour + dt.minute / 60.0
        in_rush = any(w["start"] <= h < w["end"] for w in windows)
        nearest = None
        if windows and not in_rush:
            nearest = min(windows, key=lambda w: min(abs(w["start"] - h), abs(w["end"] - h)))
        return {
            "city": city, "zone_id": zone_id, "datetime": dt.strftime("%Y-%m-%d %H:%M"),
            "score": round(score, 1), "level": level_for(score),
            "low": round(lo, 1), "high": round(hi, 1), "low_level": level_for(lo), "high_level": level_for(hi),
            "is_rush_hour": in_rush, "rush_windows": windows,
            "nearest_rush": nearest["label"] if nearest else None,
            "precip_mm": round(float(at["precip"].mean()), 1),
            "weather_mode": override or ("forecast" if today["weather_known"] else "unavailable (assumed dry)"),
            "holiday": holiday_name(d),
            "day_curve": {"mean": [round(float(v), 1) for v in day_curve],
                          "lo": [round(float(v), 1) for v in today["lo"].mean(0)],
                          "hi": [round(float(v), 1) for v in today["hi"].mean(0)]},
        }

    def rush_table(self, d=None):
        """Per-city rush windows for a date (default today)."""
        d = d or now_ist().date()
        curves = self._all_curves(d)
        rows = []
        for city, meta in self.city_meta.items():
            cc = self._city_curve(city, curves)["mean"]
            w = rush_windows(cc)
            rows.append({"city": city, "state": meta["state"], "windows": w,
                         "peak_score": round(float(cc.max()), 1), "peak_hour": _fmt_hour(int(cc.argmax())),
                         "peak_level": level_for(cc.max())})
        rows.sort(key=lambda r: -r["peak_score"])
        return {"date": d.isoformat(), "cities": rows}

    def nearest_zone(self, lat, lon, max_km=60):
        z_lat = self.static["lat"].to_numpy()
        z_lon = self.static["lon"].to_numpy()
        dy = (z_lat - lat) * 111.0
        dx = (z_lon - lon) * 111.0 * np.cos(np.radians(lat))
        dist = np.hypot(dx, dy)
        i = int(dist.argmin())
        if dist[i] > max_km:
            return None
        return {"zone_id": self.zones[i]["location_id"], "city": self.zones[i]["city"], "distance_km": round(float(dist[i]), 1)}

    def model_info(self):
        return self.bundle["metrics"]
