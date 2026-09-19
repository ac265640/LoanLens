"""Portfolio read API: the summary must describe the whole portfolio no matter
which filter the dashboard applies, and reads must not stop at one scan page."""

import importlib.util
import json
import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

# Two Lambdas are both named handler.py, so load this one under its own name.
_spec = importlib.util.spec_from_file_location(
    "portfolio_api_handler", Path(__file__).resolve().parents[1] / "backend" / "portfolio_api" / "handler.py"
)
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)


def _loan(loan_id, p_default, exception=0, balance=100000):
    return {
        "loan_id": loan_id,
        "prob_next_12m_default": Decimal(str(p_default)),
        "exception_required": exception,
        "current_balance": Decimal(balance),
        "current_status": "Current",
    }


class _PagedTable:
    def __init__(self, pages):
        self._pages = list(pages)

    def scan(self, **kwargs):
        page = self._pages.pop(0)
        result = {"Items": page}
        if self._pages:
            result["LastEvaluatedKey"] = {"loan_id": page[-1]["loan_id"]}
        return result


class _FakeDynamo:
    def __init__(self, table):
        self._table = table

    def Table(self, _name):
        return self._table


PORTFOLIO = [
    [_loan("A", 0.41), _loan("B", 0.05, exception=1)],
    [_loan("C", 0.22), _loan("D", 0.02)],  # second scan page
]


def _list(monkeypatch, params):
    monkeypatch.setattr(api, "dynamodb", _FakeDynamo(_PagedTable([list(p) for p in PORTFOLIO])))
    resp = api.list_loans(params)
    assert resp["statusCode"] == 200
    return json.loads(resp["body"])


def test_reads_every_scan_page(monkeypatch):
    body = _list(monkeypatch, {})
    assert body["summary"]["total_loans"] == 4
    assert {l["loan_id"] for l in body["loans"]} == {"A", "B", "C", "D"}


def test_summary_ignores_the_filter(monkeypatch):
    unfiltered = _list(monkeypatch, {})["summary"]
    filtered = _list(monkeypatch, {"min_default_prob": "0.20"})
    assert [l["loan_id"] for l in filtered["loans"]] == ["A", "C"]  # table is narrowed...
    assert filtered["summary"] == unfiltered  # ...KPIs are not
    assert unfiltered["high_risk_count"] == 2
    assert unfiltered["exception_count"] == 1


def test_exceptions_filter_and_ordering(monkeypatch):
    body = _list(monkeypatch, {"exceptions_only": "true"})
    assert [l["loan_id"] for l in body["loans"]] == ["B"]
    assert [l["loan_id"] for l in _list(monkeypatch, {})["loans"]] == ["A", "C", "B", "D"]  # by risk, descending


def test_counts_serialize_as_integers(monkeypatch):
    body = _list(monkeypatch, {})
    assert body["summary"]["total_loans"] == 4 and isinstance(body["summary"]["total_loans"], int)
    assert isinstance(body["loans"][0]["current_balance"], int)
