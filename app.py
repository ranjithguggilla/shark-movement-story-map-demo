from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from src.map_utils import build_story_map, filter_tracks, subset_tracks_through_day
from src.qa_checks import validate_tracks
from src.story_generator import build_journey_summary, write_sample_summaries
from src.story_llm import build_assist_payload, generate_llm_prose
from src.track_metrics import DATA_DIR, OUTPUT_DIR, SHARK_CARD_META, load_tracks, summarize_track_metrics, write_track_metrics_csv


ROOT = Path(__file__).resolve().parent
THEME_CSS_PATH = ROOT / "assets" / "theme.css"


def _inject_theme() -> None:
    if THEME_CSS_PATH.exists():
        css = THEME_CSS_PATH.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


st.set_page_config(page_title="Gulf Shark Movement Story Map", layout="wide", initial_sidebar_state="expanded")
_inject_theme()

st.markdown(
    '<div class="hero-band"><h1>Gulf Shark Movement Story Map</h1>'
    "<p>Public engagement prototype — synthetic demonstration tracks for storytelling and education. "
    "Not an operational tagging dashboard and not a substitute for tools such as Fin Finder.</p></div>",
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def _tracks_enriched(_cache_bust: int = 2) -> pd.DataFrame:
    """Bump `_cache_bust` when enriched schema changes so stale Streamlit cache refreshes."""
    return load_tracks()


@st.cache_data(show_spinner=False)
def _metrics_cached() -> pd.DataFrame:
    return summarize_track_metrics(_tracks_enriched())


@st.cache_data(show_spinner=False)
def _tracks_raw() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "synthetic_shark_tracks.csv")


tracks = _tracks_enriched()
metrics_df = _metrics_cached()

species_df = pd.read_csv(DATA_DIR / "species_profiles.csv")
notes_df = pd.read_csv(DATA_DIR / "conservation_notes.csv")

with st.sidebar:
    st.header("Filters")
    species_options = sorted(tracks["species"].unique())
    species_sel = st.multiselect("Species", species_options, default=species_options)
    month_sel = st.multiselect("Month", list(range(1, 13)), default=list(range(1, 13)))
    dist_min = st.number_input("Min total distance (miles)", min_value=0.0, value=0.0, step=50.0)
    dist_max = st.number_input("Max total distance (miles)", min_value=0.0, value=5000.0, step=50.0)
    shore_sel = st.selectbox("Nearshore / offshore", ["all", "nearshore", "offshore"])
    tag_sel = st.selectbox("Tag status", ["all", "active", "inactive"])
    st.divider()
    st.subheader("QA (synthetic)")
    if st.checkbox("Show QA table"):
        qa_df = validate_tracks(_tracks_raw())
        st.dataframe(qa_df, hide_index=True, use_container_width=True)

filtered = filter_tracks(
    tracks,
    species=species_sel if species_sel else None,
    months=month_sel if month_sel else None,
    min_distance=dist_min if dist_min > 0 else None,
    max_distance=dist_max if dist_max < 5000 else None,
    shore_filter=None if shore_sel == "all" else shore_sel,
    tag_status=None if tag_sel == "all" else tag_sel,
    metrics=metrics_df,
)

tabs = st.tabs(["Story Map", "Profiles", "Environmental context", "Education", "Export"])

with tabs[0]:
    shark_ids_avail = sorted(filtered["shark_id"].unique())
    if not shark_ids_avail:
        st.warning("No tracks match filters.")
    else:
        c_top1, c_top2 = st.columns((1, 1))
        with c_top1:
            playback_shark = st.selectbox("Playback shark", shark_ids_avail)
        with c_top2:
            st.markdown("&nbsp;", unsafe_allow_html=True)

        grp_full = filtered[filtered["shark_id"] == playback_shark].sort_values("ping_datetime")
        track_start = grp_full["ping_datetime"].min().normalize()
        span_days = max(1, int((grp_full["ping_datetime"].max() - track_start).days) + 1)
        day_slider = st.slider(
            "Playback day (1–90 demo window)",
            min_value=1,
            max_value=min(90, span_days),
            value=min(30, min(90, span_days)),
            step=1,
        )
        playback_df = subset_tracks_through_day(grp_full, track_start, day_slider)

        st.markdown(
            f"**Demo playback:** pings through **day {day_slider}** from track start `{track_start.date()}` "
            f"for **{playback_shark}**."
        )

        with st.expander("Assistive QC / pattern scoring (experimental)", expanded=False):
            st.caption(
                "QC assist flags unusual step length, speed, or time gaps on **this synthetic demo**. "
                "It does not describe real animal behavior or replace operational QA."
            )
            show_ml_qc = st.toggle("Show ML QC overlay on map", value=False, key="ml_qc_toggle")

        highlight_map = build_story_map(
            playback_df,
            zoom_start=6,
            highlight_shark_id=playback_shark,
            ml_overlay=show_ml_qc,
        )
        st_folium(highlight_map, use_container_width=True, height=520)

        with st.expander("Animated playback (Plotly, demo)", expanded=False):
            st.caption("Frame-by-frame ping reveal for presentations — same synthetic data as the Folium map above.")
            anim_df = playback_df.copy()
            if not anim_df.empty:
                anim_df = anim_df.sort_values("ping_datetime").reset_index(drop=True)
                anim_df["frame"] = np.arange(len(anim_df))
                hover_extra: dict = {
                    "ping_datetime": True,
                    "species": True,
                    "distance_from_shore_miles": ":.1f",
                }
                if "ai_anomaly_score" in anim_df.columns:
                    hover_extra["ai_anomaly_score"] = ":.2f"
                if "qc_flag_ml" in anim_df.columns:
                    hover_extra["qc_flag_ml"] = True
                fig_anim = px.scatter_geo(
                    anim_df,
                    lat="latitude",
                    lon="longitude",
                    animation_frame="frame",
                    hover_name="shark_name",
                    hover_data=hover_extra,
                    color="species",
                    height=480,
                    title="Synthetic track playback (frame = ping order)",
                )
                fig_anim.update_geos(
                    scope="north america",
                    projection_scale=3.2,
                    showland=True,
                    landcolor="#edf2f4",
                    coastlinecolor="#8d99ae",
                )
                fig_anim.update_layout(margin=dict(l=0, r=0, t=40, b=0))
                st.plotly_chart(fig_anim, use_container_width=True)

        st.subheader("Rule-based journey summary")
        row = metrics_df.set_index("shark_id").loc[playback_shark]
        st.write(build_journey_summary(playback_shark, tracks, row))

        with st.expander("Optional AI-assisted wording (experimental)", expanded=False):
            st.caption(
                "Structured facts only are sent to an LLM if configured (see README). "
                "Default is a local stub — no cloud call. This is **assistive prose**, not behavior science."
            )
            show_llm = st.checkbox("Generate assistive blurb", value=False, key="llm_gen")
            if show_llm:
                payload = build_assist_payload(playback_shark, tracks, row, playback_df=playback_df)
                llm_key = f"llm_text_{playback_shark}"
                if st.button("Refresh wording", key="llm_refresh"):
                    st.session_state[llm_key] = generate_llm_prose(payload)
                if llm_key not in st.session_state:
                    st.session_state[llm_key] = generate_llm_prose(payload)
                st.markdown(st.session_state[llm_key])
                st.info("AI-assisted wording — synthetic demonstration only; not operational telemetry.")

with tabs[1]:
    st.subheader("Shark profile cards (synthetic)")
    for shark_id in sorted(metrics_df["shark_id"].unique()):
        meta = SHARK_CARD_META.get(shark_id, {})
        row = metrics_df.set_index("shark_id").loc[shark_id]
        g = tracks[tracks["shark_id"] == shark_id].sort_values("ping_datetime")
        sp = g.iloc[0]["species"]
        sp_row = species_df[species_df["species"] == sp].iloc[0]
        with st.container(border=True):
            st.markdown(f"### {g.iloc[0]['shark_name']}")
            pc1, pc2 = st.columns(2)
            pc1.markdown(f"- **Species:** {sp}")
            pc1.markdown(f"- **Scientific name:** {sp_row['scientific_name']}")
            pc1.markdown(f"- **Tagged near:** {meta.get('tagged_near', 'Synthetic demo origin')}")
            pc1.markdown(f"- **Synthetic sex:** {meta.get('sex', '—')}")
            pc1.markdown(f"- **Synthetic length:** {meta.get('fork_length_cm', '—')} cm (demo placeholder)")
            pc2.markdown(f"- **Track duration:** {int(row['track_duration_days'])} days")
            pc2.markdown(f"- **Distance traveled (demo):** {row['total_distance_miles']:.1f} miles")
            pc2.markdown(f"- **Latest ping:** {g.iloc[-1]['ping_datetime']}")
            st.markdown(
                f"**Behavior note (demo wording):** Stayed predominantly in **{row['nearshore_percent']:.0f}%** "
                f"near-coastal contexts with shelf transitions visible in the synthetic track."
            )
            st.markdown(f"**Conservation note:** {sp_row['conservation_note']}")
            st.info(sp_row["public_message"])

with tabs[2]:
    st.subheader("Context at playback")
    shark_ids_avail = sorted(filtered["shark_id"].unique())
    if shark_ids_avail:
        ctx_shark = st.selectbox("Shark", shark_ids_avail, key="ctx_shark")
        grp = filtered[filtered["shark_id"] == ctx_shark].sort_values("ping_datetime")
        t0 = grp["ping_datetime"].min().normalize()
        span = max(1, int((grp["ping_datetime"].max() - t0).days) + 1)
        day_ctx = st.slider("Day index for context row", 1, min(90, span), min(20, min(90, span)), key="ctx_day")
        sub = subset_tracks_through_day(filtered, t0, day_ctx)
        sub_g = sub[sub["shark_id"] == ctx_shark].sort_values("ping_datetime")
        if sub_g.empty:
            st.warning("No pings at this playback day.")
        else:
            cur = sub_g.iloc[-1]
            ml_note = ""
            if "ai_anomaly_score" in cur.index:
                ml_note = f"\n- **Assistive QC score (demo):** {float(cur['ai_anomaly_score']):.2f}"
                if "qc_flag_ml" in cur.index and bool(cur["qc_flag_ml"]):
                    ml_note += " (flagged by offline model)"
            st.markdown(
                f"- **Ping date:** {cur['ping_datetime']}\n"
                f"- **Distance from shore:** {cur['distance_from_shore_miles']} miles\n"
                f"- **Estimated depth zone:** {cur['depth_zone']}\n"
                f"- **Temperature estimate:** {cur['temperature_c_estimate']} °C (synthetic)\n"
                f"- **Gulf region:** {cur['gulf_region']}\n"
                f"- **Habitat label:** {cur['habitat_zone_label']}\n"
                f"- **Movement since last ping:** {cur['distance_since_last_ping_miles']} miles\n"
                f"- **Average speed:** {cur['avg_speed_mph_since_last_ping']} mph"
                f"{ml_note}\n"
            )
            fig = px.line(
                grp,
                x="ping_datetime",
                y="distance_from_shore_miles",
                title="Distance from shore over time (synthetic demo)",
            )
            st.plotly_chart(fig, use_container_width=True)

with tabs[3]:
    st.subheader("Education and public context")
    for section in notes_df["section"].unique():
        block = notes_df[notes_df["section"] == section]
        st.markdown(f"### {block.iloc[0]['heading']}")
        for _, r in block.iterrows():
            st.markdown(r["body_md"])
    st.markdown("---")
    st.markdown(
        "**External references (examples for responsible messaging):** "
        "[NOAA Fisheries shark information](https://www.fisheries.noaa.gov/feature-story/sharks) · "
        "state coastal resources pages for handling best practices."
    )

with tabs[4]:
    st.subheader("Export demo artifacts")
    st.write("Regenerate summaries and metrics CSV in `outputs/`.")
    if st.button("Regenerate outputs"):
        write_track_metrics_csv(tracks)
        p = write_sample_summaries(tracks)
        st.success(f"Wrote track metrics and {p.name}")

    mpath = OUTPUT_DIR / "track_metrics.csv"
    spath = OUTPUT_DIR / "sample_story_summary.md"
    tpath = DATA_DIR / "synthetic_shark_tracks.csv"

    if mpath.exists():
        st.download_button("Download track_metrics.csv", mpath.read_bytes(), "track_metrics.csv", "text/csv")
    if spath.exists():
        st.download_button("Download sample_story_summary.md", spath.read_bytes(), "sample_story_summary.md", "text/markdown")
    if tpath.exists():
        st.download_button("Download synthetic_shark_tracks.csv", tpath.read_bytes(), "synthetic_shark_tracks.csv", "text/csv")
