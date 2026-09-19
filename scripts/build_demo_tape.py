"""
Build the demo loan tape (data/sample/demo_loan_tape.csv).

A real monthly loan tape is an "as of" snapshot: every loan that is still
reporting in that month, with its history up to that month. This builds one
from the synthetic panel, so the demo portfolio has the mix a servicer would
actually see (mostly current, a tail of delinquent loans, a few defaults)
rather than a dump of every loan's final record, most of which are loans that
already paid off.

The pool is the 2020+ vintages: the held-out 2022+ cohort plus the 2020-2021
validation vintages. Those validation vintages informed probability
calibration, so this tape is for demonstration, not for evaluating the models.

    python scripts/build_demo_tape.py [--as-of 2022-12]

Requires data/raw/ (run `make generate` first).
"""

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "sample" / "demo_loan_tape.csv"

# Loans still on the books in the as-of month. Paid-off and prepaid loans have
# left the portfolio by then, exactly as on a real tape.
ON_BOOKS = ["Current", "30-59 DPD", "60-89 DPD", "90+ DPD", "Default"]


def build(as_of: str) -> pd.DataFrame:
    train = pd.read_csv(RAW / "loan_monthly_performance_train.csv")
    test = pd.read_csv(RAW / "loan_monthly_performance_test.csv")
    pool = pd.concat([train[train["origination_month"] >= "2020-01"], test], ignore_index=True)

    history = pool[pool["reporting_month"] <= as_of]
    latest = history.sort_values("reporting_month").groupby("loan_id").tail(1)
    on_books = latest[(latest["reporting_month"] == as_of) & latest["current_status"].isin(ON_BOOKS)]["loan_id"]

    tape = history[history["loan_id"].isin(on_books)]
    return tape.sort_values(["loan_id", "month_index"]).reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default="2022-12", help="reporting month of the snapshot (YYYY-MM)")
    args = parser.parse_args()

    tape = build(args.as_of)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tape.to_csv(OUT, index=False)

    latest = tape.sort_values("reporting_month").groupby("loan_id").tail(1)
    print(f"as-of {args.as_of}: {latest['loan_id'].nunique():,} loans, {len(tape):,} monthly records")
    print("status mix:", latest["current_status"].value_counts().to_dict())
    print(f"exposure: ${latest['current_balance'].sum() / 1e6:.1f}M")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
