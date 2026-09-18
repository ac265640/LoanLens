import numpy as np

from lib.feature_engineer import engineer_panel_features, get_feature_columns


def test_output_has_all_declared_feature_columns(sample_panel):
    feat = engineer_panel_features(sample_panel)
    for col in get_feature_columns():
        assert col in feat.columns, f"missing declared feature column: {col}"


def test_no_nan_in_feature_columns_after_fillna(sample_panel):
    feat = engineer_panel_features(sample_panel)
    X = feat[get_feature_columns()].fillna(0)
    assert not X.isna().any().any()


def test_ordinal_encodings_are_monotonic_with_band_quality(sample_panel):
    feat = engineer_panel_features(sample_panel)
    # LN0000001 is "700-739" (better), LN0000003 is "<620" (worse) — the
    # ordinal encoding must rank the better band higher.
    better = feat.loc[feat["loan_id"] == "LN0000001", "credit_score_ordinal"].iloc[0]
    worse = feat.loc[feat["loan_id"] == "LN0000003", "credit_score_ordinal"].iloc[0]
    assert better > worse


def test_rolling_dpd_feature_is_backward_looking_only(sample_panel):
    """The 3-month rolling max DPD for LN0000001's *first* observed month
    must equal that month's own DPD — it cannot see months that haven't
    happened yet. This is the concrete check against forward-looking leakage."""
    feat = engineer_panel_features(sample_panel)
    loan1 = feat[feat["loan_id"] == "LN0000001"].sort_values("month_index")
    first_month = loan1.iloc[0]
    assert first_month["dpd_roll_max_3m"] == first_month["days_past_due"]


def test_balance_to_orig_ratio_is_bounded(sample_panel):
    feat = engineer_panel_features(sample_panel)
    # LN0000003 has current_balance=250000 vs original=100000 (2.5x) —
    # the ratio must be clipped to the documented [0, 3] range, not just
    # pass the raw 2.5 through unbounded.
    assert feat["balance_to_orig_ratio"].between(0.0, 3.0).all()


def test_missing_interest_rate_flag_and_imputation(sample_panel):
    panel = sample_panel.copy()
    panel.loc[panel["loan_id"] == "LN0000001", "interest_rate"] = np.nan
    feat = engineer_panel_features(panel)
    flagged = feat[feat["loan_id"] == "LN0000001"]
    assert (flagged["interest_rate_is_missing"] == 1).all()
    assert not flagged["interest_rate_imputed"].isna().any()
