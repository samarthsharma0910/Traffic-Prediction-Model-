"""
Synthetic historical traffic generator used to train the model.

IMPORTANT: no public hour-by-hour congestion dataset exists for Indian zones, so
history is simulated from documented *qualitative* patterns (bigger cities are
more congested; Bengaluru/Pune/Mumbai/Kolkata/Hyderabad are the worst; Indian
peaks are ~9-11h and ~17:30-21h; weekends/holidays are lighter; rain makes
things worse). It is vectorised, so ~2.5M rows are generated in seconds.
Replace/augment it with real data via collect_live.py (see README).
"""
import numpy as np
import pandas as pd

from features import holiday_dates, make_features, zone_columns

# Extra congestion intensity for cities known to be worse than their size suggests.
CITY_BIAS = {"Bengaluru": 10, "Pune": 8, "Mumbai": 5, "Kolkata": 5, "Hyderabad": 4,
             "Chennai": 2, "Jaipur": 3, "Delhi": 0, "Shimla": 6, "Gangtok": 6, "Kochi": 4}
FLOOD_PRONE = {"Mumbai", "Chennai", "Kolkata", "Bengaluru", "Hyderabad", "Guwahati",
               "Thiruvananthapuram", "Kochi", "Thane", "Surat"}
KIND_GAIN = {"CBD": 1.10, "Railway Station": 0.95, "Market Area": 1.0, "Ring Road": 0.90,
             "Highway Bypass": 0.75, "Residential Arterial": 0.85, "IT / Business Park": 1.05,
             "Airport Corridor": 0.70, "Old City": 1.0, "University / Hospital": 0.80}


def _g(h, mu, sigma):
    return np.exp(-0.5 * ((h - mu) / sigma) ** 2)


def _profile(kind, h, off_day):
    """0..~1.1 demand profile for hour array `h`; `off_day` = weekend or holiday."""
    commute_wd = 0.85 * _g(h, 9.7, 1.4) + 1.0 * _g(h, 18.8, 1.8)
    if kind == "CBD":
        p = np.where(off_day, 0.5 * _g(h, 12, 3) + 0.7 * _g(h, 18.5, 2.2),
                     0.8 * _g(h, 9.7, 1.5) + 1.0 * _g(h, 18.8, 2.0) + 0.45 * _g(h, 14, 3.5))
    elif kind == "Railway Station":
        p = np.where(off_day, 0.6 * _g(h, 10, 2.5) + 0.8 * _g(h, 18, 2.5),
                     0.9 * _g(h, 8.5, 1.3) + 1.0 * _g(h, 18.5, 1.8) + 0.3 * _g(h, 13, 4))
    elif kind == "Market Area":
        p = np.where(off_day, 0.75 * _g(h, 12.5, 2.8) + 1.0 * _g(h, 19, 2.5),
                     0.5 * _g(h, 12, 2.5) + 0.9 * _g(h, 18.8, 2.2))
    elif kind == "Ring Road":
        p = np.where(off_day, 0.5 * _g(h, 11, 3) + 0.6 * _g(h, 18, 3), 0.9 * commute_wd)
    elif kind == "Highway Bypass":
        trucks = 0.55 * (_g(h, 23, 2.0) + _g(h, 2, 2.2) + _g(h, 25, 2.0))
        p = np.where(off_day, 0.25 * commute_wd + trucks, 0.45 * commute_wd + trucks)
    elif kind == "Residential Arterial":
        p = np.where(off_day, 0.4 * _g(h, 10, 2) + 0.5 * _g(h, 19, 2.5),
                     1.0 * _g(h, 8.8, 1.2) + 0.8 * _g(h, 19.3, 1.6))
    elif kind == "IT / Business Park":
        p = np.where(off_day, 0.10 * _g(h, 12, 4),
                     1.0 * _g(h, 9.0, 1.0) + 1.0 * _g(h, 18.5, 1.3) + 0.25 * _g(h, 22, 1.5))
    elif kind == "Airport Corridor":
        p = (0.5 * _g(h, 6.5, 2) + 0.7 * _g(h, 21.5, 2.5) + 0.35 * _g(h, 14, 4)) * np.where(off_day, 0.9, 1.0)
    elif kind == "Old City":
        p = 0.9 * _g(h, 13, 4.2) + 0.45 * _g(h, 19, 2.2)
    else:  # University / Hospital
        p = np.where(off_day, 0.35 * _g(h, 11, 2.5), 0.9 * _g(h, 10, 1.8) + 0.6 * _g(h, 16.5, 1.8))
    return np.clip(p, 0, 1.15)


def _wet_day_prob(lat, lon, month):
    if 6 <= month <= 9:  # south-west monsoon
        if lon < 77 and lat < 20:
            return 0.70
        if lon > 88.5:
            return 0.65
        if lon < 75 and lat >= 22:
            return 0.30
        if lat < 12 and lon > 78:  # Tamil Nadu interior: rain shadow
            return 0.22
        return 0.50
    if 10 <= month <= 12:  # north-east monsoon over the south-east coast
        if lat < 15 and lon > 78:
            return 0.45 if month < 12 else 0.30
        return 0.06
    if 3 <= month <= 5:
        return 0.30 if (lat < 10 or lon > 88.5) else 0.08
    return 0.07


def city_intensity(city, pop_m):
    return 38 + 8 * np.log2(pop_m + 0.6) + CITY_BIAS.get(city, 0)


def simulate_weather(cities, ts, seed):
    """Hourly precipitation (mm) per city: returns {city: array(len(ts))}."""
    rng = np.random.default_rng(seed)
    days = ts.normalize()
    uniq_days = days.unique()
    day_pos = np.searchsorted(uniq_days, days)
    out = {}
    for city, lat, lon in cities:
        p_wet = np.array([_wet_day_prob(lat, lon, m) for m in uniq_days.month])
        wet_day = rng.random(len(uniq_days)) < p_wet
        raining = wet_day[day_pos] & (rng.random(len(ts)) < 0.35)
        amount = rng.exponential(3.5, len(ts))
        out[city] = np.where(raining, amount, 0.0).astype(np.float32)
    return out


def simulate(zones, city_index, kind_index, end_date, days=150, seed=42):
    """
    Returns a DataFrame with FEATURES columns + `score` (+ `ts`, `zone_idx`),
    one row per zone per hour for `days` days ending (exclusive) at `end_date`.
    """
    rng = np.random.default_rng(seed)
    ts = pd.date_range(end=pd.Timestamp(end_date) - pd.Timedelta(hours=1), periods=days * 24, freq="h")
    T, Z = len(ts), len(zones)
    h = ts.hour.to_numpy(dtype=np.float32)
    dow = ts.dayofweek.to_numpy()
    month = ts.month.to_numpy()
    is_hol = ts.normalize().isin(holiday_dates())
    off_day = (dow >= 5) | is_hol

    cities = sorted({z["city"] for z in zones})
    first = {z["city"]: z for z in zones}
    weather = simulate_weather([(c, first[c]["latitude"], first[c]["longitude"]) for c in cities], ts, seed + 1)

    city_shock = {c: rng.normal(0, 3.0, (ts.normalize().nunique(),)) for c in cities}
    day_pos = np.searchsorted(ts.normalize().unique(), ts.normalize())

    scores = np.empty((Z, T), dtype=np.float32)
    precip = np.empty((Z, T), dtype=np.float32)
    for zi, z in enumerate(zones):
        c, kind = z["city"], z["zone_kind"]
        inten = city_intensity(c, z["population_m"]) * KIND_GAIN[kind]
        prof = _profile(kind, h, off_day)
        zone_offset = rng.normal(0, 5.0)
        p = weather[c]
        rain = np.where(p > 0.1, np.minimum(26, 4 + 5 * np.sqrt(p)), 0.0)
        rain *= (0.5 + 0.8 * np.minimum(1.0, prof)) * (1.35 if c in FLOOD_PRONE else 1.0)
        festive = np.where((kind == "Market Area") & (month >= 10), 3.0, 0.0)
        festive += np.where((kind == "Market Area") & is_hol, 0.15 * inten, 0.0)
        s = (5 + 0.10 * inten + inten * prof + rain + festive + zone_offset
             + city_shock[c][day_pos] * (0.4 + prof)
             + rng.normal(0, 3.5, T))
        scores[zi] = np.clip(s, 0, 100)
        precip[zi] = p

    static = zone_columns(zones, city_index, kind_index)
    static_rep = static.loc[np.repeat(np.arange(Z), T)].reset_index(drop=True)
    ts_rep = pd.DatetimeIndex(np.tile(ts.to_numpy(), Z))
    X = make_features(static_rep, ts_rep, precip.reshape(-1))
    X["score"] = scores.reshape(-1)
    X["ts"] = ts_rep
    X["zone_idx"] = np.repeat(np.arange(Z), T).astype(np.int16)
    return X
