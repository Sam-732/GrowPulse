"""Phase 1: scrape Groww Play Store reviews (12 weeks), clean, cap per week, write CSVs.

Reuses VoC-Copilot's ingest loop (google-play-scraper, newest first, stop at cutoff)
and clean() normalisation. Usernames are never stored. Phone numbers / emails inside
review text are redacted before anything is written.
"""
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from google_play_scraper import Sort, reviews

from src.keywords import KEYWORDS, matched_keywords

APP_ID = "com.nextbillion.groww"
WEEKS = 12
CAP_PER_WEEK = 150
MIN_WORDS = 4          # VoC used 5; fee complaints are short ("extra charges deducted")
SEED = 42
DATA = Path("data")
RAW, CLEAN, SAMPLE = DATA / "raw_reviews.csv", DATA / "reviews_clean.csv", DATA / "reviews_sample.csv"

PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def scrape(cutoff: datetime) -> pd.DataFrame:
    rows, token, total = [], None, 0
    while True:
        batch, token = reviews(APP_ID, lang="en", country="in", sort=Sort.NEWEST,
                               count=200, continuation_token=token)
        if not batch:
            print("empty batch, stopping")
            break
        # userName / userImage deliberately dropped here.
        rows += [{"review_id": r["reviewId"], "text": r["content"], "rating": r["score"],
                  "date": r["at"], "thumbs_up": r.get("thumbsUpCount"),
                  "app_version": r.get("reviewCreatedVersion")} for r in batch]
        total += len(batch)
        oldest = batch[-1]["at"]
        print(f"fetched {total} | oldest {oldest:%Y-%m-%d}", flush=True)
        if oldest < cutoff or token is None:
            break
        time.sleep(1)
    return pd.DataFrame(rows)


def clean_text(t: str) -> str:
    t = re.sub(r"(.)\1{2,}", r"\1\1", t)       # goooood -> goood  (VoC rule)
    t = re.sub(r"([!?.,])\1+", r"\1", t)       # !!!! -> !
    t = EMAIL.sub("[email]", t)
    t = PHONE.sub("[phone]", t)
    return re.sub(r"\s+", " ", t).strip()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    DATA.mkdir(exist_ok=True)
    now = datetime.now()
    cutoff = now - timedelta(weeks=WEEKS)
    if RAW.exists() and "--refetch" not in sys.argv:
        raw = pd.read_csv(RAW, parse_dates=["date"])
        print(f"using cached {RAW} ({len(raw)} rows); pass --refetch to scrape again")
    else:
        raw = scrape(cutoff)
        raw.to_csv(RAW, index=False)
    n_raw = len(raw)

    df = raw.dropna(subset=["text"]).copy()
    df = df[df["date"] >= cutoff]
    # keep whole Monday-based weeks only: drop the partial leading week
    df["week_start"] = (df["date"].dt.normalize() - pd.to_timedelta(df["date"].dt.weekday, unit="D"))
    first_full = (cutoff.date() + timedelta(days=(7 - cutoff.weekday()) % 7))
    df = df[df["week_start"].dt.date >= first_full]
    n_window = len(df)

    df["text"] = df["text"].map(clean_text)
    df = df[df["text"].str.split().str.len() >= MIN_WORDS]
    n_long = len(df)
    df["_key"] = df["text"].str.lower()
    df = df.sort_values("date", ascending=False).drop_duplicates("_key").drop(columns="_key")
    df = df.drop_duplicates("review_id")
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df["week_start"] = df["week_start"].dt.strftime("%Y-%m-%d")
    df = df[df["rating"].between(1, 5)]
    df = df[["review_id", "text", "rating", "date", "week_start", "thumbs_up", "app_version"]]
    df.to_csv(CLEAN, index=False, encoding="utf-8")

    sample = pd.concat([g.sample(min(len(g), CAP_PER_WEEK), random_state=SEED)
                        for _, g in df.groupby("week_start")]
                       ).sort_values(["week_start", "date"])
    sample.to_csv(SAMPLE, index=False, encoding="utf-8")

    print("\n=== SUMMARY ===")
    print(f"raw rows fetched:              {n_raw}")
    print(f"in 12-week window (full wks):  {n_window}")
    print(f">= {MIN_WORDS} words:                  {n_long}")
    print(f"after dedupe (clean CSV):      {len(df)}")
    print(f"sample (cap {CAP_PER_WEEK}/week):        {len(sample)}")
    wk = df.groupby("week_start").size().rename("clean").to_frame().join(
        sample.groupby("week_start").size().rename("sample"))
    print(f"weeks covered: {len(wk)}  ({wk.index.min()} .. {wk.index.max()})\n{wk.to_string()}")
    print("\nrating mix (sample):", sample["rating"].value_counts().sort_index().to_dict())

    for name, frame in (("CLEAN", df), ("SAMPLE", sample)):
        hits = frame["text"].map(matched_keywords)
        print(f"\nkeyword counts [{name}, n={len(frame)}] (a review can match several):")
        for k in KEYWORDS:
            print(f"  {k:11} {sum(k in h for h in hits)}")
        print(f"  ANY keyword {sum(bool(h) for h in hits)}")


if __name__ == "__main__":
    main()
