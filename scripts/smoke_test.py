from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.story_generator import write_sample_summaries
from src.track_metrics import write_track_metrics_csv


def main() -> None:
    metrics_path = write_track_metrics_csv()
    summary_path = write_sample_summaries()

    assert metrics_path.exists(), f"Missing {metrics_path}"
    assert summary_path.exists(), f"Missing {summary_path}"

    lines = metrics_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) > 1, "track_metrics.csv should have a header and rows"

    assert summary_path.read_text(encoding="utf-8").strip(), "sample_story_summary.md should not be empty"

    print("Smoke test passed: track metrics and story summaries generate cleanly.")


if __name__ == "__main__":
    main()
