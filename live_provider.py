"""
Real-time traffic from TomTom.

* Flow Segment Data: measured current vs free-flow speed at a zone's coordinates ->
  the same 0-100 congestion score the model uses. Fetched on demand per city (in
  parallel), cached 5 min, and logged to traffic_reading for future retraining.
* Flow tiles: a live traffic raster for the whole map, proxied through our backend
  so the API key never reaches the browser.

Enabled when TOMTOM_API_KEY is set (env var or .env). A daily request budget
(TOMTOM_DAILY_BUDGET, default 2,200 of the free 2,500) protects the quota; once it
is spent the app quietly falls back to ML estimates until IST midnight.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from config import TOMTOM_API_KEY, TOMTOM_DAILY_BUDGET, level_for, now_ist
from database import get_connection

FLOW_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
TILE_URL = "https://api.tomtom.com/traffic/map/4/tile/flow/relative0/{z}/{x}/{y}.png"
CACHE_SECONDS = 300
TILE_CACHE_SECONDS = 60
MIN_CONFIDENCE = 0.3  # ignore readings TomTom itself marks as unreliable

_cache = {}        # location_id -> (fetched_at, record)
_tile_cache = {}   # (z, x, y) -> (fetched_at, bytes)
_lock = threading.Lock()
_budget = {"day": None, "used": 0}
_version = [0]     # bumps whenever fresh live data is cached (invalidates the overview cache)


def enabled():
    return bool(TOMTOM_API_KEY)


def _spend(n=1):
    """Reserve n requests from today's budget; False when exhausted."""
    today = now_ist().date()
    with _lock:
        if _budget["day"] != today:
            _budget["day"], _budget["used"] = today, 0
        if _budget["used"] + n > TOMTOM_DAILY_BUDGET:
            return False
        _budget["used"] += n
        return True


def version():
    return _version[0]


def status():
    today = now_ist().date()
    used = _budget["used"] if _budget["day"] == today else 0
    return {"enabled": enabled(), "used_today": used, "daily_budget": TOMTOM_DAILY_BUDGET,
            "exhausted": enabled() and used >= TOMTOM_DAILY_BUDGET}


def speed_ratio_to_score(current, free_flow):
    """Map current/free-flow speed to the 0-100 congestion score used everywhere."""
    if not free_flow or free_flow <= 0:
        return None
    ratio = max(0.0, min(1.0, current / free_flow))
    return round(max(0.0, min(100.0, 120.0 * (1.0 - ratio))), 1)


def _fetch_one(zone):
    if not _spend():
        return None
    try:
        r = requests.get(FLOW_URL, params={"point": f"{zone['latitude']},{zone['longitude']}",
                                           "unit": "KMPH", "key": TOMTOM_API_KEY}, timeout=5)
        r.raise_for_status()
        d = r.json()["flowSegmentData"]
        if d.get("confidence", 1) < MIN_CONFIDENCE:
            return None
        score = speed_ratio_to_score(d["currentSpeed"], d["freeFlowSpeed"])
        if score is None:
            return None
        return {"score": score, "current_speed": d["currentSpeed"], "free_flow_speed": d["freeFlowSpeed"]}
    except Exception:
        return None


def cached(location_id):
    hit = _cache.get(location_id)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    return None


def refresh_zones(zones, precip_by_zone=None):
    """Fetch live flow for these zones (in parallel), cache + log to traffic_reading."""
    if not enabled():
        return {}
    todo = [z for z in zones if cached(z["location_id"]) is None]
    rows = []
    if todo:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for z, rec in zip(todo, ex.map(_fetch_one, todo)):
                if rec:
                    _cache[z["location_id"]] = (time.time(), rec)
                    _version[0] += 1
                    rows.append((z["location_id"], now_ist().strftime("%Y-%m-%d %H:%M:%S"), rec["score"],
                                 level_for(rec["score"]), rec["current_speed"], rec["free_flow_speed"],
                                 (precip_by_zone or {}).get(z["location_id"], 0.0), "tomtom"))
    if rows:
        conn = get_connection()
        conn.executemany("""INSERT INTO traffic_reading
            (location_id, reading_datetime, congestion_score, congestion_level,
             current_speed_kmph, free_flow_speed_kmph, precip_mm, source)
            VALUES (?,?,?,?,?,?,?,?)""", rows)
        conn.commit()
        conn.close()
    return {z["location_id"]: cached(z["location_id"]) for z in zones if cached(z["location_id"])}


def fetch_tile(z, x, y):
    """Live traffic flow PNG for a map tile (cached 60 s). Returns bytes or None."""
    if not enabled() or not (0 <= z <= 22) or not (0 <= x < 2 ** z) or not (0 <= y < 2 ** z):
        return None
    key = (z, x, y)
    hit = _tile_cache.get(key)
    if hit and time.time() - hit[0] < TILE_CACHE_SECONDS:
        return hit[1]
    try:
        r = requests.get(TILE_URL.format(z=z, x=x, y=y), params={"key": TOMTOM_API_KEY}, timeout=5)
        if r.status_code != 200:
            return None
        if len(_tile_cache) > 2000:
            _tile_cache.clear()
        _tile_cache[key] = (time.time(), r.content)
        return r.content
    except Exception:
        return None
