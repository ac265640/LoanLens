REQUIRED_COLUMNS = [
    "loan_id", "month_index", "reporting_month", "origination_month",
    "current_status", "days_past_due", "current_balance", "original_balance",
    "interest_rate", "credit_score_band", "ltv_band", "dti_band",
    "loan_age_months", "remaining_term_months", "modification_flag", "state",
]

VALID_STATUSES = {"Current", "30-59 DPD", "60-89 DPD", "90+ DPD", "Default", "Prepaid", "Paid Off"}
VALID_CREDIT_BANDS = {"<620", "620-659", "660-699", "700-739", "740-779", "780+"}


def test_required_columns_present(sample_panel):
    for col in REQUIRED_COLUMNS:
        assert col in sample_panel.columns, f"missing required column: {col}"


def test_current_status_is_a_known_value(sample_panel):
    assert set(sample_panel["current_status"].unique()).issubset(VALID_STATUSES)


def test_credit_score_band_is_a_known_value_or_missing(sample_panel):
    observed = set(sample_panel["credit_score_band"].dropna().unique())
    assert observed.issubset(VALID_CREDIT_BANDS)


def test_days_past_due_is_non_negative(sample_panel):
    assert (sample_panel["days_past_due"] >= 0).all()


def test_balances_are_non_negative(sample_panel):
    assert (sample_panel["current_balance"] >= 0).all()
    assert (sample_panel["original_balance"] >= 0).all()


def test_month_index_is_positive(sample_panel):
    assert (sample_panel["month_index"] >= 1).all()
