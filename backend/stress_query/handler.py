"""
Stress Query Lambda
====================
Serves the interactive "Shockwave" sliders. Looks up the precomputed grid
(scripts/precompute_stress_grid.py) and bilinearly interpolates between the
4 nearest grid points so arbitrary slider positions feel continuous, without
running the models live on every drag event.
"""

import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data" / "stress_grid.json"
_GRID = None


def _load_grid():
    global _GRID
    if _GRID is None:
        with open(DATA_PATH) as f:
            _GRID = json.load(f)
    return _GRID


def _nearest_axis_pair(value, axis):
    lo = max((a for a in axis if a <= value), default=axis[0])
    hi = min((a for a in axis if a >= value), default=axis[-1])
    return lo, hi


def _point_at(grid_data, r, u):
    for p in grid_data["grid"]:
        if p["rate_shock_bps"] == r and p["unemployment_delta_pct"] == u:
            return p
    return None


NUMERIC_FIELDS = [
    "mean_default_prob_pct", "mean_prepay_mult", "mean_delinq_mult",
    "expected_loss_usd", "expected_loss_pct_of_portfolio", "car_impact_pct", "var99_usd",
]


def _bilinear_interpolate(grid_data, rate_bps, unemp_pct):
    rate_axis = grid_data["rate_grid_bps"]
    unemp_axis = grid_data["unemployment_grid_pct"]

    rate_bps = max(min(rate_bps, max(rate_axis)), min(rate_axis))
    unemp_pct = max(min(unemp_pct, max(unemp_axis)), min(unemp_axis))

    r0, r1 = _nearest_axis_pair(rate_bps, rate_axis)
    u0, u1 = _nearest_axis_pair(unemp_pct, unemp_axis)

    p00 = _point_at(grid_data, r0, u0)
    p01 = _point_at(grid_data, r0, u1)
    p10 = _point_at(grid_data, r1, u0)
    p11 = _point_at(grid_data, r1, u1)

    tr = (rate_bps - r0) / (r1 - r0) if r1 != r0 else 0.0
    tu = (unemp_pct - u0) / (u1 - u0) if u1 != u0 else 0.0

    out = {"rate_shock_bps": rate_bps, "unemployment_delta_pct": unemp_pct}
    for field in NUMERIC_FIELDS:
        v00, v01, v10, v11 = p00[field], p01[field], p10[field], p11[field]
        top = v00 * (1 - tu) + v01 * tu
        bot = v10 * (1 - tu) + v11 * tu
        out[field] = round(top * (1 - tr) + bot * tr, 3)

    return out


def handler(event, context):
    body = json.loads(event["body"]) if isinstance(event.get("body"), str) else (event.get("body") or event)
    rate_bps = float(body.get("rate_shock_bps", 0))
    unemp_pct = float(body.get("unemployment_delta_pct", 0))

    grid_data = _load_grid()
    result = _bilinear_interpolate(grid_data, rate_bps, unemp_pct)
    # The unstressed point, so a caller can say how far a scenario moved from today.
    baseline = _bilinear_interpolate(grid_data, 0, 0)
    result["baseline"] = {k: baseline[k] for k in NUMERIC_FIELDS}
    result["portfolio_total_exposure_usd"] = grid_data["portfolio_total_exposure_usd"]
    result["loan_count"] = grid_data["loan_count"]
    result["assumptions"] = grid_data["assumptions"]

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(result),
    }
