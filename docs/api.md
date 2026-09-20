# API reference

Base URL: `https://kwazm9gei8.execute-api.us-east-1.amazonaws.com/prod`

JSON in, JSON out, CORS open. There is no authentication (this is a demo over synthetic data). The stage is
throttled to 20 requests/second with a burst of 40. Transient failures (`429`, `502`, `503`, `504`) are worth
retrying; the dashboard's client does so with backoff.

| Method | Path | Purpose |
|---|---|---|
| GET | `/loans` | Scored portfolio plus whole-portfolio summary |
| GET | `/loans/{loan_id}` | One scored loan |
| GET | `/runs/{run_id}` | Status of an ingest run |
| POST | `/upload-url` | Presigned S3 URL for a tape upload |
| POST | `/stress` | Macro stress result for a rate and unemployment shock |
| POST | `/cedar/authorize` | Cedar policy decision |
| POST | `/copilot` | Reviewer copilot (three modes) |

## `GET /loans`

Query parameters (all optional): `status` (e.g. `30-59 DPD`), `min_default_prob` (e.g. `0.20`), `exceptions_only=true`.

```json
{
  "summary": {
    "total_loans": 395,
    "high_risk_count": 2,
    "exception_count": 4,
    "attention_count": 6,
    "total_exposure_usd": 57854592.96
  },
  "loans": [ { "loan_id": "LN0004361", "prob_next_12m_default": 0.4113, "...": "..." } ]
}
```

The `summary` always describes the whole portfolio, whatever filter narrows `loans`. `attention_count` counts loans
that are high risk (>= 20% default probability) or carry a rule-engine exception, once each. `loans` is sorted by
12-month default probability, highest first, and capped at 500.

## `POST /upload-url`

Returns `{ "upload_url": "...", "bucket": "...", "key": "raw/20260920-ab12cd34.csv" }`. `PUT` the CSV to `upload_url`
with `Content-Type: text/csv`. The run id is the key with `/` replaced by `_` and the `.csv` removed
(`raw_20260920-ab12cd34`).

## `GET /runs/{run_id}`

| `status` | Extra fields |
|---|---|
| `IN_PROGRESS` | none (no record yet) |
| `COMPLETE` | `loans_scored`, `high_risk_count`, `exception_count`, `stale_removed`, `completed_at` |
| `FAILED` | `error` (for example `TapeValidationError: Missing required columns: ...`), `failed_at` |

The tape needs the columns listed in `REQUIRED_COLUMNS` in `backend/ingest_pipeline/handler.py`;
`data/sample/demo_loan_tape.csv` shows the format.

## `POST /stress`

Body: `{ "rate_shock_bps": 150, "unemployment_delta_pct": 2.5 }`. Inputs outside the precomputed grid
(rate -300 to +300 bps, unemployment 0 to 8 pp) are clamped, and values between grid points are interpolated.

```json
{
  "mean_default_prob_pct": 10.26,
  "expected_loss_usd": 2007675.0,
  "car_impact_pct": 43.4,
  "var99_usd": 4677882.0,
  "baseline": { "mean_default_prob_pct": 4.66, "expected_loss_usd": 912580.0, "...": "..." },
  "assumptions": { "lgd": 0.35, "var99_method": "EL x 2.33 (log-normal z-approximation, not live Monte Carlo)" }
}
```

## `POST /cedar/authorize`

Body: `{ "userId": "u1", "role": "JuniorUnderwriter", "action": "ApproveLoan", "loan": { "loan_id": "...", "prob_next_12m_default": 0.2, "ltv_pct": 80, "current_balance": 105480, "exception_required": 0 } }`

Roles: `JuniorUnderwriter`, `SeniorUnderwriter`, `RiskCommittee`. Actions: `ApproveLoan`, `OverrideAnomaly`.

```json
{ "decision": "allow", "determining_policies": ["policy0"], "errors": [] }
```

A `deny` with an empty `determining_policies` means no policy permitted the action (Cedar denies by default).

## `POST /copilot`

| `mode` | Body | Answers |
|---|---|---|
| `memo` | `{ "loan_id": "LN0004361" }` | A credit committee memo for the loan |
| `portfolio_qa` | `{ "question": "Which loans are highest risk?" }` | A question about the whole scored portfolio |
| `stress_explain` | `{ "scenario_result": <a /stress response> }` | A plain-English reading of the scenario against its baseline |

```json
{
  "mode": "portfolio_qa",
  "model_name": "template",
  "provider": "template",
  "fallback": true,
  "fallback_reason": "bedrock: ... Operation not allowed | openai_compat: ProviderError: no LLM configured ...",
  "output": "**Highest 12-month default risk** (of 395 scored loans): ...",
  "disclaimer": "Recommendation — not a decision."
}
```

`provider` is `bedrock`, `openai_compat` or `template`. `fallback` is `true` only when no language model answered, in
which case `fallback_reason` lists why each provider was skipped.
