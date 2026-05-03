from __future__ import annotations

from pathlib import Path

import pandas as pd

from .track_metrics import SHARK_CARD_META, load_tracks, summarize_track_metrics


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "outputs"


def dominant_zone(series: pd.Series) -> str:
    if series.empty:
        return "mixed habitats"
    return str(series.mode().iloc[0])


def bearing_bucket(lat_start: float, lon_start: float, lat_end: float, lon_end: float) -> str:
    dlat = lat_end - lat_start
    dlon = lon_end - lon_start
    if abs(dlat) < 0.05 and abs(dlon) < 0.05:
        return "localized movements"
    if dlon > 0.08:
        return "eastward progression"
    if dlon < -0.08:
        return "westward progression"
    if dlat > 0.05:
        return "northward progression"
    if dlat < -0.05:
        return "southward progression"
    return "along-shelf transitions"


def build_journey_summary(shark_id: str, enriched: pd.DataFrame, metrics_row: pd.Series) -> str:
    grp = enriched[enriched["shark_id"] == shark_id].sort_values("ping_datetime")
    meta = SHARK_CARD_META.get(shark_id, {})
    start = grp.iloc[0]
    end = grp.iloc[-1]
    zone_mode = dominant_zone(grp["depth_zone"])
    habitat_mode = dominant_zone(grp["habitat_zone_label"])
    direction = bearing_bucket(start["latitude"], start["longitude"], end["latitude"], end["longitude"])
    tag_note = ""
    if (grp["tag_status"] == "inactive").any():
        tag_note = " The demo tag status includes an inactive phase to show how storytelling should handle sparse or ended transmissions."
    text = (
        f"Over about {int(metrics_row['track_duration_days'])} days, {grp.iloc[0]['shark_name']} "
        f"({grp.iloc[0]['species']}) shows {direction} in the Gulf with repeated use of {zone_mode} "
        f"zones and {habitat_mode} contexts (synthetic demonstration only). "
        f"Total movement in the demo track is roughly {metrics_row['total_distance_miles']:.0f} miles, "
        f"which helps communicate how tagged animals can link coastal and offshore areas in public-facing maps."
        f"{tag_note}"
    )
    if meta.get("tagged_near"):
        text = f"Tagged near {meta['tagged_near']}. {text}"
    return text


def write_sample_summaries(enriched: pd.DataFrame | None = None) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if enriched is None:
        enriched = load_tracks()
    metrics = summarize_track_metrics(enriched).set_index("shark_id")
    lines = ["# Sample journey summaries (synthetic demonstration)\n"]
    for shark_id in sorted(enriched["shark_id"].unique()):
        summary = build_journey_summary(shark_id, enriched, metrics.loc[shark_id])
        lines.append(f"## {shark_id}\n\n{summary}\n")
    path = OUTPUT_DIR / "sample_story_summary.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


if __name__ == "__main__":
    p = write_sample_summaries()
    print(p)
