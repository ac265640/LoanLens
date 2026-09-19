"""
Bedrock Reviewer Copilot Lambda
================================
Single Lambda, three grounded modes (replaces the original Gemini/OpenAI
copilot's single mode):

  memo          - full Credit Committee underwriting memo for one loan
  portfolio_qa  - natural-language question answered ONLY from loans that
                  actually match in DynamoDB (no invented facts)
  stress_explain - plain-English explanation of a precomputed stress delta

Guardrails carried over from the original design:
  1. The LLM never predicts — every number comes from the LightGBM/Isolation
     Forest models already written to DynamoDB by the ingest pipeline.
  2. Retrieval-before-generation — grounding facts are pulled from DynamoDB
     first and injected into the prompt; the model can only reference them.
  3. Every call is logged verbatim to the audit table.
  4. Every output ends with "Recommendation — not a decision."
"""

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

TABLE_NAME = os.environ.get("LOANS_TABLE", "loanlens-loans")
AUDIT_TABLE_NAME = os.environ.get("AUDIT_TABLE", "loanlens-copilot-audit")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
DISCLAIMER = "Recommendation — not a decision."

dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime")


def _decimalize(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _decimalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimalize(v) for v in obj]
    return obj


def _floatify(obj):
    if isinstance(obj, Decimal):
        # whole numbers stay ints (344, not 344.0); DynamoDB returns every number as Decimal
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, dict):
        return {k: _floatify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floatify(v) for v in obj]
    return obj


def _get_loan(loan_id: str):
    table = dynamodb.Table(TABLE_NAME)
    resp = table.get_item(Key={"loan_id": str(loan_id)})
    item = resp.get("Item")
    return _floatify(item) if item else None


def _query_portfolio(filters: dict, limit: int = 25):
    """Best-effort scan with filters for grounded portfolio Q&A. Small demo
    portfolios only — a real deployment would back this with an index."""
    table = dynamodb.Table(TABLE_NAME)
    scan_kwargs = {"Limit": 500}
    resp = table.scan(**scan_kwargs)
    items = [_floatify(i) for i in resp.get("Items", [])]

    if filters.get("min_default_prob") is not None:
        items = [i for i in items if i.get("prob_next_12m_default", 0) >= filters["min_default_prob"]]
    if filters.get("state"):
        items = [i for i in items if i.get("state") == filters["state"]]
    if filters.get("exception_required_only"):
        items = [i for i in items if i.get("exception_required") == 1]

    return items[:limit]


def build_loan_context(loan: dict) -> dict:
    return {
        "loan_id": loan.get("loan_id"),
        "reporting_month": loan.get("reporting_month"),
        "current_status": loan.get("current_status"),
        "days_past_due": loan.get("days_past_due"),
        "current_balance_usd": loan.get("current_balance"),
        "credit_score_band": loan.get("credit_score_band"),
        "state": loan.get("state"),
        "prob_next_3m_delinquency": loan.get("prob_next_3m_delinquency"),
        "prob_next_6m_delinquency": loan.get("prob_next_6m_delinquency"),
        "prob_next_12m_default": loan.get("prob_next_12m_default"),
        "prob_next_12m_prepayment": loan.get("prob_next_12m_prepayment"),
        "predicted_next_state": loan.get("next_state"),
        "anomaly_score": loan.get("anomaly_score"),
        "exception_required": loan.get("exception_required"),
        "exception_type": loan.get("exception_type"),
        "top_risk_drivers": [loan.get("top_driver_1"), loan.get("top_driver_2"), loan.get("top_driver_3")],
        "recommended_action": loan.get("recommended_action"),
    }


PROMPT_TEMPLATES = {
    "memo": """You are an expert Credit & Loan Quality Reviewer assisting an operational underwriter.
Use ONLY the facts below — never invent numbers, never assume anything not stated.

LOAN FACTS AND MODEL OUTPUTS:
{context}

Write a 3-part Credit Committee memo:
- Part A: Key Risk & Underwriting Assessment
- Part B: Data Quality & Anomaly Flags
- Part C: Recommended Action Plan
End with the exact text: "Recommendation — not a decision." """,

    "portfolio_qa": """You are a portfolio risk analyst assistant. Answer the question using ONLY the
matching loan records below. If no records match, say so plainly — do not guess.

QUESTION: {question}

MATCHING LOAN RECORDS ({n} of them):
{context}

Give a concise, factual answer grounded only in the records above. End with the exact text:
"Recommendation — not a decision." """,

    "stress_explain": """You are a macro risk advisor. Explain the following stress scenario result in
plain English for a non-technical committee member. Use ONLY the numbers given.

STRESS SCENARIO RESULT:
{context}

Explain what changed, why it matters, and what it means for the portfolio. End with the exact text:
"Recommendation — not a decision." """,
}


def _deterministic_fallback(mode: str, context: dict, question: str = "") -> str:
    if mode == "memo":
        p_def = context.get("prob_next_12m_default", 0) or 0
        risk_tier = "High Risk" if p_def >= 0.20 else "Moderate Risk" if p_def >= 0.08 else "Low Risk"
        return (
            f"### Reviewer Note: Loan {context.get('loan_id')}\n\n"
            f"**Part A: Key Risk Assessment** — {risk_tier} "
            f"(12M Default Probability: {p_def:.1%}, Status: {context.get('current_status')}, "
            f"DPD: {context.get('days_past_due')}).\n\n"
            f"**Part B: Data Quality** — Anomaly score {context.get('anomaly_score')}, "
            f"Exception: {context.get('exception_type')}.\n\n"
            f"**Part C: Recommended Action** — {context.get('recommended_action')}.\n\n"
            f"*{DISCLAIMER}*"
        )
    if mode == "portfolio_qa":
        n = context.get("n", 0)
        return f"Found {n} matching loan(s) for: \"{question}\". See table for details.\n\n*{DISCLAIMER}*"
    return f"Stress scenario computed from precomputed grid — see figures above.\n\n*{DISCLAIMER}*"


def _invoke_bedrock(prompt: str):
    resp = bedrock.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"temperature": 0.2, "maxTokens": 800},
    )
    text = resp["output"]["message"]["content"][0]["text"]
    return text, BEDROCK_MODEL_ID


def _log_audit(mode: str, prompt: str, context: dict, output: str, model_name: str):
    table = dynamodb.Table(AUDIT_TABLE_NAME)
    table.put_item(Item=_decimalize({
        "call_id": f"{mode}-{datetime.now(timezone.utc).timestamp()}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "model_name": model_name,
        "retrieved_context": context,
        "prompt": prompt,
        "output": output,
        "disclaimer": DISCLAIMER,
    }))


def handler(event, context_):
    body = json.loads(event["body"]) if isinstance(event.get("body"), str) else (event.get("body") or event)
    mode = body.get("mode", "memo")

    if mode == "memo":
        loan = _get_loan(body.get("loan_id"))
        if not loan:
            return _respond(404, {"error": f"loan {body.get('loan_id')} not found"})
        ctx = build_loan_context(loan)
        prompt = PROMPT_TEMPLATES["memo"].format(context=json.dumps(ctx, indent=2))

    elif mode == "portfolio_qa":
        question = body.get("question", "")
        matches = _query_portfolio(body.get("filters", {}))
        ctx = {"n": len(matches), "loans": [build_loan_context(m) for m in matches[:15]]}
        prompt = PROMPT_TEMPLATES["portfolio_qa"].format(
            question=question, n=len(matches), context=json.dumps(ctx["loans"], indent=2)
        )

    elif mode == "stress_explain":
        ctx = body.get("scenario_result", {})
        prompt = PROMPT_TEMPLATES["stress_explain"].format(context=json.dumps(ctx, indent=2))

    else:
        return _respond(400, {"error": f"unknown mode {mode}"})

    model_name = "deterministic-grounded-fallback"
    fallback_reason = None
    try:
        output, model_name = _invoke_bedrock(prompt)
    except Exception as e:
        fallback_reason = f"{type(e).__name__}: {e}"[:300]
        log.warning(f"Bedrock call failed ({e}); using deterministic grounded fallback.")
        output = _deterministic_fallback(mode, ctx if mode != "portfolio_qa" else {"n": ctx["n"]}, body.get("question", ""))

    if DISCLAIMER not in output:
        output += f"\n\n*{DISCLAIMER}*"

    _log_audit(mode, prompt, ctx, output, model_name)

    return _respond(200, {
        "mode": mode,
        "model_name": model_name,
        "fallback": fallback_reason is not None,
        "fallback_reason": fallback_reason,
        "output": output,
        "disclaimer": DISCLAIMER,
    })


def _respond(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body, default=str),
    }
