"""
Live weather + forecast from Open-Meteo (free, no API key).

All cities are fetched in a few batched requests by a background thread, so no
page request ever waits on the network.

Built to survive rate limiting (HTTP 429), which is common on shared cloud hosts
whose outgoing IP is used by many apps:
  * requests are spread out (a short pause between batches);
  * each batch succeeds or fails on its own - good batches are kept;
  * after a failure only the missing cities are retried, with growing delays
    (honouring Retry-After), instead of waiting for the next full refresh;
  * if there is still no data for a city, precipitation falls back to 0 (dry) and
    the UI is told the forecast is unavailable.
"""
import logging
import threading
import time
from datetime import datetime

import requests

log = logging.getLogger("saarthi.weather")
API = "https://api.open-meteo.com/v1/forecast"
CHUNK = 40                      # cities per request
CHUNK_PAUSE = 2.0               # seconds between requests in one refresh
REFRESH_SECONDS = 60 * 60       # hourly data only changes hourly
RETRY_SECONDS = (60, 120, 300, 600, 900)   # backoff after failures
MAX_WAIT = 900


def describe_error(exc):
    """Short, useful text for a failed request (status, Open-Meteo's stated reason, Retry-After)."""
    resp = getattr(exc, "response", None)
    if resp is None:
        return f"{type(exc).__name__}: {exc}"
    reason = None
    try:
        reason = resp.json().get("reason")
    except Exception:
        pass
    text = f"HTTP {resp.status_code}" + (f" - {reason}" if reason else "")
    if resp.headers.get("Retry-After"):
        text += f" (Retry-After {resp.headers['Retry-After']}s)"
    return text


def retry_after_seconds(exc):
    resp = getattr(exc, "response", None)
    try:
        return int(resp.headers.get("Retry-After")) if resp is not None else None
    except (TypeError, ValueError):
        return None


def next_wait(fails, retry_after=None):
    """Seconds to wait after `fails` consecutive failed attempts (0-based count before this one)."""
    wait = RETRY_SECONDS[min(fails, len(RETRY_SECONDS) - 1)]
    return min(max(wait, retry_after or 0), MAX_WAIT)


class WeatherService:
    def __init__(self, cities, on_refresh=None):
        """cities: list of (name, lat, lon); on_refresh is called after every attempt."""
        self.cities = cities
        self.on_refresh = on_refresh
        self._hourly = {}     # city -> {datetime(hour): precip_mm}
        self._current = {}    # city -> {"temp": .., "precip": ..}
        self.version = 0      # bumps whenever new data arrives (cache key for forecasts)
        self.last_ok = None
        self.last_error = None
        self._retry_after = None
        self._lock = threading.Lock()
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._loop, daemon=True, name="weather-refresh").start()

    def _loop(self):
        fails, todo = 0, None
        while True:
            try:
                failed = self.refresh(todo)
            except Exception as exc:  # never let the thread die
                log.warning("weather refresh crashed: %s", exc)
                failed = [c[0] for c in (todo or self.cities)]
            todo = [c for c in self.cities if c[0] in set(failed)] or None   # retry only what is missing
            if self.on_refresh:
                try:
                    self.on_refresh()
                except Exception as exc:
                    log.warning("post-refresh warm-up failed: %s", exc)
            if failed:
                wait = next_wait(fails, self._retry_after)
                fails += 1
                log.warning("weather incomplete (%d/%d cities missing); retrying in %ds", len(failed), len(self.cities), wait)
            else:
                fails, wait = 0, REFRESH_SECONDS
            time.sleep(wait)

    def _fetch(self, chunk):
        r = requests.get(API, params={
            "latitude": ",".join(str(c[1]) for c in chunk),
            "longitude": ",".join(str(c[2]) for c in chunk),
            "hourly": "precipitation",
            "current": "temperature_2m,precipitation",
            "forecast_days": 7, "past_days": 1, "timezone": "Asia/Kolkata",
        }, timeout=20)
        r.raise_for_status()
        data = r.json()
        return [data] if isinstance(data, dict) else data   # single location -> dict, several -> list

    def refresh(self, cities=None):
        """Fetch `cities` (default all). Keeps whatever succeeds; returns the names of cities that failed."""
        cities = self.cities if cities is None else cities
        hourly, current, failed = {}, {}, []
        self._retry_after = None
        for n, i in enumerate(range(0, len(cities), CHUNK)):
            chunk = cities[i:i + CHUNK]
            if n:
                time.sleep(CHUNK_PAUSE)
            try:
                for (name, _, _), d in zip(chunk, self._fetch(chunk)):
                    times, vals = d["hourly"]["time"], d["hourly"]["precipitation"]
                    hourly[name] = {datetime.fromisoformat(t): float(v or 0.0) for t, v in zip(times, vals)}
                    cur = d.get("current", {})
                    current[name] = {"temp": cur.get("temperature_2m"), "precip": cur.get("precipitation")}
            except Exception as exc:
                failed.extend(c[0] for c in chunk)
                self.last_error = describe_error(exc)
                self._retry_after = retry_after_seconds(exc) or self._retry_after
                log.warning("weather request failed for %d cities: %s", len(chunk), self.last_error)
        if hourly:
            with self._lock:
                self._hourly.update(hourly)      # cities that failed keep their previous data
                self._current.update(current)
                self.version += 1
                self.last_ok = datetime.now()
            if not failed:
                self.last_error = None
        return failed

    @property
    def available(self):
        return bool(self._hourly)

    def status(self):
        return {"live": self.available, "cities": len(self._hourly), "of": len(self.cities),
                "last_ok": self.last_ok.isoformat(timespec="seconds") if self.last_ok else None,
                "last_error": self.last_error}

    def precip(self, city, dt):
        """Precipitation (mm/h) for the hour containing `dt`; (value, is_forecast_known)."""
        h = self._hourly.get(city)
        if not h:
            return 0.0, False
        key = dt.replace(minute=0, second=0, microsecond=0)
        if key in h:
            return h[key], True
        return 0.0, False

    def current(self, city):
        return self._current.get(city, {"temp": None, "precip": None})
