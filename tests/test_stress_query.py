import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "stress_handler", Path(__file__).resolve().parents[1] / "backend" / "stress_query" / "handler.py"
)
stress = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stress)


def _query(rate, unemp):
    resp = stress.handler({"body": json.dumps({"rate_shock_bps": rate, "unemployment_delta_pct": unemp})}, None)
    assert resp["statusCode"] == 200
    return json.loads(resp["body"])


def test_unstressed_point_equals_the_baseline():
    out = _query(0, 0)
    for key, value in out["baseline"].items():
        assert out[key] == value


def test_baseline_is_the_same_for_every_scenario():
    assert _query(150, 2.5)["baseline"] == _query(-100, 0)["baseline"]


def test_adverse_scenario_costs_more_than_baseline():
    out = _query(150, 2.5)
    assert out["expected_loss_usd"] > out["baseline"]["expected_loss_usd"]
    assert out["mean_default_prob_pct"] > out["baseline"]["mean_default_prob_pct"]


def test_expected_loss_rises_monotonically_with_unemployment():
    losses = [_query(0, u)["expected_loss_usd"] for u in (0, 1, 2, 4, 8)]
    assert losses == sorted(losses)


def test_interpolates_between_grid_points():
    lo, hi, mid = _query(0, 1.0), _query(0, 1.5), _query(0, 1.25)
    assert lo["expected_loss_usd"] < mid["expected_loss_usd"] < hi["expected_loss_usd"]


def test_out_of_range_inputs_are_clamped_not_extrapolated():
    assert _query(9999, 99)["expected_loss_usd"] == _query(300, 8)["expected_loss_usd"]
