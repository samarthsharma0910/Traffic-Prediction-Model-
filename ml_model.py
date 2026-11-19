"""
Train / load / run the traffic forecasting model.

Three gradient-boosted regressors share one feature set:
  * mean  -> expected congestion score (0-100)
  * lo/hi -> 10th / 90th percentile, i.e. an 80% prediction interval
Congestion level and rush-hour windows are derived from the score, so every
number the UI shows is consistent with every other.

Validation is a strict *time-based* split (last 28 days held out) - a random
split would leak neighbouring hours of the same day into the test set.
"""
import json
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

from config import LEVEL_THRESHOLDS, MODEL_DIR, now_ist
from features import CAT_MASK, FEATURES
from traffic_sim import simulate

BUNDLE_PATH = os.path.join(MODEL_DIR, "traffic_model.joblib")
METRICS_PATH = os.path.join(MODEL_DIR, "metrics.json")


def _fit(loss, quantile=None, max_iter=300):
    kw = dict(loss=loss, max_iter=max_iter, learning_rate=0.1, max_leaf_nodes=63,
              min_samples_leaf=100, l2_regularization=1.0, categorical_features=CAT_MASK,
              early_stopping=True, validation_fraction=0.1, n_iter_no_change=15, random_state=42)
    if quantile is not None:
        kw["quantile"] = quantile
    return HistGradientBoostingRegressor(**kw)


def _levels(a):
    return np.digitize(a, LEVEL_THRESHOLDS)


def train(zones, days=400, test_days=28, seed=42, verbose=True):
    os.makedirs(MODEL_DIR, exist_ok=True)
    t0 = time.time()
    city_index = {c: i for i, c in enumerate(sorted({z["city"] for z in zones}))}
    kind_index = {k: i for i, k in enumerate(sorted({z["zone_kind"] for z in zones}))}
    end = pd.Timestamp(now_ist().date())
    df = simulate(zones, city_index, kind_index, end, days=days, seed=seed)
    if verbose:
        print(f"[data] {len(df):,} rows, {len(zones)} zones, {len(city_index)} cities, {df.ts.min()} -> {df.ts.max()}")

    cut = end - pd.Timedelta(days=test_days)
    tr, te = df[df.ts < cut], df[df.ts >= cut]
    Xtr, ytr, Xte, yte = tr[FEATURES], tr["score"].to_numpy(), te[FEATURES], te["score"].to_numpy()

    if verbose:
        print(f"[train] train={len(tr):,} test={len(te):,} (held-out last {test_days} days)")
    mean = _fit("squared_error").fit(Xtr, ytr)
    lo = _fit("quantile", 0.10, 200).fit(Xtr, ytr)
    hi = _fit("quantile", 0.90, 200).fit(Xtr, ytr)

    p = np.clip(mean.predict(Xte), 0, 100)
    plo, phi = np.minimum(np.clip(lo.predict(Xte), 0, 100), p), np.maximum(np.clip(hi.predict(Xte), 0, 100), p)

    # Baseline a non-ML system would use: historical average per zone x weekday x hour.
    base = tr.groupby(["zone_idx", "dow", "hour"])["score"].mean().rename("b")
    bp = te.join(base, on=["zone_idx", "dow", "hour"])["b"].fillna(ytr.mean()).to_numpy()

    # Peak-hour accuracy: does the predicted busiest hour of a zone-day land within 1h of the real one?
    n_zone = df.zone_idx.nunique()
    n_hours = len(te) // n_zone
    A = yte.reshape(n_zone, n_hours // 24, 24)
    P = p.reshape(n_zone, n_hours // 24, 24)
    diff = np.abs(A.argmax(2) - P.argmax(2))
    peak_ok = float(np.mean(np.minimum(diff, 24 - diff) <= 1))

    rainy = te["precip_mm"].to_numpy() > 0.1
    metrics = {
        "trained_at": now_ist().strftime("%Y-%m-%d %H:%M"),
        "train_rows": int(len(tr)), "test_rows": int(len(te)), "zones": len(zones), "cities": len(city_index),
        "test_window_days": test_days,
        "mae": round(float(mean_absolute_error(yte, p)), 2),
        "rmse": round(float(np.sqrt(np.mean((yte - p) ** 2))), 2),
        "r2": round(float(r2_score(yte, p)), 4),
        "baseline_mae": round(float(mean_absolute_error(yte, bp)), 2),
        "baseline_mae_rainy": round(float(mean_absolute_error(yte[rainy], bp[rainy])), 2),
        "mae_rainy": round(float(mean_absolute_error(yte[rainy], p[rainy])), 2),
        "level_accuracy": round(float(np.mean(_levels(yte) == _levels(p))), 4),
        "level_within_one": round(float(np.mean(np.abs(_levels(yte) - _levels(p)) <= 1)), 4),
        "interval_80_coverage": round(float(np.mean((yte >= plo) & (yte <= phi))), 4),
        "peak_hour_within_1h": round(peak_ok, 4),
        "data_source": "synthetic (calibrated simulator) - see README",
        "train_seconds": round(time.time() - t0, 1),
    }
    bundle = {"mean": mean, "lo": lo, "hi": hi, "city_index": city_index, "kind_index": kind_index, "metrics": metrics}
    joblib.dump(bundle, BUNDLE_PATH, compress=3)
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    if verbose:
        print(json.dumps(metrics, indent=2))
    return bundle


def load_bundle():
    return joblib.load(BUNDLE_PATH)


def predict(bundle, X):
    """X: FEATURES DataFrame -> (mean, lo, hi) arrays clipped to 0..100."""
    m = np.clip(bundle["mean"].predict(X), 0, 100)
    lo = np.minimum(np.clip(bundle["lo"].predict(X), 0, 100), m)
    hi = np.maximum(np.clip(bundle["hi"].predict(X), 0, 100), m)
    return m, lo, hi


if __name__ == "__main__":
    from database import load_zones
    train(load_zones())
