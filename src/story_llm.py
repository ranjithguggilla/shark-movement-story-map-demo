"""
Optional LLM-assisted wording from structured facts only (no raw coordinate dumps to APIs by default).

Labels output as experimental; does not claim biological inference.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .track_metrics import SHARK_CARD_META


def _stub_paragraph(payload: dict[str, Any]) -> str:
    sid = payload.get("shark_id", "")
    n_flag = int(payload.get("ml_qc_flags_in_playback", 0))
    score_max = payload.get("ml_anomaly_max_in_playback")
    bits = [
        "This optional AI-assisted blurb rephrases the same synthetic demo facts shown above.",
        f"It must not be read as field telemetry or animal behavior science — the track is **demonstration-only**.",
    ]
    if n_flag or (score_max is not None and float(score_max) > 0.65):
        bits.append(
            f"Assistive QC highlighted **{n_flag}** flagged ping(s) in the current playback window; "
            "that only reflects unusual step/gap/speed patterns on synthetic data."
        )
    return " ".join(bits)


def build_assist_payload(
    shark_id: str,
    enriched: Any,
    metrics_row: Any,
    playback_df: Any | None = None,
) -> dict[str, Any]:
    """Structured JSON-safe facts for LLM or stub (no coordinate arrays)."""
    import pandas as pd

    g = enriched[enriched["shark_id"] == shark_id].sort_values("ping_datetime")
    meta = SHARK_CARD_META.get(shark_id, {})
    sp = str(g.iloc[0]["species"]) if len(g) else ""
    out: dict[str, Any] = {
        "shark_id": shark_id,
        "shark_name": str(g.iloc[0]["shark_name"]) if len(g) else "",
        "species": sp,
        "tagged_near": meta.get("tagged_near", ""),
        "track_duration_days": float(metrics_row["track_duration_days"]),
        "total_distance_miles": float(metrics_row["total_distance_miles"]),
        "nearshore_percent": float(metrics_row["nearshore_percent"]),
        "rule_summary_one_liner": "",  # filled by caller if desired
        "synthetic_demo_disclaimer": True,
    }
    if playback_df is not None and len(playback_df):
        sub = playback_df[playback_df["shark_id"] == shark_id] if "shark_id" in playback_df.columns else playback_df
        if "qc_flag_ml" in sub.columns:
            out["ml_qc_flags_in_playback"] = int(sub["qc_flag_ml"].sum())
        if "ai_anomaly_score" in sub.columns:
            out["ml_anomaly_max_in_playback"] = float(sub["ai_anomaly_score"].max())
            out["ml_anomaly_mean_in_playback"] = float(sub["ai_anomaly_score"].mean())
    return out


def _system_prompt() -> str:
    return (
        "You write short public-education blurbs for a synthetic shark-track demonstration app. "
        "Never claim real telemetry, predictions of future locations, or biological inference. "
        "Always state that the dataset is synthetic demonstration. "
        "Use at most 3 sentences. No coordinates."
    )


def _user_prompt(payload: dict[str, Any]) -> str:
    return (
        "Produce assistive prose from this JSON only:\n"
        f"{json.dumps(payload, indent=2)}\n\n"
        "Include the phrase 'synthetic demonstration' once."
    )


def generate_llm_prose(payload: dict[str, Any]) -> str:
    """
    Order: OpenAI-compatible API if OPENAI_API_KEY set; else Ollama if OLLAMA_HOST set;
    else deterministic stub (no network).
    """
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        try:
            return _openai_complete(payload, key)
        except Exception:
            return _stub_paragraph(payload)

    ollama = os.environ.get("OLLAMA_HOST", "").strip()
    model = os.environ.get("OLLAMA_MODEL", "llama3.2").strip()
    if ollama:
        try:
            return _ollama_complete(payload, ollama.rstrip("/"), model)
        except Exception:
            return _stub_paragraph(payload)

    return _stub_paragraph(payload)


def _openai_complete(payload: dict[str, Any], api_key: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        return _stub_paragraph(payload)

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)
    chat = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt(payload)},
        ],
        max_tokens=220,
        temperature=0.4,
    )
    return (chat.choices[0].message.content or "").strip()


def _ollama_complete(payload: dict[str, Any], host: str, model: str) -> str:
    url = f"{host}/api/generate"
    body = json.dumps(
        {
            "model": model,
            "prompt": _system_prompt() + "\n\n" + _user_prompt(payload),
            "stream": False,
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    return str(data.get("response", "")).strip()
