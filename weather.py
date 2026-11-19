"""
Live weather + forecast from Open-Meteo (free, no API key).

All cities are fetched in a few batched requests by a background thread, so no
page request ever waits on the network. If the API is unreachable the last good
data is kept; if there never was any, precipitation falls back to 0 (dry) and
the UI is told weather is unavailable.
"""
import logging
import threading
import time
from datetime import datetime

import requests

log = logging.getLogger("saarthi.weather")
API = "https://api.open-meteo.com/v1/forecast"
CHUNK = 40
REFRESH_SECONDS = 30 * 60


class WeatherService:
    def __init__(self, cities, on_refresh=None):
        """cities: list of (name, lat, lon); on_refresh is called after every attempt."""
        self.cities = cities
        self.on_refresh = on_refresh
        self._hourly = {}     # city -> {datetime(hour): precip_mm}
        self._current = {}    # city -> {"temp": .., "precip": ..}
        self.version = 0      # bumps on every successful refresh (cache key for forecasts)
        self.last_ok = None
        self._lock = threading.Lock()
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._loop, daemon=True, name="weather-refresh").start()

    def _loop(self):
        while True:
            try:
                self.refresh()
            except Exception as exc:  # never let the thread die
                log.warning("weather refresh failed: %s", exc)
            if self.on_refresh:
                try:
                    self.on_refresh()
                except Exception as exc:
                    log.warning("post-refresh warm-up failed: %s", exc)
            time.sleep(REFRESH_SECONDS)

    def refresh(self):
        hourly, current = {}, {}
        for i in range(0, len(self.cities), CHUNK):
            chunk = self.cities[i:i + CHUNK]
            r = requests.get(API, params={
                "latitude": ",".join(str(c[1]) for c in chunk),
                "longitude": ",".join(str(c[2]) for c in chunk),
                "hourly": "precipitation",
                "current": "temperature_2m,precipitation",
                "forecast_days": 7, "past_days": 1, "timezone": "Asia/Kolkata",
            }, timeout=20)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict):  # single location -> dict, several -> list
                data = [data]
            for (name, _, _), d in zip(chunk, data):
                times = d["hourly"]["time"]
                vals = d["hourly"]["precipitation"]
                hourly[name] = {datetime.fromisoformat(t): float(v or 0.0) for t, v in zip(times, vals)}
                cur = d.get("current", {})
                current[name] = {"temp": cur.get("temperature_2m"), "precip": cur.get("precipitation")}
        with self._lock:
            self._hourly, self._current = hourly, current
            self.version += 1
            self.last_ok = datetime.now()

    @property
    def available(self):
        return bool(self._hourly)

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
