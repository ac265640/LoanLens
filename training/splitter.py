"""
Time-Aware Cohort Splitter
============================
Splits the training panel into train/validation cohorts by origination
month rather than randomly. A random row-level split would leak future
months of a loan's own history into training, since a loan_id appears
repeatedly across its monthly records — the model would effectively see
the answer key. Splitting by vintage (origination cohort) instead means
validation loans are ones the model has never seen a single row of.
"""

import logging
from typing import Tuple

import pandas as pd

log = logging.getLogger(__name__)


def time_aware_split(
    df: pd.DataFrame,
    val_cutoff: str,
    time_col: str = "origination_month",
    id_col: str = "loan_id",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.to_datetime(df[time_col].astype(str) + "-01", errors="coerce")
    cutoff = pd.Timestamp(val_cutoff)

    train_df = df[dates < cutoff].copy()
    val_df = df[dates >= cutoff].copy()

    train_ids = set(train_df[id_col].unique())
    val_ids = set(val_df[id_col].unique())
    overlap = train_ids & val_ids
    if overlap:
        raise ValueError(f"loan_id leakage between train/val cohorts: {len(overlap)} loans appear in both")

    log.info(
        f"Time-aware split at {val_cutoff}: train={len(train_df):,} rows "
        f"({len(train_ids):,} loans), val={len(val_df):,} rows ({len(val_ids):,} loans)"
    )
    return train_df, val_df
