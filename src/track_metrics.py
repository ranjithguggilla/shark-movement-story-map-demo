from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"

# Synthetic demo-only card fields (public-safe placeholders).
SHARK_CARD_META = {
    "SHK-001": {"sex": "F", "fork_length_cm": 285, "tagged_near": "Port Aransas, TX"},
    "SHK-002": {"sex": "M", "fork_length_cm": 320, "tagged_near": "Port Aransas, TX"},
    "SHK-003": {"sex": "M", "fork_length_cm": 265, "tagged_near": "Galveston, TX"},
    "SHK-004": {"sex": "F", "fork_length_cm": 178, "tagged_near": "South Padre Island, TX"},
    "SHK-005": {"sex": "F", "fork_length_cm": 225, "tagged_near": "Corpus Christi, TX"},
}

# Approximate Gulf coast polyline for demo distance-from-shore (degrees WGS84).
_COAST_XY = np.array(
    [
        [-97.35, 27.65],
        [-97.05, 27.85],
        [-96.55, 28.15],
        [-95.85, 28.65],
        [-94.85, 29.05],
        [-93.55, 29.55],
        [-92.10, 29.85],
        [-90.50, 29.95],
        [-88.80, 29.95],
        [-87.00, 29.85],
    ]
)


def haversine_miles(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    r = 3958.7613  # Earth radius miles
    p = math.pi / 180.0
    a = 0.5 - np.cos((lat2 - lat1) * p) / 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * (1 - np.cos((lon2 - lon1) * p)) / 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _nearest_coast_distance_miles(lat: float, lon: float) -> float:
    dists = haversine_miles(
        np.full(len(_COAST_XY), lat),
        np.full(len(_COAST_XY), lon),
        _COAST_XY[:, 1],
        _COAST_XY[:, 0],
    )
    return float(np.min(dists))


def load_tracks() -> pd.DataFrame:
    path = DATA_DIR / "synthetic_shark_tracks.csv"
    df = pd.read_csv(path)
    df["ping_datetime"] = pd.to_datetime(df["ping_datetime"], errors="coerce")
    df = df.dropna(subset=["ping_datetime", "latitude", "longitude"])
    df = df.sort_values(["shark_id", "ping_datetime"]).reset_index(drop=True)
    enriched = enrich_tracks(df)
    # Lazy import avoids circular dependency with ml_assist (which uses haversine from this module).
    from .ml_assist import apply_ml_assist

    return apply_ml_assist(enriched)


def enrich_tracks(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    shore = []
    depth_zones = []
    temps = []
    regions = []
    habitat = []
    for _, row in out.iterrows():
        d_shore = _nearest_coast_distance_miles(row["latitude"], row["longitude"])
        shore.append(round(d_shore, 2))
        if d_shore < 15:
            dz = "nearshore"
        elif d_shore < 60:
            dz = "mid-shelf"
        else:
            dz = "offshore"
        depth_zones.append(dz)
        # Synthetic temperature placeholder (not environmental reanalysis).
        temp = 22.0 + (28.5 - row["latitude"]) * 0.35 + min(d_shore, 120) * 0.012
        temps.append(round(float(temp), 1))
        lon = row["longitude"]
        if lon < -93:
            regions.append("Western Gulf")
        elif lon < -89:
            regions.append("Central Gulf")
        else:
            regions.append("Eastern Gulf")
        if d_shore < 20:
            habitat.append("near coastal / bay entrance")
        elif dz == "mid-shelf":
            habitat.append("continental shelf")
        else:
            habitat.append("offshore shelf / blue water transition")

    out["distance_from_shore_miles"] = shore
    out["depth_zone"] = depth_zones
    out["temperature_c_estimate"] = temps
    out["gulf_region"] = regions
    out["habitat_zone_label"] = habitat

    seg_dist = []
    seg_speed = []
    for sid, grp in out.groupby("shark_id", sort=False):
        lat0 = grp["latitude"].shift(1)
        lon0 = grp["longitude"].shift(1)
        t0 = grp["ping_datetime"].shift(1)
        dmi = haversine_miles(lat0.to_numpy(), lon0.to_numpy(), grp["latitude"].to_numpy(), grp["longitude"].to_numpy())
        dmi = np.where(np.isnan(dmi), 0.0, dmi)
        hours = (grp["ping_datetime"] - t0).dt.total_seconds() / 3600.0
        hours = hours.replace(0, np.nan)
        mph = np.where(hours.notna() & (hours > 0.1), dmi / hours, np.nan)
        seg_dist.extend(dmi.tolist())
        seg_speed.extend(mph.tolist())
    out["distance_since_last_ping_miles"] = [round(float(x), 2) if pd.notna(x) else 0.0 for x in seg_dist]
    out["avg_speed_mph_since_last_ping"] = [round(float(x), 2) if pd.notna(x) else np.nan for x in seg_speed]
    return out


def summarize_track_metrics(enriched: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for shark_id, grp in enriched.groupby("shark_id"):
        grp = grp.sort_values("ping_datetime")
        cum = grp["distance_since_last_ping_miles"].sum()
        dur_days = (grp["ping_datetime"].max() - grp["ping_datetime"].min()).days + 1
        grp_day = grp.assign(day=grp["ping_datetime"].dt.date)
        daily = grp_day.groupby("day")["distance_since_last_ping_miles"].sum()
        max_daily = float(daily.max()) if len(daily) else 0.0
        speeds = grp["avg_speed_mph_since_last_ping"].dropna()
        avg_speed = float(speeds.mean()) if len(speeds) else 0.0
        near_pct = float((grp["distance_from_shore_miles"] < 25).mean() * 100)
        rows.append(
            {
                "shark_id": shark_id,
                "total_distance_miles": round(float(cum), 1),
                "max_daily_distance": round(max_daily, 1),
                "avg_speed_mph": round(avg_speed, 2),
                "track_duration_days": int(dur_days),
                "nearshore_percent": round(near_pct, 1),
            }
        )
    return pd.DataFrame(rows).sort_values("shark_id")


def write_track_metrics_csv(enriched: pd.DataFrame | None = None) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if enriched is None:
        enriched = load_tracks()
    metrics = summarize_track_metrics(enriched)
    path = OUTPUT_DIR / "track_metrics.csv"
    metrics.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    write_track_metrics_csv()

