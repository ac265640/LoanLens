import pandas as pd
import pytest

from splitter import time_aware_split


@pytest.fixture
def multi_vintage_panel():
    rows = []
    for loan_id, orig_month in [("A", "2018-01"), ("B", "2019-06"), ("C", "2020-06"), ("D", "2021-01")]:
        for m in range(1, 4):
            rows.append(dict(loan_id=loan_id, origination_month=orig_month, month_index=m))
    return pd.DataFrame(rows)


def test_no_loan_id_overlap_between_train_and_val(multi_vintage_panel):
    train_df, val_df = time_aware_split(multi_vintage_panel, val_cutoff="2020-01-01")
    assert set(train_df["loan_id"]).isdisjoint(set(val_df["loan_id"]))


def test_split_respects_the_cutoff(multi_vintage_panel):
    train_df, val_df = time_aware_split(multi_vintage_panel, val_cutoff="2020-01-01")
    assert set(train_df["loan_id"].unique()) == {"A", "B"}
    assert set(val_df["loan_id"].unique()) == {"C", "D"}


def test_raises_on_injected_leakage():
    """If the same loan_id appears with origination dates straddling the
    cutoff (a malformed/duplicated record), the split must refuse rather
    than silently leak it into both cohorts."""
    panel = pd.DataFrame([
        dict(loan_id="X", origination_month="2019-01", month_index=1),
        dict(loan_id="X", origination_month="2021-01", month_index=2),  # same id, later "vintage"
    ])
    with pytest.raises(ValueError, match="leakage"):
        time_aware_split(panel, val_cutoff="2020-01-01")
