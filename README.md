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

## What's genuinely new here vs. the original prototype

The credit-risk modeling (5 LightGBM prediction targets, Isolation Forest anomaly
detection, the deterministic VR001–VR005 rule engine, feature engineering) is carried
over — it's already trained and validated, and retraining it wouldn't teach us anything
new about AWS. Everything around it is new, built during this hackathon:

| | Before | Now |
|---|---|---|
| Hosting | Local Streamlit | S3 + Lambda + API Gateway + Amplify, live URL |
| Trigger | Manual `make run-all` | S3 upload → EventBridge → Step Functions, automatic |
| LLM copilot | Gemini/OpenAI, single mode | **Amazon Bedrock**, 3 grounded modes |
| Governance | None | **AWS Cedar** policy-as-code authorization gate |
| Stress testing | 3 fixed scenarios | Live interactive sliders over a precomputed response grid |
| Audit log | Local JSONL file | DynamoDB, queryable |
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
# 1. Backend
cd infra
sam build
sam deploy --guided   # first time only; writes samconfig.toml

# 2. Precompute the stress grid (needed once before first deploy, or after
#    changing the demo portfolio)
python3 -m venv .venv && source .venv/bin/activate
pip install -r ../backend/ingest_pipeline/requirements.txt
python3 ../scripts/precompute_stress_grid.py

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

The original credit-risk model design, feature set, and synthetic dataset generator
(`scripts/generate_synthetic_data.py`) are the authors' own prior work. The demo
portfolio (`data/sample/demo_loan_tape.csv`) is fully synthetic — no real borrower data.
