"""n2c2-2018-style benchmark harness. Deterministic, stdlib only.

Scores criterion-level eligibility on n2c2-formatted data (notes + labels).
Real n2c2 data is DUA-gated (request from the n2c2/Harvard DBMI portal) and
goes under data/n2c2/ as {id}.txt notes + labels.csv with one column per
criterion below. Ships with a tiny synthetic fixture proving the harness
end to end. Numeric/temporal criteria are pragmatic approximations —
verify against the annotation guidelines when ingesting real data.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    from backend.agents.cohort_matcher import _affirmed as affirmed
except ImportError:  # fallback: run with backend/ as cwd
    from agents.cohort_matcher import _affirmed as affirmed  # type: ignore[no-redef]

CRITERIA = ("ABDOMINAL", "ADVANCED-CAD", "ALCOHOL-ABUSE", "ASP-FOR-MI",
            "CREATININE", "DIETSUPP-2MOS", "DRUG-ABUSE", "ENGLISH", "HBA1C",
            "KETO-1YR", "MAJOR-DIABETES", "MAKES-DECISIONS", "MI-6MOS")

_TERM_RULES = {
    "ABDOMINAL": ("abdominal surgery", "laparotomy", "colectomy", "bowel resection",
                  "appendectomy", "cholecystectomy", "hysterectomy"),
    "ADVANCED-CAD": ("cabg", "triple vessel", "multi-vessel", "multivessel",
                     "severe cad", "three-vessel"),
    "ALCOHOL-ABUSE": ("alcohol abuse", "alcoholic", "etoh abuse", "drinks daily",
                      "heavy drinking"),
    "DIETSUPP-2MOS": ("multivitamin", "fish oil", "vitamin d", "supplement",
                      "calcium", "probiotic"),
    "DRUG-ABUSE": ("cocaine", "heroin", "marijuana", "ivdu", "illicit",
                   "substance abuse"),
    "KETO-1YR": ("dka", "ketoacidosis", "ketosis"),
    "MAJOR-DIABETES": ("nephropathy", "retinopathy", "neuropathy", "amputation",
                       "diabetic foot", "chronic kidney"),
}


def _num_after(pattern: str, text: str) -> List[float]:
    return [float(v) for v in re.findall(pattern, text)]


def predict(note_text: str) -> Dict[str, int]:
    """Predict 13 binary labels for one clinical note."""
    low = note_text.lower()
    out: Dict[str, int] = {}
    for crit, terms in _TERM_RULES.items():
        out[crit] = 1 if affirmed(low, *terms) else 0
    out["ASP-FOR-MI"] = 1 if (affirmed(low, "aspirin") and affirmed(
        low, "mi", "myocardial", "cardiac", "cad", "stent")) else 0
    creat = _num_after(r"creatinine\s*(\d+\.?\d*)", low)
    out["CREATININE"] = 1 if any(v > 1.5 for v in creat) else 0
    out["ENGLISH"] = 1 if affirmed(low, "english") else 0
    a1c = _num_after(r"(?:hgba1c|hba1c|a1c)\s*(\d+\.?\d*)", low)
    out["HBA1C"] = 1 if any(6.5 <= v <= 9.5 for v in a1c) else 0
    makes = (re.search(r"makes (own |their |his |her )?(\w+ ){0,3}decisions?", low)
             is not None
             or affirmed(low, "decisional capacity", "decisions independently"))
    represented = re.search(
        r"(dementia|guardian|surrogate|daughter|son|wife|husband).{0,25}decision", low)
    out["MAKES-DECISIONS"] = 1 if (makes and not represented) else 0
    mi = affirmed(low, "mi", "myocardial infarction", "stemi", "nstemi")
    old = re.search(r"(remote|years ago|> ?1 year|history of mi in 20\d\d)", low)
    out["MI-6MOS"] = 1 if (mi and not old) else 0
    return out


def micro_f1(patients: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Micro-averaged P/R/F1 over all patient x criterion labels."""
    tp = fp = fn = 0
    for p in patients:
        pred = predict(p["note"])
        for c in CRITERIA:
            gold = int(p["labels"].get(c, 0))
            got = pred[c]
            tp += gold and got
            fp += (not gold) and got
            fn += gold and (not got)
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, tp + fn)
    f1 = 2 * prec * rec / max(1e-9, prec + rec)
    return {"micro_p": round(prec, 4), "micro_r": round(rec, 4),
            "micro_f1": round(f1, 4), "n_patients": len(patients),
            "n_labels": len(patients) * len(CRITERIA)}


def load_fixture() -> List[Dict[str, Any]]:
    path = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "n2c2_mini.json"
    return json.loads(path.read_text())["patients"]


def load_n2c2_dir(data_dir: str) -> List[Dict[str, Any]]:
    """Load real n2c2-formatted data: {id}.txt notes + labels.csv."""
    root = Path(data_dir)
    labels = {}
    with open(root / "labels.csv", newline="") as f:
        for row in csv.DictReader(f):
            labels[row["id"]] = {c: int(row.get(c, 0) or 0) for c in CRITERIA}
    patients = []
    for pid, labs in sorted(labels.items()):
        note = (root / f"{pid}.txt").read_text(errors="ignore")
        patients.append({"id": pid, "note": note, "labels": labs})
    return patients


def main(argv: List[str]) -> int:
    if len(argv) > 1:
        patients = load_n2c2_dir(argv[1])
        print(f"scored {len(patients)} real n2c2 patients from {argv[1]}")
    else:
        patients = load_fixture()
        print(f"scored {len(patients)} fixture patients (real data: put notes + labels.csv under data/n2c2/)")
    print(json.dumps(micro_f1(patients), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
