"""Fit outlook LR coefficients on user-supplied tabular data.

The TrialBench approval-outcome slice is gated (HuggingFace access
approval + unknown byte size), so this script takes a CSV the operator
already obtained and fits a stdlib logistic regression. Output lands in
data/fitted/outlook_lr.json (git-ignored, local-only); the app prefers it
over bootloader priors when present, with the source + test AUC reported
in the drivers list.

Expected columns: fragility (0-100), burden (raw total score),
n_safety (organ-safety exclusion count), approved (0/1).

Usage:
    python scripts/fit_outlook.py path/to/slice.csv [--l2 0.1]

Map TrialBench columns to these four before running; drop molecule and
disease-embedding columns (not usable stdlib-only).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.agents.logreg import auc_score, fit_logreg  # noqa: E402
from backend.config import FITTED_OUTLOOK  # noqa: E402


def load_rows(path: Path) -> tuple[list[list[float]], list[int]]:
    X, y = [], []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            try:
                X.append(
                    [
                        min(float(row["fragility"]), 100.0) / 100.0,
                        min(float(row["burden"]), 60.0) / 60.0,
                        float(row["n_safety"]),
                    ]
                )
                y.append(int(row["approved"]))
            except (KeyError, ValueError, TypeError):
                continue
    if len(X) < 10:
        raise ValueError(f"need >=10 usable rows, got {len(X)} in {path}")
    if len(set(y)) < 2:
        raise ValueError("need both classes (approved 0 and 1) in the slice")
    return X, y


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", type=Path, help="tabular slice with approved labels")
    ap.add_argument("--l2", type=float, default=0.1)
    args = ap.parse_args()
    X, y = load_rows(args.csv)
    train_idx = [i for i in range(len(X)) if i % 5 != 4]
    test_idx = [i for i in range(len(X)) if i % 5 == 4]
    w, b = fit_logreg([X[i] for i in train_idx], [y[i] for i in train_idx], l2=args.l2)
    from backend.agents.logreg import predict_proba  # noqa: E402

    test_auc = auc_score(
        predict_proba([X[i] for i in test_idx], w, b),
        [y[i] for i in test_idx],
    )
    doc = {
        "weights": {
            "fragility": w[0],
            "burden": w[1],
            "safety_excl": w[2],
            "bias": b,
        },
        "trained_on": f"{args.csv.name} (n={len(X)}, test n={len(test_idx)})",
        "test_auc": round(test_auc, 3),
        "l2": args.l2,
    }
    FITTED_OUTLOOK.parent.mkdir(parents=True, exist_ok=True)
    FITTED_OUTLOOK.write_text(json.dumps(doc, indent=1))
    print(f"wrote {FITTED_OUTLOOK} test_auc={doc['test_auc']}")


if __name__ == "__main__":
    main()
