"""
Copilot Lambda: provider chain, grounding, and deterministic answers.

Uses a local fake OpenAI-compatible server, fake DynamoDB/SSM, and a real
botocore ClientError for the Bedrock refusal, so the chain and its fallbacks
are verified end to end without any external account.
"""

import importlib.util
import json
import os
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

_spec = importlib.util.spec_from_file_location(
    "copilot_handler", Path(__file__).resolve().parents[1] / "backend" / "copilot" / "handler.py"
)
cp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cp)

LONG_ANSWER = "LN0000002 has the highest 12-month default risk at 41.0%, followed by LN0000001. Recommendation — not a decision."


# ------------------------------------------------------------------ test doubles


def _loan(loan_id, p12, **kw):
    base = {
        "loan_id": loan_id, "state": "TX", "current_status": "Current", "days_past_due": 0,
        "current_balance": 100000, "credit_score_band": "660-699", "ltv_band": "70-80%",
        "prob_next_3m_delinquency": 0.02, "prob_next_6m_delinquency": 0.04, "prob_next_12m_default": p12,
        "prob_next_12m_prepayment": 0.05, "next_state": "Current", "anomaly_score": 0.3, "exception_required": 0,
        "exception_type": "None", "top_driver_1": "days_past_due", "top_driver_2": "credit_score_ordinal",
        "top_driver_3": "interest_rate_imputed", "recommended_action": "Standard Portfolio Surveillance",
    }
    base.update(kw)
    return base


def _dec(item):
    return {k: (Decimal(str(v)) if isinstance(v, float) else v) for k, v in item.items()}


class _LoansTable:
    def __init__(self, pages):
        self._pages = [list(p) for p in pages]

    def scan(self, **kwargs):
        page = self._pages.pop(0)
        out = {"Items": [_dec(i) for i in page]}
        if self._pages:
            out["LastEvaluatedKey"] = {"loan_id": page[-1]["loan_id"]}
        return out

    def get_item(self, Key):
        for page in self._pages:
            for i in page:
                if i["loan_id"] == Key["loan_id"]:
                    return {"Item": _dec(i)}
        return {}


class _AuditTable:
    def __init__(self):
        self.items = []

    def put_item(self, Item):
        self.items.append(Item)


class _FakeDynamo:
    def __init__(self, loans_pages, audit):
        self.loans_pages, self.audit = loans_pages, audit

    def Table(self, name):
        return self.audit if name == cp.AUDIT_TABLE_NAME else _LoansTable(self.loans_pages)


class _FakeSSM:
    def __init__(self, values):
        self.values = values

    def get_parameters(self, Names, WithDecryption):
        return {"Parameters": [{"Name": n, "Value": self.values[n]} for n in Names if n in self.values]}


class _BedrockRefusing:
    def converse(self, **kw):
        raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "Your account is currently being verified."}}, "Converse")


class _BedrockAnswering:
    def converse(self, **kw):
        return {"output": {"message": {"content": [{"text": "Bedrock says: " + LONG_ANSWER}]}}}


class _LLMRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
        status, payload = self.server.responder(body)
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def llm_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _LLMRequestHandler)
    server.requests = []
    server.responder = lambda body: (200, {"choices": [{"message": {"content": LONG_ANSWER}}]})
    server.url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


@pytest.fixture
def env(monkeypatch, llm_server):
    """Fresh module state: 40 loans over two scan pages, Bedrock refusing, LLM configured."""
    page1 = [_loan(f"LN{i:04d}", 0.01 + i * 0.001) for i in range(20)]
    page2 = [_loan(f"LN{i:04d}", 0.01 + i * 0.001) for i in range(20, 40)]
    page2.append(_loan("LN9999", 0.41, current_status="30-59 DPD", exception_required=1, exception_type="Data Conflict"))
    audit = _AuditTable()

    monkeypatch.setattr(cp, "dynamodb", _FakeDynamo([page1, page2], audit))
    monkeypatch.setattr(cp, "bedrock", _BedrockRefusing())
    monkeypatch.setattr(cp, "ssm", _FakeSSM({
        "/loanlens/llm/api_key": "sk-test-123", "/loanlens/llm/base_url": llm_server.url, "/loanlens/llm/model": "test-model",
    }))
    monkeypatch.setattr(cp, "PROVIDERS", ["bedrock", "openai_compat"])
    monkeypatch.setattr(cp, "_llm_cache", {"at": 0.0, "cfg": None})
    monkeypatch.setattr(cp, "_bedrock_blocked_until", 0.0)
    return type("Env", (), {"audit": audit, "server": llm_server})


def _call(body):
    resp = cp.handler({"body": json.dumps(body)}, None)
    return resp["statusCode"], json.loads(resp["body"])


# -------------------------------------------------------------------- grounding


def test_portfolio_context_is_whole_portfolio_and_ranked():
    loans = [_loan("A", 0.05), _loan("B", 0.41), _loan("C", 0.22, exception_required=1, exception_type="Date Anomaly"),
             _loan("D", 0.02, credit_score_band=None)]
    ctx = cp.build_portfolio_context(loans, top_n=2)

    assert ctx["summary"]["total_loans"] == 4
    assert ctx["summary"]["high_risk_count"] == 2
    assert ctx["summary"]["exception_count"] == 1
    assert [l["loan_id"] for l in ctx["top_risk_loans"]] == ["B", "C"]
    assert ctx["exception_types"] == {"Date Anomaly": 1}
    assert "Unknown" in ctx["by_credit_band"]  # a missing band is grouped, not dropped


def test_question_about_highest_risk_sees_loan_on_second_scan_page(env, monkeypatch):
    """Regression: the model used to be fed an arbitrary 25-loan slice, so the highest-risk loan could be absent."""
    monkeypatch.setattr(cp, "PROVIDERS", [])  # template path
    status, out = _call({"mode": "portfolio_qa", "question": "Which loans are highest risk right now?"})
    assert status == 200
    first_loan_line = [l for l in out["output"].splitlines() if l.startswith("- ")][0]
    assert "LN9999" in first_loan_line and "41.0%" in first_loan_line


def test_llm_prompt_contains_portfolio_aggregates_not_a_slice(env):
    _call({"mode": "portfolio_qa", "question": "What credit bands are most vulnerable?"})
    prompt = env.server.requests[-1]["body"]["messages"][1]["content"]
    assert "computed over all 41 scored loans" in prompt
    assert "by_credit_band" in prompt and "LN9999" in prompt


# ------------------------------------------------------------- provider chain


def test_bedrock_answers_first_when_available(env, monkeypatch):
    monkeypatch.setattr(cp, "bedrock", _BedrockAnswering())
    status, out = _call({"mode": "portfolio_qa", "question": "summary"})
    assert out["provider"] == "bedrock" and out["fallback"] is False
    assert out["model_name"].startswith("bedrock/")
    assert env.server.requests == []  # the second provider was never called


def test_falls_through_to_openai_compatible_when_bedrock_refuses(env):
    status, out = _call({"mode": "portfolio_qa", "question": "summary"})
    assert out["provider"] == "openai_compat" and out["fallback"] is False
    assert out["model_name"].endswith("/test-model")
    assert "LN0000002" in out["output"]


def test_request_carries_key_model_and_a_non_urllib_user_agent(env):
    _call({"mode": "portfolio_qa", "question": "summary"})
    req = env.server.requests[-1]
    assert req["path"] == "/v1/chat/completions"
    assert req["headers"]["Authorization"] == "Bearer sk-test-123"
    assert req["body"]["model"] == "test-model"
    assert "urllib" not in req["headers"]["User-Agent"].lower()  # WAFs commonly block the default agent


def test_all_providers_failing_returns_a_labelled_template(env):
    env.server.responder = lambda body: (500, {"error": "boom"})
    status, out = _call({"mode": "portfolio_qa", "question": "Which loans are highest risk?"})
    assert out["fallback"] is True and out["provider"] == "template" and out["model_name"] == "template"
    assert "bedrock:" in out["fallback_reason"] and "openai_compat:" in out["fallback_reason"]
    assert "HTTP 500" in out["fallback_reason"]
    assert "LN9999" in out["output"]  # still a useful, grounded answer


def test_missing_api_key_is_reported_not_silently_swallowed(env, monkeypatch):
    monkeypatch.setattr(cp, "ssm", _FakeSSM({}))
    status, out = _call({"mode": "portfolio_qa", "question": "summary"})
    assert out["fallback"] is True
    assert "no LLM configured" in out["fallback_reason"] and "/loanlens/llm/api_key" in out["fallback_reason"]


def test_rate_limit_from_provider_falls_back(env):
    env.server.responder = lambda body: (429, {"error": {"message": "rate limit"}})
    status, out = _call({"mode": "portfolio_qa", "question": "summary"})
    assert out["fallback"] is True and "HTTP 429" in out["fallback_reason"]


def test_empty_model_response_is_treated_as_failure(env):
    env.server.responder = lambda body: (200, {"choices": [{"message": {"content": "ok"}}]})
    status, out = _call({"mode": "portfolio_qa", "question": "summary"})
    assert out["fallback"] is True and "too-short" in out["fallback_reason"]


def test_bedrock_is_skipped_after_an_access_refusal(env, monkeypatch):
    calls = []
    real = cp.bedrock
    monkeypatch.setattr(cp, "bedrock", type("B", (), {"converse": lambda self, **kw: (calls.append(1), real.converse(**kw))[1]})())
    _call({"mode": "portfolio_qa", "question": "summary"})
    _call({"mode": "portfolio_qa", "question": "summary"})
    assert len(calls) == 1  # the second request did not pay for a call known to fail


def test_disclaimer_is_always_appended(env):
    env.server.responder = lambda body: (200, {"choices": [{"message": {"content": "A perfectly reasonable answer that forgets the closing line."}}]})
    status, out = _call({"mode": "portfolio_qa", "question": "summary"})
    assert out["output"].rstrip().endswith("Recommendation — not a decision.*") or out["output"].rstrip().endswith("Recommendation — not a decision.")


def test_audit_log_records_provider_and_failures(env):
    _call({"mode": "portfolio_qa", "question": "summary"})
    item = env.audit.items[-1]
    assert item["provider"] == "openai_compat"
    assert any("bedrock" in e for e in item["provider_errors"])


# ------------------------------------------------------ deterministic answers


def test_template_exception_and_band_answers(env, monkeypatch):
    monkeypatch.setattr(cp, "PROVIDERS", [])
    _, exc = _call({"mode": "portfolio_qa", "question": "Summarize the exceptions flagged in this portfolio."})
    assert "Data Conflict (1)" in exc["output"] and "LN9999" in exc["output"]
    _, band = _call({"mode": "portfolio_qa", "question": "What credit bands are most vulnerable?"})
    assert "660-699" in band["output"] and "average 12-month default" in band["output"]


def test_template_on_an_empty_portfolio_says_so():
    ctx = cp.build_portfolio_context([])
    assert "No loans have been scored yet" in cp.template_portfolio_answer("anything", ctx)


def test_memo_template_and_404(env, monkeypatch):
    monkeypatch.setattr(cp, "PROVIDERS", [])
    status, out = _call({"mode": "memo", "loan_id": "LN9999"})
    assert status == 200 and "High Risk" in out["output"] and "Data Conflict" in out["output"]
    assert "days past due" in out["output"]  # driver names are translated for a reader
    assert _call({"mode": "memo", "loan_id": "NOPE"})[0] == 404


def test_stress_template_reports_deltas_against_baseline(env, monkeypatch):
    monkeypatch.setattr(cp, "PROVIDERS", [])
    scenario = {"rate_shock_bps": 150, "unemployment_delta_pct": 2.5, "mean_default_prob_pct": 8.86,
                "expected_loss_usd": 1_300_000, "car_impact_pct": 37.7, "var99_usd": 3_000_000,
                "baseline": {"mean_default_prob_pct": 4.0, "expected_loss_usd": 600_000}}
    status, out = _call({"mode": "stress_explain", "scenario_result": scenario})
    assert status == 200
    assert "+150 bps" in out["output"] and "+4.86 pp" in out["output"] and "+117%" in out["output"]


def test_stress_requires_a_scenario(env):
    assert _call({"mode": "stress_explain"})[0] == 400
    assert _call({"mode": "no_such_mode"})[0] == 400
