"""Shared constants for the Traffic Management India system."""
import os
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(path):
    """Minimal .env loader (KEY=VALUE lines). Real environment variables win over the file."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


_load_dotenv(os.path.join(BASE_DIR, ".env"))
DB_PATH = os.path.join(BASE_DIR, "TrafficManagementDB.sqlite")
MODEL_DIR = os.path.join(BASE_DIR, "models")

# India has a single timezone with no DST, so a fixed offset is exact
# (and avoids needing the tzdata package on Windows).
IST = timezone(timedelta(hours=5, minutes=30))

# Optional real live-traffic source (TomTom). Without a key the app serves ML-estimated status.
# TRAFFIC_DISABLE_LIVE=1 turns it off even if a key is configured (used by the tests).
TOMTOM_API_KEY = "" if os.environ.get("TRAFFIC_DISABLE_LIVE") else os.environ.get("TOMTOM_API_KEY", "").strip()
# TomTom's free tier is 2,500 non-tile requests/day; stay safely under it.
TOMTOM_DAILY_BUDGET = int(os.environ.get("TOMTOM_DAILY_BUDGET", "2200"))

# Congestion score (0-100) -> level. Single source of truth for UI, API and training.
LEVELS = ["Low", "Moderate", "Heavy", "Severe"]
LEVEL_THRESHOLDS = (30.0, 55.0, 75.0)  # upper bounds of Low, Moderate, Heavy


def level_for(score):
    if score < LEVEL_THRESHOLDS[0]:
        return "Low"
    if score < LEVEL_THRESHOLDS[1]:
        return "Moderate"
    if score < LEVEL_THRESHOLDS[2]:
        return "Heavy"
    return "Severe"


def now_ist():
    return datetime.now(IST).replace(tzinfo=None)  # naive IST wall-clock time
