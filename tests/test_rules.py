from lib.rules import compute_rule_violation_signals


def test_clean_loan_trips_no_rules(sample_panel):
    signals = compute_rule_violation_signals(sample_panel)
    clean_rows = sample_panel["loan_id"] == "LN0000001"
    assert (signals.loc[clean_rows, "total_rule_violations"] == 0).all()


def test_vr001_date_anomaly_detected(sample_panel):
    signals = compute_rule_violation_signals(sample_panel)
    bad_row = sample_panel["loan_id"] == "LN0000002"
    assert signals.loc[bad_row, "sig_date_anomaly"].iloc[0] == 1


def test_vr002_paidoff_balance_detected(sample_panel):
    signals = compute_rule_violation_signals(sample_panel)
    bad_row = sample_panel["loan_id"] == "LN0000002"
    assert signals.loc[bad_row, "sig_paidoff_balance"].iloc[0] == 1


def test_vr003_default_low_dpd_detected(sample_panel):
    signals = compute_rule_violation_signals(sample_panel)
    bad_row = sample_panel["loan_id"] == "LN0000003"
    assert signals.loc[bad_row, "sig_default_low_dpd"].iloc[0] == 1


def test_vr004_modification_missing_doc_detected(sample_panel):
    signals = compute_rule_violation_signals(sample_panel)
    bad_row = sample_panel["loan_id"] == "LN0000002"
    assert signals.loc[bad_row, "sig_mod_missing_doc"].iloc[0] == 1


def test_vr005_excessive_balance_detected(sample_panel):
    signals = compute_rule_violation_signals(sample_panel)
    bad_row = sample_panel["loan_id"] == "LN0000003"
    assert signals.loc[bad_row, "sig_excessive_balance"].iloc[0] == 1


def test_bad_loan_trips_multiple_rules(sample_panel):
    signals = compute_rule_violation_signals(sample_panel)
    bad_row = sample_panel["loan_id"] == "LN0000002"
    assert signals.loc[bad_row, "total_rule_violations"].iloc[0] >= 3
