import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "ingest_pipeline"))
sys.path.insert(0, str(ROOT / "training"))


@pytest.fixture
def sample_panel() -> pd.DataFrame:
    """A tiny, hand-built 2-loan panel covering both a clean loan and one
    that trips every VR001-VR005 rule, so tests don't depend on the
    (regenerable, gitignored) full synthetic dataset existing on disk."""
    rows = [
        # LN0000001: clean, paying loan, 3 months of history
        dict(loan_id="LN0000001", month_index=1, reporting_month="2021-01", origination_month="2020-11",
             current_status="Current", days_past_due=0, current_balance=98000, original_balance=100000,
             interest_rate=4.5, credit_score_band="700-739", ltv_band="70-80%", dti_band="20-28%",
             loan_age_months=2, remaining_term_months=358, modification_flag=0, state="TX",
             servicer_name="Acme Servicing", loan_purpose="Purchase", occupancy_type="Primary",
             property_type="Single Family", document_status="Complete", source_system="LOS-A"),
        dict(loan_id="LN0000001", month_index=2, reporting_month="2021-02", origination_month="2020-11",
             current_status="Current", days_past_due=0, current_balance=97500, original_balance=100000,
             interest_rate=4.5, credit_score_band="700-739", ltv_band="70-80%", dti_band="20-28%",
             loan_age_months=3, remaining_term_months=357, modification_flag=0, state="TX",
             servicer_name="Acme Servicing", loan_purpose="Purchase", occupancy_type="Primary",
             property_type="Single Family", document_status="Complete", source_system="LOS-A"),
        dict(loan_id="LN0000001", month_index=3, reporting_month="2021-03", origination_month="2020-11",
             current_status="Current", days_past_due=0, current_balance=97000, original_balance=100000,
             interest_rate=4.5, credit_score_band="700-739", ltv_band="70-80%", dti_band="20-28%",
             loan_age_months=4, remaining_term_months=356, modification_flag=0, state="TX",
             servicer_name="Acme Servicing", loan_purpose="Purchase", occupancy_type="Primary",
             property_type="Single Family", document_status="Complete", source_system="LOS-A"),
        # LN0000002: trips every rule violation at once
        dict(loan_id="LN0000002", month_index=1, reporting_month="2019-01", origination_month="2020-01",  # VR001: reporting < origination
             current_status="Paid Off", days_past_due=0, current_balance=5000,  # VR002: Paid Off with balance > $1k
             original_balance=100000, interest_rate=4.5, credit_score_band="620-659", ltv_band="80-90%",
             dti_band="36-43%", loan_age_months=1, remaining_term_months=359, modification_flag=1,
             state="FL", servicer_name="Acme Servicing", loan_purpose="Purchase", occupancy_type="Primary",
             property_type="Single Family", document_status="Missing Items", source_system="LOS-B"),
    ]
    df = pd.DataFrame(rows)
    # VR003 (Default with DPD<60) and VR005 (balance > 2x original) on a 3rd row
    df.loc[len(df)] = dict(
        loan_id="LN0000003", month_index=1, reporting_month="2021-01", origination_month="2020-01",
        current_status="Default", days_past_due=10, current_balance=250000, original_balance=100000,
        interest_rate=4.5, credit_score_band="<620", ltv_band=">95%", dti_band=">43%",
        loan_age_months=12, remaining_term_months=348, modification_flag=0, state="CA",
        servicer_name="Acme Servicing", loan_purpose="Purchase", occupancy_type="Primary",
        property_type="Single Family", document_status="Complete", source_system="LOS-A",
    )
    return df
