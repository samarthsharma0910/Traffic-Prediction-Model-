"""
Feature engineering shared by training and serving, so they can never drift.

The model forecasts from *knowable-in-advance* inputs only: where (zone), when
(hour/day/month/holiday) and weather (precipitation). It deliberately does NOT
use vehicle counts or speeds - those are consequences of congestion, so using
them would leak the answer and make future prediction impossible.
"""
import math

import holidays as _holidays
import numpy as np
import pandas as pd

FEATURES = [
    "hour", "hour_sin", "hour_cos", "dow", "is_weekend", "month", "is_holiday",
    "precip_mm", "lat", "lon", "log_pop", "city_code", "kind_code",
]
CATEGORICAL = ["city_code", "kind_code"]
CAT_MASK = [f in CATEGORICAL for f in FEATURES]

_HOLIDAY_DATES = None


def holiday_dates():
    global _HOLIDAY_DATES
    if _HOLIDAY_DATES is None:
        h = _holidays.India(years=range(2023, 2032))
        _HOLIDAY_DATES = pd.DatetimeIndex(sorted(pd.Timestamp(d) for d in h.keys()))
    return _HOLIDAY_DATES


def holiday_name(date):
    return _holidays.India(years=[date.year]).get(date)


def zone_columns(zones, city_index, kind_index):
    """Static per-zone numeric columns, in the order of `zones`."""
    return pd.DataFrame({
        "lat": [z["latitude"] for z in zones],
        "lon": [z["longitude"] for z in zones],
        "log_pop": [math.log1p(z["population_m"]) for z in zones],
        "city_code": [city_index[z["city"]] for z in zones],
        "kind_code": [kind_index[z["zone_kind"]] for z in zones],
    })


def make_features(static, ts, precip):
    """
    static : DataFrame of zone_columns, one row per sample
    ts     : DatetimeIndex (IST wall-clock), one per sample
    precip : array of precipitation in mm/h, one per sample
    """
    ts = pd.DatetimeIndex(ts)
    hour = (ts.hour + ts.minute / 60.0).to_numpy(dtype=np.float32)
    dow = ts.dayofweek.to_numpy()
    out = pd.DataFrame({
        "hour": hour,
        "hour_sin": np.sin(2 * np.pi * hour / 24).astype(np.float32),
        "hour_cos": np.cos(2 * np.pi * hour / 24).astype(np.float32),
        "dow": dow.astype(np.int8),
        "is_weekend": (dow >= 5).astype(np.int8),
        "month": ts.month.to_numpy().astype(np.int8),
        "is_holiday": ts.normalize().isin(holiday_dates()).astype(np.int8),
        "precip_mm": np.asarray(precip, dtype=np.float32),
    })
    for c in ["lat", "lon", "log_pop"]:
        out[c] = static[c].to_numpy(dtype=np.float32)
    for c in CATEGORICAL:
        out[c] = static[c].to_numpy(dtype=np.int16)
    return out[FEATURES]
