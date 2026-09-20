# ML pipeline

Everything here is reproducible from scratch: `make run-all` generates the data, trains every model, runs each
analysis and both test suites in about two minutes. The committed model artifacts and reports live in
`backend/ingest_pipeline/models/`.

**All data is synthetic.** `training/generate_data.py` produces a 5,000-loan portfolio (statics, a monthly
performance panel, and a secondary servicer feed with injected conflicts). No real borrower data exists in this
repository. Model metrics therefore show how the pipeline behaves, not how it would perform on a real lender's book.

## Pipeline

| Step | Script | Output |
|---|---|---|
| Generate data | `training/generate_data.py` | `data/raw/*.csv` (gitignored, regenerable) |
| Time-aware split | `training/splitter.py` | Train / validation cohorts by origination month, with a `loan_id` leakage assertion |
| Prediction models | `training/train_prediction_models.py` | 4 calibrated LightGBM classifiers + 1 multiclass |
| Anomaly models | `training/train_anomaly_models.py` | Isolation Forest + hybrid exception classifier |
| Data quality | `training/profile_data.py` | Quality score and missingness diagnosis |
| Survival | `training/survival_analysis.py` | Competing-risk CIF vs. naive Kaplan-Meier, Markov matrix |
| Explainability | `training/explainability.py` | TreeSHAP, calibration diagnostics, fairness audit |
| Scenarios | `training/scenario_segments.py` | Three named macro scenarios by segment |
| Counterfactuals | `training/counterfactuals.py` | "What single change lowers this loan's risk most" |
| Conformal | `training/conformal_intervals.py` | 90% prediction intervals |
| Stress grid | `scripts/precompute_stress_grid.py` | The grid behind the dashboard's live sliders |

## Features and targets

32 features from the raw panel, all backward-looking: ordinal encodings of credit, LTV, DTI and status;
balance ratios and trajectories; rolling 3- and 6-month delinquency; seasoning; categorical frequencies.
`tests/test_feature_engineer.py` checks concretely that a loan's first month cannot see later months.

Targets are one model per business question: 3-month and 6-month delinquency (who needs a call), 12-month default
(provisioning), 12-month prepayment (cash flow), and the next-month status.

## Results

Validation cohort = loans originated 2020-01 or later. The LightGBM models never trained on them; only the Platt calibration layer was fitted on them.

| Target | ROC-AUC | PR-AUC | Brier |
|---|---|---|---|
| 3-month delinquency | 0.808 | 0.426 | 0.029 |
| 6-month delinquency | 0.763 | 0.356 | 0.049 |
| 12-month default | 0.675 | 0.085 | 0.044 |
| 12-month prepayment | 0.616 | 0.059 | 0.045 |
| Next-month status (macro-F1) | 0.524 | | |

These are modest, and the longer horizons and rarer events are harder, as expected. F1 at a 0.5 threshold is
uninformative for the two rare targets (positives are rare, so calibrated probabilities seldom reach 0.5), which is
why the product acts on 8% and 20% thresholds and reports PR-AUC and Brier instead.

**Calibration.** Probabilities are Platt-scaled on the validation cohort. Expected Calibration Error on the 12-month
default target is 0.0174, so a predicted 12% is close to an observed 12%, not only a good ranking. ECE and Brier are
measured on the same cohort the calibrator was fitted on, so read them as in-sample figures; AUC is unaffected by calibration.

**Uncertainty.** Split-conformal 90% prediction intervals around the 12-month default probability have half-width 0.188.
Measured coverage on the held-out half is 90.28% against a 90% target.

## Anomaly and exception detection

A hybrid of two signals, neither sufficient alone:

- **Deterministic rules VR001-VR005:** reporting month before origination; "Paid Off" with a balance over $1,000;
  "Default" with under 60 days past due; a modification with missing documents; balance above twice the original.
  Logical constraints with no false positives by construction, but only for what someone wrote down.
- **Isolation Forest:** an unsupervised score of how unusual a record is across all 32 features, which can surface
  patterns nobody wrote a rule for, but cannot explain itself.

A LightGBM classifier combines both to predict whether a record needs review and what kind. The exception
labels in the synthetic data are derived from these same rules, so the in-sample scores for that classifier
are near-perfect and should not be read as detection accuracy on real data.

## Competing risks

A loan ends one of two ways, default or prepayment, and each removes the loan from the population at risk of the
other. A single-risk Kaplan-Meier curve treats prepayment as non-informative censoring, which overstates default
risk. On this portfolio the naive estimate exceeds the Aalen-Johansen (competing-risk) estimate at every horizon:

| Horizon | Competing-risk CIF | Naive KM | Overstatement |
|---|---|---|---|
| 12 months | 8.45% | 8.94% | +0.49 pp |
| 24 months | 15.65% | 16.58% | +0.93 pp |
| 36 months | 21.67% | 23.13% | +1.46 pp |

The gap grows with the horizon and would be larger in a portfolio with heavier prepayment.

## Data quality

The mean per-record quality score is 97.48 / 100 (grade A), built from eight explicit, auditable penalties.
`credit_score_band` is missing far more often on older vintages, and the diagnosis flags it as Missing Not At Random.
`interest_rate` (about 3.7% missing) has no such dependency and is Missing Completely At Random. The distinction
matters: naive imputation of an MNAR gap biases every downstream model.

## Explainability and fairness

TreeSHAP global importance ranks `credit_score_ordinal`, `ltv_ordinal`, `state_freq`, `original_balance` first.
A four-fifths-rule audit runs across credit bands and states. Credit-band disparity is expected (credit score *is* the
legitimate risk signal). The per-state audit is noisy at this portfolio size, so it needs a re-check at scale before it
is treated as a finding.

Counterfactuals re-score a loan with one input improved (credit tier, DTI, LTV, or cured days past due) through the
real calibrated model. For example, one high-risk loan drops from 19.7% to 8.4% with a single LTV tier improvement.

## Stress simulation

The dashboard's sliders read a precomputed grid: 13 rate shocks (-300 to +300 bps) x 17 unemployment shocks
(0 to 8 pp). For each cell the calibrated 12-month default model is applied to the current portfolio with a
default multiplier that is a linear function of the two shocks, fit exactly through the three named scenarios
(base, adverse credit, high prepayment). Between cells the API interpolates bilinearly, so the sliders feel live
without recomputing on every drag.

Expected loss = PD x LGD x exposure with an illustrative **35% LGD**. Capital impact uses an illustrative capital base
(8% of exposure), and VaR 99% is expected loss x 2.33 (a z-score approximation, not a Monte Carlo run). These are stated
next to the numbers in the UI: read them as relative movement, not a forecast.

On the named scenarios, the portfolio's average 12-month default probability moves from 3.98% (base) to 9.88% (adverse
credit) and 3.00% (high prepayment).
