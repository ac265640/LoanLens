"""
Reviewer Copilot Lambda
========================
Three grounded modes:

  memo            credit committee memo for one loan
  portfolio_qa    answer a question about the scored portfolio
  stress_explain  plain-English reading of a stress-scenario result

Guardrails:
  1. The model never predicts. Every number in its context comes from the
     LightGBM / Isolation Forest / rule-engine output already stored in DynamoDB.
  2. Retrieval before generation: the facts are assembled first and are the only
     thing the model is given. Portfolio questions get whole-portfolio aggregates,
     the top loans by risk and every exception, not an arbitrary slice.
  3. Every call is audit-logged, including which provider answered and why the
     others did not.
  4. Every answer ends with "Recommendation — not a decision."

Providers, tried in order (COPILOT_PROVIDERS, default "bedrock,openai_compat"):
  bedrock        Amazon Bedrock Converse API (needs Bedrock access on the account)
  openai_compat  any OpenAI-compatible chat endpoint (Groq, Gemini, OpenAI, ...).
                 Base URL, model and API key are read from SSM Parameter Store
                 (/loanlens/llm/*, key as SecureString), never from code or env.
  template       deterministic answer built from the same facts. Always available,
                 and always labelled as a template, never presented as model output.
"""

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

TABLE_NAME = os.environ.get("LOANS_TABLE", "loanlens-loans")
AUDIT_TABLE_NAME = os.environ.get("AUDIT_TABLE", "loanlens-copilot-audit")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
PROVIDERS = [p.strip() for p in os.environ.get("COPILOT_PROVIDERS", "bedrock,openai_compat").split(",") if p.strip()]
SSM_PREFIX = os.environ.get("LLM_SSM_PREFIX", "/loanlens/llm")
DISCLAIMER = "Recommendation — not a decision."

# API Gateway cuts a request off at 29s, so no single provider call may run longer.
PROVIDER_TIMEOUT_S = 20

dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime", config=Config(connect_timeout=5, read_timeout=PROVIDER_TIMEOUT_S, retries={"max_attempts": 1}))
ssm = boto3.client("ssm")

HIGH_RISK = 0.20
WATCHLIST = 0.08

DRIVER_LABELS = {
    "days_past_due": "days past due",
    "credit_score_ordinal": "credit score tier",
    "balance_to_orig_ratio": "balance vs. original",
    "interest_rate_imputed": "interest rate",
    "dpd_roll_max_6m": "6-month peak days past due",
    "balance_change_1m_pct": "1-month balance change",
}

SYSTEM_PROMPT = (
    "You are a credit-risk review assistant for a loan servicer. Answer using ONLY the facts in the JSON the user "
    "provides. Never invent loans, numbers or causes. Probabilities in the JSON are fractions (0.41 means 41%); "
    "write them as percentages. Be concise and specific, and cite loan IDs. If the facts do not answer the "
    f'question, say so plainly. End with the exact text: "{DISCLAIMER}"'
)


# ---------------------------------------------------------------- data access


def _floatify(obj):
    if isinstance(obj, Decimal):
        # whole numbers stay ints; DynamoDB returns every number as Decimal
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, dict):
        return {k: _floatify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floatify(v) for v in obj]
    return obj


def _decimalize(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _decimalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimalize(v) for v in obj]
    return obj


def _get_loan(loan_id: str):
    item = dynamodb.Table(TABLE_NAME).get_item(Key={"loan_id": str(loan_id)}).get("Item")
    return _floatify(item) if item else None


def _load_portfolio() -> list:
    """Every scored loan. A single scan call returns at most 1 MB, so walk the pages."""
    table, items, kwargs = dynamodb.Table(TABLE_NAME), [], {}
    while True:
        page = table.scan(**kwargs)
        items += page.get("Items", [])
        if "LastEvaluatedKey" not in page:
            return [_floatify(i) for i in items]
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


# -------------------------------------------------------------------- context


def _tier(p: float) -> str:
    return "High Risk" if p >= HIGH_RISK else "Watch-list" if p >= WATCHLIST else "Healthy"


def build_loan_context(loan: dict) -> dict:
    return {
        "loan_id": loan.get("loan_id"),
        "reporting_month": loan.get("reporting_month"),
        "state": loan.get("state"),
        "current_status": loan.get("current_status"),
        "days_past_due": loan.get("days_past_due"),
        "current_balance_usd": loan.get("current_balance"),
        "credit_score_band": loan.get("credit_score_band"),
        "ltv_band": loan.get("ltv_band"),
        "prob_next_3m_delinquency": loan.get("prob_next_3m_delinquency"),
        "prob_next_6m_delinquency": loan.get("prob_next_6m_delinquency"),
        "prob_next_12m_default": loan.get("prob_next_12m_default"),
        "prob_next_12m_prepayment": loan.get("prob_next_12m_prepayment"),
        "predicted_next_state": loan.get("next_state"),
        "anomaly_score": loan.get("anomaly_score"),
        "exception_required": loan.get("exception_required"),
        "exception_type": loan.get("exception_type"),
        "top_risk_drivers": [loan.get(k) for k in ("top_driver_1", "top_driver_2", "top_driver_3") if loan.get(k)],
        "recommended_action": loan.get("recommended_action"),
        "risk_tier": _tier(loan.get("prob_next_12m_default") or 0),
    }


def _compact(loan: dict) -> dict:
    return {
        "loan_id": loan.get("loan_id"),
        "state": loan.get("state"),
        "status": loan.get("current_status"),
        "balance_usd": loan.get("current_balance"),
        "credit_score_band": loan.get("credit_score_band") or "Unknown",
        "prob_12m_default": loan.get("prob_next_12m_default") or 0,
        "exception_type": loan.get("exception_type") if loan.get("exception_required") == 1 else None,
        "recommended_action": loan.get("recommended_action"),
    }


def build_portfolio_context(loans: list, top_n: int = 10, exceptions_n: int = 10) -> dict:
    """Whole-portfolio facts a portfolio question can be answered from."""
    p12 = lambda l: l.get("prob_next_12m_default") or 0  # noqa: E731
    n = len(loans)
    exceptions = [l for l in loans if l.get("exception_required") == 1]

    by_band = {}
    for l in loans:
        band = l.get("credit_score_band") or "Unknown"
        b = by_band.setdefault(band, {"loans": 0, "exposure_usd": 0.0, "_p_sum": 0.0, "high_risk": 0})
        b["loans"] += 1
        b["exposure_usd"] += l.get("current_balance") or 0
        b["_p_sum"] += p12(l)
        b["high_risk"] += 1 if p12(l) >= HIGH_RISK else 0
    for b in by_band.values():
        b["avg_prob_12m_default"] = round(b.pop("_p_sum") / b["loans"], 4)
        b["exposure_usd"] = round(b["exposure_usd"], 2)

    return {
        "summary": {
            "total_loans": n,
            "total_exposure_usd": round(sum(l.get("current_balance") or 0 for l in loans), 2),
            "high_risk_count": sum(1 for l in loans if p12(l) >= HIGH_RISK),
            "watchlist_count": sum(1 for l in loans if WATCHLIST <= p12(l) < HIGH_RISK),
            "exception_count": len(exceptions),
            "avg_prob_12m_default": round(sum(p12(l) for l in loans) / n, 4) if n else 0,
            "thresholds": {"high_risk": HIGH_RISK, "watchlist": WATCHLIST},
        },
        "status_mix": dict(Counter(l.get("current_status") for l in loans)),
        "by_credit_band": by_band,
        "top_risk_loans": [_compact(l) for l in sorted(loans, key=p12, reverse=True)[:top_n]],
        "exception_types": dict(Counter(l.get("exception_type") for l in exceptions)),
        "exception_loans": [_compact(l) for l in sorted(exceptions, key=lambda l: l.get("anomaly_score") or 0, reverse=True)[:exceptions_n]],
    }


# ------------------------------------------------------------------- prompts

PROMPTS = {
    "memo": """Write a credit committee memo for this loan in three short parts:
Part A: Key risk and underwriting assessment. Part B: Data quality and anomaly flags. Part C: Recommended action plan.

LOAN FACTS AND MODEL OUTPUTS:
{context}""",
    "portfolio_qa": """QUESTION: {question}

PORTFOLIO FACTS (computed over all {n} scored loans):
{context}""",
    "stress_explain": """Explain this macro stress scenario result for a non-technical committee member: what changed against
the baseline, why it matters, and what it means for the portfolio.

SCENARIO RESULT (with baseline for comparison):
{context}""",
}


# ------------------------------------------------- deterministic (template) answers


def _pct(x) -> str:
    return f"{(x or 0) * 100:.1f}%"


def _usd(x) -> str:
    return f"${(x or 0):,.0f}"


def template_memo(ctx: dict) -> str:
    p12 = ctx.get("prob_next_12m_default") or 0
    drivers = [DRIVER_LABELS.get(d, d) for d in ctx.get("top_risk_drivers", [])]
    if ctx.get("exception_required") == 1:
        quality = f"Flagged for review: {ctx.get('exception_type')} (anomaly score {ctx.get('anomaly_score')})."
    else:
        quality = f"No rule-engine exception (anomaly score {ctx.get('anomaly_score')})."
    return (
        f"### Credit review: loan {ctx.get('loan_id')}\n\n"
        f"**Assessment.** {_tier(p12)}. 12-month default probability {_pct(p12)} "
        f"(3-month delinquency {_pct(ctx.get('prob_next_3m_delinquency'))}, 6-month {_pct(ctx.get('prob_next_6m_delinquency'))}). "
        f"Status {ctx.get('current_status')}, {ctx.get('days_past_due')} days past due, balance {_usd(ctx.get('current_balance_usd'))}, "
        f"{ctx.get('credit_score_band') or 'unknown'} credit band, {ctx.get('state')}.\n\n"
        f"**Main risk drivers.** {', '.join(drivers) if drivers else 'none flagged'}.\n\n"
        f"**Data quality.** {quality}\n\n"
        f"**Recommended action.** {ctx.get('recommended_action')}.\n\n"
        f"*{DISCLAIMER}*"
    )


def template_portfolio_answer(question: str, ctx: dict) -> str:
    s = ctx["summary"]
    if s["total_loans"] == 0:
        return f"No loans have been scored yet. Upload a loan tape first.\n\n*{DISCLAIMER}*"

    q = (question or "").lower()
    parts = []

    if re.search(r"highest|riskiest|risky|top|worst|high[- ]risk|most at risk|default", q):
        top = ctx["top_risk_loans"][:5]
        lines = [f"**Highest 12-month default risk** (of {s['total_loans']} scored loans):"]
        for l in top:
            lines.append(f"- {l['loan_id']} ({l['state']}, {l['status']}): {_pct(l['prob_12m_default'])}, balance {_usd(l['balance_usd'])}. Suggested: {l['recommended_action']}")
        lines.append(f"{s['high_risk_count']} loans are High Risk (20% or more) and {s['watchlist_count']} more are on the Watch-list (8% to 20%).")
        parts.append("\n".join(lines))

    if re.search(r"exception|anomal|data quality|flag|conflict|discrepan|review", q):
        types = ctx["exception_types"]
        lines = [f"**Exceptions:** {s['exception_count']} of {s['total_loans']} loans need review."]
        if types:
            lines.append("By type: " + ", ".join(f"{t} ({c})" for t, c in sorted(types.items(), key=lambda kv: -kv[1])) + ".")
        for l in ctx["exception_loans"][:5]:
            lines.append(f"- {l['loan_id']}: {l['exception_type']}, balance {_usd(l['balance_usd'])}")
        parts.append("\n".join(lines))

    if re.search(r"credit|band|vulnerab|segment|score|weak|fragile", q):
        bands = sorted(ctx["by_credit_band"].items(), key=lambda kv: -kv[1]["avg_prob_12m_default"])
        lines = ["**Credit bands, most to least vulnerable** (average 12-month default probability):"]
        for band, b in bands:
            lines.append(f"- {band}: {_pct(b['avg_prob_12m_default'])} across {b['loans']} loans ({b['high_risk']} high-risk), exposure {_usd(b['exposure_usd'])}")
        parts.append("\n".join(lines))

    if not parts:
        mix = ", ".join(f"{k} {v}" for k, v in sorted(ctx["status_mix"].items(), key=lambda kv: -kv[1]))
        parts.append(
            f"**Portfolio:** {s['total_loans']} loans, {_usd(s['total_exposure_usd'])} exposure, average 12-month default probability "
            f"{_pct(s['avg_prob_12m_default'])}. {s['high_risk_count']} High Risk, {s['watchlist_count']} Watch-list, "
            f"{s['exception_count']} exceptions. Status mix: {mix}."
        )

    return "\n\n".join(parts) + f"\n\n*{DISCLAIMER}*"


def template_stress_explanation(result: dict) -> str:
    base = result.get("baseline") or {}
    if not base or "expected_loss_usd" not in result:
        return f"Stress result: {json.dumps(result)[:400]}\n\n*{DISCLAIMER}*"

    def delta(key):
        b, c = base.get(key) or 0, result.get(key) or 0
        return c - b, ((c - b) / b * 100 if b else 0)

    d_pd, _ = delta("mean_default_prob_pct")
    d_el, el_rel = delta("expected_loss_usd")
    rate, unemp = result.get("rate_shock_bps", 0), result.get("unemployment_delta_pct", 0)
    direction = "rises" if d_el > 0 else "falls" if d_el < 0 else "is unchanged"
    return (
        f"**Scenario:** interest rates {rate:+.0f} bps and unemployment {unemp:+.2f} pp.\n\n"
        f"The average 12-month default probability moves from {base.get('mean_default_prob_pct', 0):.2f}% to "
        f"{result.get('mean_default_prob_pct', 0):.2f}% ({d_pd:+.2f} pp). Expected loss {direction} from {_usd(base.get('expected_loss_usd'))} to "
        f"{_usd(result.get('expected_loss_usd'))} ({el_rel:+.0f}%). Capital impact is {result.get('car_impact_pct', 0):.1f}% of the assumed capital base "
        f"and 99% VaR is {_usd(result.get('var99_usd'))}.\n\n"
        f"Loss uses an illustrative 35% loss-given-default and a z-score VaR approximation, so read the figures as relative movement, not a forecast.\n\n"
        f"*{DISCLAIMER}*"
    )


# ------------------------------------------------------------------- providers


class ProviderError(Exception):
    pass


_bedrock_blocked_until = 0.0


def _invoke_bedrock(prompt: str):
    """Amazon Bedrock Converse. After an access refusal, skip it for 5 minutes so
    every request doesn't pay for a call that is known to fail."""
    global _bedrock_blocked_until
    if time.time() < _bedrock_blocked_until:
        raise ProviderError("skipped: Bedrock refused access moments ago")
    try:
        resp = bedrock.converse(
            modelId=BEDROCK_MODEL_ID,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"temperature": 0.2, "maxTokens": 700},
        )
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("AccessDeniedException", "ValidationException"):
            _bedrock_blocked_until = time.time() + 300
        raise
    return resp["output"]["message"]["content"][0]["text"], f"bedrock/{BEDROCK_MODEL_ID}"


_llm_cache = {"at": 0.0, "cfg": None}


def _llm_config():
    """OpenAI-compatible endpoint settings from SSM. A found config is cached for
    5 minutes; a missing one for 20 seconds so setting the key takes effect quickly."""
    now = time.time()
    ttl = 300 if _llm_cache["cfg"] else 20
    if now - _llm_cache["at"] < ttl:
        return _llm_cache["cfg"]

    names = [f"{SSM_PREFIX}/{k}" for k in ("api_key", "base_url", "model")]
    resp = ssm.get_parameters(Names=names, WithDecryption=True)
    values = {p["Name"].rsplit("/", 1)[1]: p["Value"] for p in resp.get("Parameters", [])}
    cfg = values if values.get("api_key") and values.get("base_url") and values.get("model") else None
    _llm_cache.update(at=now, cfg=cfg)
    return cfg


def _provider_label(base_url: str) -> str:
    host = urlparse(base_url).netloc.lower()
    for needle, label in (("groq", "groq"), ("googleapis", "gemini"), ("openai.com", "openai"), ("openrouter", "openrouter")):
        if needle in host:
            return label
    return host or "openai-compatible"


def _invoke_openai_compat(prompt: str):
    cfg = _llm_config()
    if not cfg:
        raise ProviderError(f"no LLM configured (set {SSM_PREFIX}/api_key, base_url and model in SSM Parameter Store)")

    body = json.dumps({
        "model": cfg["model"],
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 1500,
    }).encode()
    req = urllib.request.Request(
        cfg["base_url"].rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
            # Some providers sit behind a WAF that rejects the default Python-urllib agent.
            "User-Agent": "loanlens-copilot/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=PROVIDER_TIMEOUT_S) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        raise ProviderError(f"HTTP {e.code} from {_provider_label(cfg['base_url'])}: {detail}") from None
    except urllib.error.URLError as e:
        raise ProviderError(f"cannot reach {_provider_label(cfg['base_url'])}: {e.reason}") from None

    text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return text, f"{_provider_label(cfg['base_url'])}/{cfg['model']}"


_PROVIDER_FUNCS = {
    "bedrock": lambda prompt: _invoke_bedrock(prompt),
    "openai_compat": lambda prompt: _invoke_openai_compat(prompt),
}


def _call_providers(prompt: str):
    """First provider that returns a real answer wins. Returns (text, model, provider, errors)."""
    errors = []
    for name in PROVIDERS:
        fn = _PROVIDER_FUNCS.get(name)
        if not fn:
            continue
        try:
            text, model = fn(prompt)
            if not text or len(text.strip()) < 40:
                raise ProviderError("empty or too-short response")
            return text.strip(), model, name, errors
        except Exception as e:  # noqa: BLE001  any provider failure must fall through to the next
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:220]}")
            log.warning("provider %s failed: %s", name, e)
    return None, None, None, errors


# ---------------------------------------------------------------------- audit


def _log_audit(mode, prompt, context, output, model_name, provider, errors):
    try:
        dynamodb.Table(AUDIT_TABLE_NAME).put_item(Item=_decimalize({
            "call_id": f"{mode}-{datetime.now(timezone.utc).timestamp()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "model_name": model_name,
            "provider": provider,
            "provider_errors": errors,
            "retrieved_context": context,
            "prompt": prompt,
            "output": output,
            "disclaimer": DISCLAIMER,
        }))
    except Exception:  # noqa: BLE001  an audit-write failure must not take the answer down with it
        log.exception("audit log write failed")


# -------------------------------------------------------------------- handler


def handler(event, context_):
    body = json.loads(event["body"]) if isinstance(event.get("body"), str) else (event.get("body") or event)
    mode = body.get("mode", "memo")

    if mode == "memo":
        loan = _get_loan(body.get("loan_id"))
        if not loan:
            return _respond(404, {"error": f"loan {body.get('loan_id')} not found"})
        ctx = build_loan_context(loan)
        prompt = PROMPTS["memo"].format(context=json.dumps(ctx, indent=2))
        template = lambda: template_memo(ctx)  # noqa: E731

    elif mode == "portfolio_qa":
        question = str(body.get("question", ""))[:500]
        ctx = build_portfolio_context(_load_portfolio())
        prompt = PROMPTS["portfolio_qa"].format(question=question, n=ctx["summary"]["total_loans"], context=json.dumps(ctx, indent=2))
        template = lambda: template_portfolio_answer(question, ctx)  # noqa: E731

    elif mode == "stress_explain":
        ctx = body.get("scenario_result")
        if not isinstance(ctx, dict) or not ctx:
            return _respond(400, {"error": "scenario_result is required"})
        prompt = PROMPTS["stress_explain"].format(context=json.dumps(ctx, indent=2))
        template = lambda: template_stress_explanation(ctx)  # noqa: E731

    else:
        return _respond(400, {"error": f"unknown mode {mode}"})

    output, model_name, provider, errors = _call_providers(prompt)
    used_template = output is None
    if used_template:
        output, model_name, provider = template(), "template", "template"

    if DISCLAIMER not in output:
        output += f"\n\n*{DISCLAIMER}*"

    _log_audit(mode, prompt, ctx, output, model_name, provider, errors)

    return _respond(200, {
        "mode": mode,
        "model_name": model_name,
        "provider": provider,
        "fallback": used_template,
        "fallback_reason": " | ".join(errors) if used_template and errors else None,
        "output": output,
        "disclaimer": DISCLAIMER,
    })


def _respond(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body, default=str),
    }
