"""Writes outputs/run_summary.json (committed) from the local pipeline files, so the app never needs raw data."""
import json
from pathlib import Path

import pandas as pd

raw, clean = pd.read_csv("data/raw_reviews.csv"), pd.read_csv("data/reviews_clean.csv")
sample = pd.read_csv("data/reviews_sample.csv")
summary = {
    "app": "Groww (com.nextbillion.groww)",
    "raw_fetched": len(raw), "clean": len(clean), "sample": len(sample),
    "weeks": int(sample.week_start.nunique()),
    "first_week": sample.week_start.min(), "last_week": sample.week_start.max(),
    "date_min": sample.date.min(), "date_max": sample.date.max(),
    "rating_mix": {int(k): int(v) for k, v in sample.rating.value_counts().sort_index().items()},
    "low_star_in_sample": int((sample.rating <= 2).sum()),
    "classifier_model": "openai/gpt-oss-20b", "judge_model": "openai/gpt-oss-120b",
}
Path("outputs/run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(summary)
