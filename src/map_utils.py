from __future__ import annotations

import folium
import pandas as pd
from branca.colormap import LinearColormap


def subset_tracks_through_day(tracks: pd.DataFrame, track_start: pd.Timestamp, day_index: int) -> pd.DataFrame:
    """day_index 1 = first 24h from track_start, etc."""
    cutoff = track_start + pd.Timedelta(days=day_index)
    return tracks[tracks["ping_datetime"] <= cutoff]


def filter_tracks(
    df: pd.DataFrame,
    species: list[str] | None = None,
    months: list[int] | None = None,
    min_distance: float | None = None,
    max_distance: float | None = None,
    shore_filter: str | None = None,
    tag_status: str | None = None,
    metrics: pd.DataFrame | None = None,
) -> pd.DataFrame:
    out = df.copy()
    if species:
        out = out[out["species"].isin(species)]
    if months:
        out = out[out["ping_datetime"].dt.month.isin(months)]
    if tag_status and tag_status != "all":
        out = out[out["tag_status"] == tag_status]
    if shore_filter == "nearshore":
        out = out[out["distance_from_shore_miles"] < 25]
    elif shore_filter == "offshore":
        out = out[out["distance_from_shore_miles"] >= 25]
    if metrics is not None:
        if min_distance is not None:
            mids = metrics[metrics["total_distance_miles"] >= min_distance]["shark_id"]
            out = out[out["shark_id"].isin(mids)]
        if max_distance is not None:
            mids = metrics[metrics["total_distance_miles"] <= max_distance]["shark_id"]
            out = out[out["shark_id"].isin(mids)]
    return out


def build_story_map(
    shark_df: pd.DataFrame,
    center: tuple[float, float] | None = None,
    zoom_start: int = 5,
    highlight_shark_id: str | None = None,
    ml_overlay: bool = False,
    anomaly_col: str = "ai_anomaly_score",
) -> folium.Map:
    if shark_df.empty:
        fmap = folium.Map(location=[27.8, -90.0], zoom_start=4, tiles="CartoDB positron")
        return fmap
    if center is None:
        center = (shark_df["latitude"].mean(), shark_df["longitude"].mean())
    fmap = folium.Map(location=list(center), zoom_start=zoom_start, tiles="CartoDB positron")

    palette = ["#1d3557", "#e63946", "#2a9d8f", "#f4a261", "#8338ec"]
    shark_ids = list(shark_df["shark_id"].unique())
    color_map = {sid: palette[i % len(palette)] for i, sid in enumerate(sorted(shark_ids))}

    use_ml = ml_overlay and anomaly_col in shark_df.columns and not shark_df[anomaly_col].isna().all()
    if use_ml:
        vmin = float(shark_df[anomaly_col].min())
        vmax = float(shark_df[anomaly_col].max())
        if vmax <= vmin:
            vmax = vmin + 1e-6
        cmap = LinearColormap(
            colors=["#cfe8dc", "#89c2a6", "#e9c46a", "#f4a261"],
            vmin=vmin,
            vmax=vmax,
            caption="Assistive QC score (higher = more unusual step/gap/speed pattern)",
        )
        cmap.add_to(fmap)

    for sid, grp in shark_df.groupby("shark_id"):
        grp = grp.sort_values("ping_datetime")
        base_color = color_map[sid]
        coords = [(r["latitude"], r["longitude"]) for _, r in grp.iterrows()]
        if len(coords) > 1:
            folium.PolyLine(
                coords,
                color=base_color,
                weight=3 if sid == highlight_shark_id else 2,
                opacity=0.85,
            ).add_to(fmap)
        for _, r in grp.iloc[:-1].iterrows():
            if use_ml:
                v = float(r[anomaly_col])
                mcol = cmap(v)
                fill_op = 0.72
                line_col = "#335544"
            else:
                mcol = base_color
                fill_op = 0.65
                line_col = base_color
            popup_extra = ""
            if use_ml:
                popup_extra = f"<br>QC assist score {float(r[anomaly_col]):.2f}"
                if "qc_flag_ml" in r.index and bool(r["qc_flag_ml"]):
                    popup_extra += " (flagged)"
            folium.CircleMarker(
                location=[r["latitude"], r["longitude"]],
                radius=3 if sid != highlight_shark_id else 4,
                color=line_col,
                fill=True,
                fill_color=mcol,
                fill_opacity=fill_op,
                popup=f"{r['shark_name']}<br>{r['ping_datetime']}<br>quality {r['location_quality']}{popup_extra}",
            ).add_to(fmap)
        last = grp.iloc[-1]
        highlight = highlight_shark_id if highlight_shark_id is not None else (shark_ids[0] if len(shark_ids) == 1 else None)
        if highlight is not None and sid == highlight:
            folium.Marker(
                location=[last["latitude"], last["longitude"]],
                popup=f"<b>Latest demo ping</b><br>{last['shark_name']}<br>{last['ping_datetime']}",
                icon=folium.Icon(color="red", icon="info-sign"),
            ).add_to(fmap)
        else:
            if use_ml:
                v = float(last[anomaly_col])
                mcol = cmap(v)
                lp_extra = f"<br>QC assist score {float(last[anomaly_col]):.2f}"
                if "qc_flag_ml" in last.index and bool(last["qc_flag_ml"]):
                    lp_extra += " (flagged)"
            else:
                mcol = base_color
                lp_extra = ""
            folium.CircleMarker(
                location=[last["latitude"], last["longitude"]],
                radius=5,
                color="#335544" if use_ml else base_color,
                fill=True,
                fill_color=mcol,
                fill_opacity=0.9,
                popup=f"Latest ping<br>{last['shark_name']}<br>{last['ping_datetime']}{lp_extra}",
            ).add_to(fmap)
    return fmap
