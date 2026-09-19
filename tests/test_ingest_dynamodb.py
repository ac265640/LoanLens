"""
Regression tests for the ingest Lambda's DynamoDB write path.

boto3's DynamoDB layer refuses Python floats (it needs Decimal) and cannot
represent NaN/Infinity. Scored rows contain both — probabilities are floats,
and a missing credit score band is NaN — so writing them unconverted crashes
the Lambda. These tests run boto3's own TypeSerializer, the exact code path
that raised in production, so the failure is reproducible without AWS.
"""

import os
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from boto3.dynamodb.types import TypeSerializer

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import handler  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEMO_TAPE = ROOT / "data" / "sample" / "demo_loan_tape.csv"
serializer = TypeSerializer()


def test_control_raw_python_float_is_rejected_by_boto3():
    with pytest.raises(TypeError, match="Float types are not supported"):
        serializer.serialize({"prob": 0.1234})


def test_float_becomes_rounded_decimal():
    v = handler._to_dynamo_value(0.123456)
    assert v == Decimal("0.1235")
    assert isinstance(v, Decimal)


def test_numpy_scalars_are_converted():
    assert isinstance(handler._to_dynamo_value(np.float64(0.5)), Decimal)
    assert handler._to_dynamo_value(np.int64(7)) == 7
    assert type(handler._to_dynamo_value(np.int64(7))) is int
    assert handler._to_dynamo_value(np.bool_(True)) is True


@pytest.mark.parametrize("bad", [float("nan"), np.float64("nan"), float("inf"), float("-inf")])
def test_nan_and_infinity_become_null(bad):
    assert handler._to_dynamo_value(bad) is None


def test_strings_and_none_pass_through():
    assert handler._to_dynamo_value("620-659") == "620-659"
    assert handler._to_dynamo_value(None) is None


def test_item_with_missing_credit_band_serializes():
    row = {
        "loan_id": np.str_("LN0000001"),
        "credit_score_band": float("nan"),  # pandas holds a missing string as NaN
        "prob_next_12m_default": np.float64(0.0412),
        "exception_required": np.int64(0),
        "days_past_due": np.int64(0),
    }
    item = handler._to_dynamo_item(row, run_id="raw_test", scored_at="2026-01-01T00:00:00+00:00")
    serializer.serialize(item)  # must not raise
    assert item["credit_score_band"] is None
    assert item["run_id"] == "raw_test"


@pytest.mark.skipif(not DEMO_TAPE.exists(), reason="demo tape not present")
def test_every_item_from_the_real_demo_tape_serializes():
    scored = handler.score_loan_tape(pd.read_csv(DEMO_TAPE))
    assert len(scored) > 0

    for row in scored.to_dict(orient="records"):
        item = handler._to_dynamo_item(row, run_id="raw_demo", scored_at="2026-01-01T00:00:00+00:00")
        serializer.serialize(item)  # raises TypeError on any float / NaN left behind
