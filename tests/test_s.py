"""S-track regression: sweep, forensics, retention, enrichment, priors,
outcomes shape, provenance."""

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

from agents.cohort_matcher import evaluate_patient as evaluate  # noqa: E402
from agents.enrollment_forecast import (  # noqa: E402
    backtest_accrual,
    site_priors_from_metrics,
)
from agents.failure_forensics import forensic_report  # noqa: E402
from agents.protocol_auditor import parse_protocol  # noqa: E402
from agents.relaxation_sweep import ladder_for, sweep  # noqa: E402
from agents.retention import retention_risk  # noqa: E402
from agents.safety_triage import triage_one  # noqa: E402

FHIR = ROOT / "data" / "fhir" / "synthea"
PROTO = ROOT / "data" / "raw" / "protocols" / "protocol_oncology_phase3.txt"


def load_bundle(pid):
    return json.loads((FHIR / f"{pid}.json").read_text())


def set_anc(bundle, value, new_id="near-001"):
    b = copy.deepcopy(bundle)
    b["id"] = new_id
    for e in b["entry"]:
        r = e["resource"]
        if r.get("resourceType") == "Patient":
            r["id"] = new_id
        if r.get("resourceType") == "Observation" and "Neutrophil" in str(
            (r.get("code", {}) or {}).get("text", "")
        ):
            r["valueQuantity"]["value"] = value
    return b


def eval_row(pid, inc, exc):
    return {
        "patient_id": pid,
        "inclusion_evaluations": [
            {"criterion_id": c, "passed": p, "missing_data": m} for c, p, m in inc
        ],
        "exclusion_evaluations": [
            {"criterion_id": c, "triggered": t, "missing_data": m} for c, t, m in exc
        ],
    }


class STrackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        audit = parse_protocol(PROTO.read_text())
        cls.crit = {
            "inclusion_criteria": audit["inclusion_criteria"],
            "exclusion_criteria": audit["exclusion_criteria"],
        }

    def test_ladder_shapes(self):
        self.assertEqual(ladder_for(">=", 1.5), [1.35, 1.125, 0.9])
        self.assertEqual(ladder_for("<=", 100), [115.0, 135.0, 160.0])
        self.assertEqual(ladder_for("IN", [0, 1]), [2, 3])
        self.assertEqual(ladder_for("==", "present"), [])

    def test_sweep_marginal_and_ladder(self):
        near = set_anc(load_bundle("patient_001_breast_cancer"), 1400)
        out = sweep(
            self.crit,
            [
                load_bundle("patient_001_breast_cancer"),
                near,
                load_bundle("patient_002_control"),
            ],
        )
        inc04 = [c for c in out["criteria"] if c["id"] == "INC-04"][0]
        self.assertEqual(inc04["marginal_n"], 1)
        anc = [s for s in inc04["sub_sweeps"] if "ANC" in str(s["variable"])][0]
        self.assertEqual(anc["base"], 1.5)
        self.assertEqual(anc["ladder"][0]["threshold"], 1.35)
        self.assertEqual(anc["ladder"][0]["newly_n"], 1)
        self.assertEqual(out["baseline_eligible_n"], 1)

    def test_sweep_twins_mode(self):
        out = sweep(
            self.crit, [load_bundle("patient_001_breast_cancer")], twins_n=20, seed=7
        )
        self.assertEqual(out["n_patients"], 20)
        self.assertIn("twins", out["source"])
        self.assertTrue(out["criteria"])

    def test_forensics_rates(self):
        rep = forensic_report(
            [
                eval_row("a", [("INC-01", True, False)], [("EXC-01", False, False)]),
                eval_row("b", [("INC-01", False, False)], [("EXC-01", True, False)]),
            ]
        )
        self.assertEqual(rep["n_evaluations"], 2)
        inc = rep["inclusions"][0]
        self.assertEqual((inc["fail_rate"], inc["missing_rate"]), (50.0, 0.0))
        self.assertEqual(rep["exclusions"][0]["trigger_rate"], 50.0)
        self.assertEqual(len(rep["top_drivers"]), 2)

    def test_retention_monotone_and_whatif(self):
        burden = {
            "total_score": 20,
            "visits": [
                {"score": 10, "convertible": True},
                {"score": 10, "convertible": False},
            ],
        }
        fit = retention_risk(burden, load_bundle("patient_001_breast_cancer"))
        frail_bundle = load_bundle("patient_002_control")
        frail = retention_risk(
            {"total_score": 40, "visits": [{"score": 20, "convertible": False}] * 4},
            frail_bundle,
        )
        self.assertLess(fit["score"], frail["score"])
        self.assertLessEqual(fit["what_if_remote"]["delta"], 0)
        self.assertEqual(fit["what_if_remote"]["convertible_visits"], 1)
        self.assertIn(fit["band"], ("low", "moderate", "high"))

    def test_enrichment_cues(self):
        acute = triage_one(
            {"reported_term": "ALT increased post-dose", "severity": "MODERATE"}
        )["enrichment"]
        self.assertEqual(acute["temporality"]["onset"], "acute")
        alt = triage_one(
            {"reported_term": "Dyspnea with disease progression", "severity": "MILD"}
        )["enrichment"]
        self.assertEqual(alt["attribution"]["relatedness"], "unlikely")
        stated = triage_one(
            {"reported_term": "Rash", "severity": "MILD", "relatedness": "related"}
        )["enrichment"]
        self.assertEqual(stated["certainty"]["level"], "high")
        plain = triage_one({"reported_term": "Headache", "severity": "MILD"})[
            "enrichment"
        ]
        self.assertEqual(plain["temporality"]["onset"], "unknown")

    def test_priors_from_metrics(self):
        priors = site_priors_from_metrics(
            [
                {"site_id": "SX", "month": "2025-01", "enrolled": 2},
                {"site_id": "SX", "month": "2025-02", "enrolled": 4},
                {"site_id": "SX", "month": "2025-03", "enrolled": 6},
                {"site_id": "BAD", "month": "2025-01"},
            ]
        )
        self.assertEqual(priors["SX"], {"accrual": 4.0, "months_observed": 3.0})
        self.assertNotIn("BAD", priors)

    def test_backtest_constant_site(self):
        rows = [
            {"site_id": "SX", "month": f"2025-0{m}", "enrolled": 3} for m in range(1, 7)
        ]
        b = backtest_accrual(rows)
        self.assertEqual(b["n_sites"], 1)
        self.assertEqual(b["n_predictions"], 5)
        self.assertLess(b["mae"], 1.0)
        self.assertEqual(b["sites"][0]["site_id"], "SX")

    def test_backtest_needs_history(self):
        b = backtest_accrual([{"site_id": "SX", "month": "2025-01", "enrolled": 3}])
        self.assertEqual(b["n_predictions"], 0)
        self.assertEqual(b["mae"], 0.0)

    def test_outcomes_shape_never_crashes(self):
        import tempfile

        from backend.agents import site_scout

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(site_scout, "CACHE", Path(tmp) / "c.json"):
                r = site_scout.fetch_ctgov_outcomes(
                    "xyz-no-such-condition-123", "PHASE9", timeout=6.0
                )
        self.assertIn(r["source"], ("live", "cache", "offline-fallback"))
        for k in (
            "n_completed",
            "with_results_pct",
            "median_enrollment",
            "top_outcomes",
        ):
            self.assertIn(k, r)

    def test_provenance_structured(self):
        ev = evaluate(
            {
                "inclusion_criteria": self.crit["inclusion_criteria"][:4],
                "exclusion_criteria": [],
            },
            load_bundle("patient_001_breast_cancer"),
        )["inclusion_evaluations"][3]
        self.assertEqual(
            ev["provenance"], {"match_type": "exact", "confidence": "high"}
        )

    def test_provenance_synonym_and_note(self):
        crit_mi = {
            "id": "INC-99",
            "category": "Other",
            "raw_text": "myocardial infarction documented",
            "variable": "history",
            "operator": "==",
            "value": "present",
        }
        b = load_bundle("patient_002_control")
        b["entry"].append(
            {
                "resource": {
                    "resourceType": "Condition",
                    "code": {"text": "History of MI"},
                }
            }
        )
        ev = evaluate({"inclusion_criteria": [crit_mi], "exclusion_criteria": []}, b)[
            "inclusion_evaluations"
        ][0]
        self.assertTrue(ev["passed"])
        self.assertEqual(
            ev["provenance"], {"match_type": "synonym", "confidence": "medium"}
        )
        crit_note = dict(crit_mi, raw_text="EGFR Exon 19 deletion documented")
        note_only = {
            "id": "note-only",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "note-only",
                        "birthDate": "1980-01-01",
                    }
                },
                {
                    "resource": {
                        "resourceType": "DocumentReference",
                        "status": "current",
                        "type": {"text": "Assessment"},
                        "content": [{"text": "EGFR Exon 19 deletion confirmed."}],
                    }
                },
            ],
        }
        ev2 = evaluate(
            {"inclusion_criteria": [crit_note], "exclusion_criteria": []}, note_only
        )["inclusion_evaluations"][0]
        self.assertTrue(ev2["passed"])
        self.assertIn("note (Assessment)", ev2["clinical_evidence_found"])
        self.assertEqual(
            ev2["provenance"], {"match_type": "note", "confidence": "medium"}
        )

    def test_provenance_missing_and_absent(self):
        crit = {
            "id": "INC-99",
            "category": "Renal",
            "raw_text": "No such lab <= 1",
            "variable": "No such lab",
            "operator": "<=",
            "value": 1,
            "unit": "mg/dL",
        }
        crit_lab = {
            "id": "INC-98",
            "category": "Renal",
            "raw_text": "Creatinine <= 1.5 mg/dL",
            "variable": "Creatinine",
            "operator": "<=",
            "value": 1.5,
            "unit": "mg/dL",
        }
        no_obs = {
            "id": "no-obs",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "no-obs",
                        "birthDate": "1980-01-01",
                    }
                }
            ],
        }
        ev = evaluate(
            {"inclusion_criteria": [crit_lab], "exclusion_criteria": []}, no_obs
        )["inclusion_evaluations"][0]
        self.assertTrue(ev["missing_data"])
        self.assertEqual(
            ev["provenance"], {"match_type": "missing", "confidence": "low"}
        )
        ev_absent = evaluate(
            {"inclusion_criteria": [crit], "exclusion_criteria": []},
            load_bundle("patient_001_breast_cancer"),
        )["inclusion_evaluations"][0]
        self.assertEqual(
            ev_absent["provenance"], {"match_type": "absent", "confidence": "medium"}
        )
        exc = evaluate(
            {
                "inclusion_criteria": [],
                "exclusion_criteria": [self.crit["exclusion_criteria"][0]],
            },
            load_bundle("patient_001_breast_cancer"),
        )["exclusion_evaluations"][0]
        self.assertFalse(exc["triggered"])
        self.assertEqual(
            exc["provenance"], {"match_type": "absent", "confidence": "medium"}
        )


if __name__ == "__main__":
    unittest.main()
