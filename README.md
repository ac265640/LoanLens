# LoanLens

**Autonomous Credit Underwriting, Portfolio Risk Intelligence & Governance — built on AWS.**

Every month, a lender gets a "loan tape" — a spreadsheet of thousands of loans and how
they're performing. The industry-standard practice is to manually sample and review about
5% of it. **95% of the portfolio gets zero scrutiny, every month.**

LoanLens scores 100% of an uploaded loan tape automatically: 5 risk predictions per loan,
anomaly/exception detection, an interactive macro stress simulator, a Bedrock-grounded
reviewer copilot, and a Cedar policy-as-code governance gate — all serverless, all on AWS,
built for the WeMakeDevs × AWS "First Commit" hackathon (Bharat Builds Tour).

## Live demo

- **Dashboard:** https://main.d3uibhd8oe3ebl.amplifyapp.com
- **API:** `https://kwazm9gei8.execute-api.us-east-1.amazonaws.com/prod` (try `GET /loans`)

To see it work end to end:

1. Open the dashboard, then drop `data/sample/demo_loan_tape.csv` on the upload area. That
   uploads to S3, EventBridge starts a Step Functions run, and a container Lambda scores
   every loan into DynamoDB. The table refreshes when the run completes.
2. Open the **High Risk** tab and click a loan. In the *Cedar Policy Compliance Gate*, run
   `ApproveLoan` as each role: the 41% loan is denied to a Junior Underwriter and allowed to a
   Senior Underwriter or the Risk Committee. On an **Exceptions** loan, run `OverrideAnomaly`:
   only the Risk Committee may override a flagged loan.
3. Move the **Shockwave** sliders (rate and unemployment shock) for live expected loss,
   capital impact and VaR.

## Why this architecture

Everything here is **serverless and scales to zero** — no idle EC2, no SageMaker endpoint,
no OpenSearch domain — specifically to stay well inside a $100 AWS credit budget while
still being a real, deployed, judge-clickable Ship It submission.

```
                                   ┌─────────────────────────────┐
                                   │   React + Vite Dashboard     │
                                   │   (Amplify Hosting)          │
                                   └───────────────┬───────────────┘
                                                   │ REST (API Gateway)
                     ┌─────────────────────────────┼─────────────────────────────┐
                     ▼                             ▼                             ▼
       ┌──────────────────────┐      ┌──────────────────────┐      ┌──────────────────────┐
       │   Cedar Policy Gate   │      │   Bedrock Copilot     │      │   Stress Query        │
       │   (Node.js Lambda,    │      │   (Python Lambda,     │      │   (Python Lambda,     │
       │   @cedar-policy/      │      │   Amazon Nova/Claude) │      │   precomputed grid)   │
       │   cedar-wasm)         │      │                       │      │                       │
       └──────────────────────┘      └───────────┬───────────┘      └──────────────────────┘
                                                   │
                                        ┌──────────▼──────────┐
                                        │  DynamoDB            │
                                        │  loans / runs /      │
                                        │  copilot-audit        │
                                        └──────────▲────────────┘
                                                   │
       ┌───────────────────────────────────────────┴──────────────────────────────┐
       │  S3 (raw/ loan tapes) → EventBridge → Step Functions → Ingest Pipeline    │
       │  Lambda (container image: LightGBM x5, Isolation Forest, VR001-VR005)     │
       └────────────────────────────────────────────────────────────────────────┘
```

## Built during this hackathon

Every model in `backend/ingest_pipeline/models/` is trained by the scripts in
`training/`, against this repo's own synthetic portfolio (`training/generate_data.py`) —
nothing here is a pre-trained artifact dropped in from elsewhere. See `training/*.py` and
`backend/ingest_pipeline/models/prediction_metrics.json` for the real, reproducible
training run:

1. `training/generate_data.py` — synthetic loan portfolio (statics + monthly performance
   panel + a secondary servicer feed with injected conflicts), fully self-contained, no
   real borrower data
2. `training/splitter.py` — time-aware cohort split (train/val by origination month, with
   a hard loan_id-leakage assertion)
3. `training/train_prediction_models.py` — 4 binary LightGBM targets (3M/6M delinquency,
   12M default, 12M prepayment) + 1 multiclass (next-month status), Platt-calibrated on
   the held-out validation cohort
4. `training/train_anomaly_models.py` — Isolation Forest + a hybrid LightGBM exception
   classifier combining it with the deterministic VR001–VR005 rules
5. `training/profile_data.py` — per-record data quality score (8 auditable penalty rules)
   + MCAR/MAR/MNAR missingness diagnosis (97.48/100, Grade A on this portfolio)
6. `training/survival_analysis.py` — Aalen-Johansen competing-risk CIF vs. naive
   single-risk Kaplan-Meier (default and prepayment are competing terminal events —
   treating them as independent overstates default risk) + empirical Markov transition
   matrix
7. `training/explainability.py` — TreeSHAP global/local attributions, calibration
   reliability diagnostics (ECE), and a four-fifths-rule disparate-impact fairness audit
8. `training/scenario_segments.py` — the 3 named macro scenarios broken down by credit
   band, vintage era, and state (complements the dashboard's live Shockwave sliders)
9. `training/counterfactuals.py` — "what single change reduces this loan's risk most",
   answered by re-running the real calibrated model on perturbed features, not a proxy
10. `training/conformal_intervals.py` — distribution-free 90% prediction intervals,
    empirically validated at 90.28% coverage on a held-out split
11. `tests/` (pytest, 22 tests) + `backend/cedar_gate/test_policies.mjs` (8 Cedar
    authorization scenarios) — `make test cedar-test` runs both

Everything downstream of the trained models — the AWS deployment, the Cedar governance
gate, the Bedrock copilot, the live stress simulator, the dashboard — is new, built
specifically for this hackathon:

| | Elsewhere-style prototype | LoanLens (this repo) |
|---|---|---|
| Hosting | Local Streamlit | S3 + Lambda + API Gateway + Amplify, live URL |
| Trigger | Manual pipeline run | S3 upload → EventBridge → Step Functions, automatic |
| LLM copilot | Single-mode, non-AWS LLM | **Amazon Bedrock**, 3 grounded modes |
| Governance | None | **AWS Cedar** policy-as-code authorization gate |
| Stress testing | 3 fixed scenarios | Live interactive sliders over a precomputed response grid |
| Audit log | Local file | DynamoDB, queryable |
| UI | Streamlit multi-page | React + Vite + Tailwind, dark glassmorphic |

## AWS services used

- **S3** — loan tape uploads (`raw/` prefix triggers the pipeline)
- **EventBridge** — S3 object-created events routed to Step Functions
- **Step Functions** — orchestrates the ingest pipeline
- **Lambda** — ingest pipeline (arm64 container image, Python 3.12, ~13MB of trained model
  artifacts + pandas/lightgbm/scikit-learn), Cedar gate (Node.js 22), Bedrock copilot
  (Python), stress query (Python), portfolio read API (Python)
- **DynamoDB** — `loanlens-loans`, `loanlens-runs`, `loanlens-copilot-audit` (all
  on-demand billing)
- **API Gateway** — REST API fronting all Lambdas
- **Amazon Bedrock** — reviewer copilot (default: Amazon Nova Lite; change the
  `BedrockModelId` parameter for another model). If the model can't be reached, the API
  returns `fallback: true` and the UI labels the answer as a template instead of presenting
  it as model output
- **Amplify Hosting** — the React dashboard (`scripts/deploy_frontend.sh`)
- **CloudWatch Logs** — per-function log groups with 7-day retention

## AWS Cedar

`backend/cedar_gate/policies/underwriting.cedar` defines real, declarative authorization
policies — e.g. a Junior Underwriter may approve a loan only when risk and LTV are within
bounds; nobody below the Risk Committee may override a fraud-flagged anomaly. Evaluated
via the official `@cedar-policy/cedar-wasm` engine (not a lookalike — verified against the
real AWS Cedar semantics, including `when`/`unless` clauses). Every loan approval or
override action in the UI runs through this gate live. Cedar has no floating point, so
policies compare integer percentages: risk is the 12M default probability x 100, and LTV is
the upper bound of the loan's LTV band (the conservative reading).

## Setup

```bash
# 1. (Optional) Regenerate data and retrain everything from scratch — the
#    repo already ships with trained model artifacts and analysis reports
#    under backend/ingest_pipeline/models/
make setup            # creates .venv, installs training/requirements.txt
make run-all           # generate -> train -> analyze -> test, ~60-90s
# (see the Makefile for the individual targets this chains together)

# 2. Backend (needs Docker running, and AWS credentials via `aws configure`)
make deploy-backend    # sam build && sam deploy; deploy config is committed in infra/samconfig.toml

# 3. Frontend
make deploy-frontend   # builds against the stack's ApiUrl and publishes to Amplify Hosting
# local dev instead:
cd frontend && cp .env.example .env    # set VITE_API_URL to the ApiUrl stack output
npm install && npm run dev
```

The demo tape (`data/sample/demo_loan_tape.csv`) is an as-of snapshot built from the
synthetic panel by `make demo-tape` (`scripts/build_demo_tape.py`).

## Known limitations

- The API has no authentication. It is a demo deployment over synthetic data, so every
  endpoint, including tape upload, is open.
- The Bedrock copilot needs Bedrock model access on the AWS account. Without it, answers are
  clearly labeled template answers.
- Everything is synthetic. Expected loss uses an illustrative 35% LGD, and the capital and
  VaR figures use an illustrative capital base and a z-score approximation (not a live Monte
  Carlo); the UI says so next to the numbers.
- Models are trained on a 5,000-loan portfolio, so the absolute AUCs (0.62 to 0.81 across
  targets, see `backend/ingest_pipeline/models/prediction_metrics.json`) are lower than a
  full-scale run would give, and the per-segment fairness audit is noisy at this size.
- A tape replaces the portfolio snapshot: loans absent from the newest tape are removed.

## AI tools used during this hackathon

Claude (Claude Code) — architecture design, all AWS Lambda/Cedar/Bedrock integration
code, the React dashboard, and the Cedar-on-Lambda feasibility spike.

## Credit / licensing

The credit-risk modeling approach (feature set, target definitions, calibration
methodology) builds on the authors' own prior work. All code in this repo, the
synthetic data generator, and every trained model artifact were (re)built during this
hackathon — see `training/` and the commit history. The demo portfolio
(`data/sample/demo_loan_tape.csv`) is fully synthetic — no real borrower data.
