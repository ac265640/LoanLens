# LoanLens

**Autonomous Credit Underwriting, Portfolio Risk Intelligence & Governance — built on AWS.**

Every month, a lender gets a "loan tape" — a spreadsheet of thousands of loans and how
they're performing. The industry-standard practice is to manually sample and review about
5% of it. **95% of the portfolio gets zero scrutiny, every month.**

LoanLens scores 100% of an uploaded loan tape automatically: 5 risk predictions per loan,
anomaly/exception detection, an interactive macro stress simulator, a Bedrock-grounded
reviewer copilot, and a Cedar policy-as-code governance gate — all serverless, all on AWS,
built for the WeMakeDevs × AWS "First Commit" hackathon (Bharat Builds Tour).

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
- **Lambda** — ingest pipeline (container image, ~13MB of trained model artifacts +
  pandas/lightgbm/scikit-learn), Cedar gate (Node.js), Bedrock copilot (Python), stress
  query (Python), portfolio read API (Python)
- **DynamoDB** — `loanlens-loans`, `loanlens-runs`, `loanlens-copilot-audit` (all
  on-demand billing)
- **API Gateway** — REST API fronting all Lambdas
- **Amazon Bedrock** — reviewer copilot (default: Amazon Nova Lite; swap
  `BedrockModelId` in `infra/template.yaml` for an Anthropic model once access is granted)
- **Amplify Hosting** — the React dashboard

## AWS Cedar

`backend/cedar_gate/policies/underwriting.cedar` defines real, declarative authorization
policies — e.g. a Junior Underwriter may approve a loan only when risk and LTV are within
bounds; nobody below the Risk Committee may override a fraud-flagged anomaly. Evaluated
via the official `@cedar-policy/cedar-wasm` engine (not a lookalike — verified against the
real AWS Cedar semantics, including `when`/`unless` clauses). Every loan approval or
override action in the UI runs through this gate live.

## Setup

```bash
# 1. (Optional) Regenerate data and retrain from scratch — the repo already
#    ships with trained model artifacts under backend/ingest_pipeline/models/
python3 -m venv .venv && source .venv/bin/activate
pip install -r training/requirements.txt
python3 training/generate_data.py
python3 training/train_prediction_models.py
python3 training/train_anomaly_models.py
python3 scripts/precompute_stress_grid.py   # rebuild the Shockwave grid to match

# 2. Backend
cd infra
sam build
sam deploy --guided   # first time only; writes samconfig.toml

# 3. Frontend
cd ../frontend
cp .env.example .env   # set VITE_API_URL to the ApiUrl output from sam deploy
npm install
npm run dev             # local dev
# or: npm run build && push dist/ to Amplify Hosting
```

## AI tools used during this hackathon

Claude (Claude Code) — architecture design, all AWS Lambda/Cedar/Bedrock integration
code, the React dashboard, and the Cedar-on-Lambda feasibility spike.

## Credit / licensing

The credit-risk modeling approach (feature set, target definitions, calibration
methodology) builds on the authors' own prior work. All code in this repo, the
synthetic data generator, and every trained model artifact were (re)built during this
hackathon — see `training/` and the commit history. The demo portfolio
(`data/sample/demo_loan_tape.csv`) is fully synthetic — no real borrower data.
