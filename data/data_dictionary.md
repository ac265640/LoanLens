# Data Dictionary

`training/generate_data.py` produces the synthetic loan tape everything else in this
repo trains and scores against. No real borrower data exists anywhere in this project.

## `loan_static_attributes.csv` — one row per loan

| Field | Type | Description |
|---|---|---|
| `loan_id` | string | Unique loan identifier (`LN0000001`...) |
| `origination_month` | string (`YYYY-MM`) | Month the loan was originated |
| `original_balance` | float | Original principal at origination (USD) |
| `interest_rate` | float | Note interest rate (%) |
| `credit_score_band` | string | One of `<620`, `620-659`, `660-699`, `700-739`, `740-779`, `780+` (can be missing — see below) |
| `ltv_band` | string | Loan-to-value band, e.g. `70-80%` |
| `dti_band` | string | Debt-to-income band, e.g. `20-28%` |
| `state` | string | US state code |
| `loan_purpose`, `occupancy_type`, `property_type` | string | Origination attributes |
| `servicer_name` | string | Which servicer is reporting this loan |
| `loan_term_months` | int | Original term (180/240/360) |

## `loan_monthly_performance_{train,test}.csv` — one row per loan per month

Includes every static field above plus:

| Field | Type | Description |
|---|---|---|
| `month_index` | int | Months since origination (1-based) |
| `reporting_month` | string (`YYYY-MM`) | The month this row reports on |
| `loan_age_months` / `remaining_term_months` | int | Seasoning |
| `current_balance` | float | Outstanding principal this month |
| `current_status` | string | `Current`, `30-59 DPD`, `60-89 DPD`, `90+ DPD`, `Default`, `Prepaid`, `Paid Off` |
| `days_past_due` | int | Days delinquent |
| `modification_flag` | 0/1 | Loan modification active this month |
| `prepayment_flag` / `default_flag` | 0/1 | Terminal event flags, set on the month it happens |
| `loss_severity_band` | string | Only populated on default months |
| `document_status` | string | `Complete` or `Missing Items` |
| `source_system` | string | Which loan-origination system reported this record |

**Forward-looking prediction targets** (computed once, by scanning each loan's full future
history at generation time — never used as model *inputs*, only as training labels):

| Field | Meaning |
|---|---|
| `next_state` | The loan's `current_status` next month |
| `next_3m_delinquency_flag` | Will the loan be 30+ DPD or worse within 3 months? |
| `next_6m_delinquency_flag` | Same, 6-month horizon |
| `next_12m_default_flag` | Will the loan reach `Default` within 12 months? |
| `next_12m_prepayment_flag` | Will the loan prepay within 12 months? |
| `exception_required` / `exception_type` | Ground truth for the VR001-VR005 rule engine + hybrid anomaly classifier — see `backend/ingest_pipeline/lib/rules.py` |

**Time-aware split**: `train` = loans originated before 2022-01; `test` = originated on/after
2022-01. Zero `loan_id` overlap between the two files (see `training/splitter.py` for the
further train/validation split used during model training, and `tests/test_splitter.py` for
the leakage guard).

## `servicer_updates.csv`

A secondary data feed sampled from 25% of the train panel, with ~5% of records perturbed
(balance noise, status conflicts) to simulate real-world servicer/system-of-record
disagreements — the kind of cross-source inconsistency the anomaly detector is meant to
catch, not just single-record rule violations.

## `macro_scenarios.csv`

Three named stress scenarios (`base`, `adverse_credit`, `high_prepayment`) used by
`training/scenario_segments.py` and, in continuous form, by
`scripts/precompute_stress_grid.py` (the dashboard's live Shockwave sliders).

## Injected data-quality issues (deliberate)

The generator intentionally injects realistic messiness so the data-quality profiler
(`training/profile_data.py`) and rule engine (`backend/ingest_pipeline/lib/rules.py`) have
something genuine to catch:

- `credit_score_band` missingness that increases sharply on older-vintage loans (MNAR)
- `interest_rate` missingness spread uniformly (~3.7%, MCAR)
- A small fraction of records that trip VR001-VR005 (date ordering, status/balance
  contradictions, missing documentation on modified loans, runaway balance growth)
