from __future__ import annotations

import pandas as pd

REQUIRED_COLS = ["shark_id", "shark_name", "species", "ping_datetime", "latitude", "longitude", "location_quality", "tag_status"]


def validate_tracks(df: pd.DataFrame) -> pd.DataFrame:
    issues: list[dict] = []
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        issues.append({"severity": "high", "category": "schema", "record_id": "-", "message": f"Missing columns: {missing}"})
        return pd.DataFrame(issues)

    dup_cols = ["shark_id", "ping_datetime", "latitude", "longitude"]
    dupes = df[df.duplicated(subset=dup_cols, keep=False)]
    for idx, row in dupes.iterrows():
        issues.append(
            {"severity": "low", "category": "duplicate_ping", "record_id": row["shark_id"], "message": f"Duplicate ping rows at index {idx}"}
        )

    bad_lat = df[(df["latitude"] < -90) | (df["latitude"] > 90)]
    for _, row in bad_lat.iterrows():
        issues.append({"severity": "high", "category": "coordinates", "record_id": row["shark_id"], "message": "Latitude out of range"})

    bad_lon = df[(df["longitude"] < -180) | (df["longitude"] > 180)]
    for _, row in bad_lon.iterrows():
        issues.append({"severity": "high", "category": "coordinates", "record_id": row["shark_id"], "message": "Longitude out of range"})

    for shark_id, grp in df.groupby("shark_id"):
        grp = grp.sort_values("ping_datetime")
        if not grp["ping_datetime"].is_monotonic_increasing:
            issues.append({"severity": "medium", "category": "time_order", "record_id": shark_id, "message": "Ping timestamps not monotonic"})
        latd = grp["latitude"].diff().abs()
        lond = grp["longitude"].diff().abs()
        huge = (latd > 2.5) | (lond > 2.5)
        if huge.any():
            issues.append({"severity": "medium", "category": "jump", "record_id": shark_id, "message": "Possible impossible movement step in demo track"})

    if not issues:
        return pd.DataFrame(columns=["severity", "category", "record_id", "message"])
    return pd.DataFrame(issues)
