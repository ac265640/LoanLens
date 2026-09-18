"""
Deterministic Validation Rule Engine (VR001-VR005)
===================================================
Hard, logically-certain checks on loan tape rows. These have 100% precision
by construction — they are constraints, not predictions — and feed into the
hybrid anomaly/exception model alongside the learned Isolation Forest score.
"""

import pandas as pd


def compute_rule_violation_signals(df: pd.DataFrame) -> pd.DataFrame:
    signals = pd.DataFrame(index=df.index)

    if "reporting_month" in df.columns and "origination_month" in df.columns:
        r_dt = pd.to_datetime(df["reporting_month"] + "-01", errors="coerce")
        o_dt = pd.to_datetime(df["origination_month"] + "-01", errors="coerce")
        signals["sig_date_anomaly"] = (r_dt < o_dt).fillna(False).astype(int)
    else:
        signals["sig_date_anomaly"] = 0

    if "current_status" in df.columns and "current_balance" in df.columns:
        signals["sig_paidoff_balance"] = (
            (df["current_status"] == "Paid Off") & (df["current_balance"] > 1000)
        ).fillna(False).astype(int)
    else:
        signals["sig_paidoff_balance"] = 0

    if "current_status" in df.columns and "days_past_due" in df.columns:
        signals["sig_default_low_dpd"] = (
            (df["current_status"] == "Default") & (df["days_past_due"] < 60)
        ).fillna(False).astype(int)
    else:
        signals["sig_default_low_dpd"] = 0

    if "modification_flag" in df.columns and "document_status" in df.columns:
        signals["sig_mod_missing_doc"] = (
            (df["modification_flag"] == 1) & (df["document_status"] == "Missing Items")
        ).fillna(False).astype(int)
    else:
        signals["sig_mod_missing_doc"] = 0

    if "current_balance" in df.columns and "original_balance" in df.columns:
        signals["sig_excessive_balance"] = (
            df["current_balance"] > df["original_balance"] * 2.0
        ).fillna(False).astype(int)
    else:
        signals["sig_excessive_balance"] = 0

    signals["total_rule_violations"] = signals.sum(axis=1)
    return signals
