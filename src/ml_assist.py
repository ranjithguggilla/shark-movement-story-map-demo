"""
Offline QC-style anomaly scoring on synthetic demonstration tracks.

Uses engineered movement features only (segment length, gap, speed, turn proxy).
Does not infer biology or replace operational QA systems.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from .track_metrics import haversine_miles

MIN_SAMPLES_ISO = 15
RNG_SEED = 42


def _bearing_deg(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Initial bearing from point 1 to point 2 in degrees [0, 360)."""
    φ1 = np.radians(lat1)
    φ2 = np.radians(lat2)
    Δλ = np.radians(lon2 - lon1)
    x = np.sin(Δλ) * np.cos(φ2)
    y = np.cos(φ1) * np.sin(φ2) - np.sin(φ1) * np.cos(φ2) * np.cos(Δλ)
    θ = np.degrees(np.arctan2(x, y))
    return (θ + 360.0) % 360.0


def _angular_diff_deg(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return float(min(d, 360.0 - d))


def _feature_matrix(grp: pd.DataFrame) -> np.ndarray:
    """Rows aligned with sorted grp; first row uses neutral segment features."""
    g = grp.sort_values("ping_datetime").reset_index(drop=True)
    n = len(g)
    lat = g["latitude"].to_numpy(dtype=float)
    lon = g["longitude"].to_numpy(dtype=float)
    t = g["ping_datetime"]

    lat0 = g["latitude"].shift(1)
    lon0 = g["longitude"].shift(1)
    t0 = g["ping_datetime"].shift(1)
    step_mi = haversine_miles(lat0.to_numpy(), lon0.to_numpy(), lat, lon).astype(float)
    step_mi[0] = 0.0

    hours_gap = np.zeros(n, dtype=float)
    dt = (t - t0).dt.total_seconds() / 3600.0
    if n > 1:
        hours_gap[1:] = np.maximum(dt.iloc[1:].to_numpy(dtype=float), 0.0)

    speed = np.full(n, np.nan, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        spd = np.where(hours_gap > 0.05, step_mi / hours_gap, np.nan)
    speed[:] = spd

    med_spd = np.nanmedian(speed[np.isfinite(speed)])
    if not np.isfinite(med_spd):
        med_spd = 0.0
    speed_f = np.nan_to_num(speed, nan=med_spd)

    turn_deg = np.zeros(n, dtype=float)
    if n >= 3:
        b_in = _bearing_deg(lat[:-2], lon[:-2], lat[1:-1], lon[1:-1])
        b_out = _bearing_deg(lat[1:-1], lon[1:-1], lat[2:], lon[2:])
        for i in range(n - 2):
            turn_deg[i + 1] = _angular_diff_deg(float(b_in[i]), float(b_out[i]))

    shore = g["distance_from_shore_miles"].to_numpy(dtype=float)

    return np.column_stack(
        [
            np.log1p(np.maximum(step_mi, 0.0)),
            np.log1p(np.maximum(hours_gap, 0.0)),
            speed_f,
            turn_deg / 180.0,
            shore / 100.0,
        ]
    )


def _score_track_rows(grp: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Returns (anomaly_score_0_1_higher_is_weirder, qc_flag_bool)."""
    g = grp.sort_values("ping_datetime")
    X_raw = _feature_matrix(g)
    n = len(g)
    if n < 2:
        return np.zeros(n), np.zeros(n, dtype=bool)

    scaler = StandardScaler()
    X = scaler.fit_transform(X_raw)

    if n >= MIN_SAMPLES_ISO:
        iso = IsolationForest(random_state=RNG_SEED, contamination="auto", n_estimators=200)
        iso.fit(X)
        decision = iso.decision_function(X)
        pred = iso.predict(X)
        lo, hi = float(np.min(decision)), float(np.max(decision))
        if hi > lo:
            norm = (decision - lo) / (hi - lo)
        else:
            norm = np.ones_like(decision) * 0.5
        anomaly = 1.0 - norm
        flag = pred == -1
    else:
        Z = np.abs((X - np.mean(X, axis=0)) / (np.std(X, axis=0) + 1e-9))
        score_row = np.max(Z, axis=1)
        ano_max = float(np.max(score_row)) or 1.0
        anomaly = np.clip(score_row / ano_max, 0.0, 1.0)
        flag = score_row > np.percentile(score_row, 90)

    return anomaly.astype(float), flag


def apply_ml_assist(df: pd.DataFrame) -> pd.DataFrame:
    """
    Append ai_anomaly_score [0,1] (higher = more unusual on engineered features)
    and qc_flag_ml (bool). Rule-based metrics remain authoritative.
    """
    out = df.copy()
    scores = pd.Series(np.nan, index=out.index, dtype=float)
    flags = pd.Series(False, index=out.index)

    for _, grp in out.groupby("shark_id", sort=False):
        order = grp.sort_values("ping_datetime")
        s, f = _score_track_rows(order)
        scores.loc[order.index] = s
        flags.loc[order.index] = f

    out["ai_anomaly_score"] = scores.fillna(0.0)
    out["qc_flag_ml"] = flags.fillna(False)
    return out
