"""Counting helpers for the app. Pure pandas, no AI. Same trend rule as pulse.py (last 4 weeks vs the 4 before)."""
import pandas as pd


def theme_reviews(sample_csv: str = "data/reviews_sample.csv",
                  assign_csv: str = "data/theme_assignments.csv") -> pd.DataFrame:
    return pd.read_csv(sample_csv).merge(pd.read_csv(assign_csv), on="review_id")


def trend(df: pd.DataFrame, theme_id: str) -> dict:
    """1-2 star reviews of a theme: last 4 weeks vs the previous 4. More low-star reviews = worse."""
    weeks = sorted(df.week_start.unique())
    recent_w, prev_w = weeks[-4:], weeks[-8:-4]
    low = df[(df.theme == theme_id) & (df.rating <= 2)]
    recent, prev = int(low.week_start.isin(recent_w).sum()), int(low.week_start.isin(prev_w).sum())
    delta = recent - prev
    pct = (delta / prev * 100) if prev else None
    direction = "flat" if delta == 0 else ("up" if delta > 0 else "down")
    return {"recent": recent, "prev": prev, "delta": delta, "pct": pct, "direction": direction}


def weekly_low(df: pd.DataFrame, theme_id: str) -> pd.Series:
    weeks = sorted(df.week_start.unique())
    low = df[(df.theme == theme_id) & (df.rating <= 2)]
    return low.groupby("week_start").size().reindex(weeks, fill_value=0)
