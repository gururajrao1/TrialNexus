"""Tier 1+2 regression: synonyms, notes, forecast, outlook, twins, mCODE, n2c2."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

from agents.cohort_matcher import clinical_notes  # noqa: E402
from agents.cohort_matcher import evaluate_patient as evaluate  # noqa: E402
from agents.enrollment_forecast import forecast  # noqa: E402
from agents.mcode import mcode_profile  # noqa: E402
from agents.n2c2_harness import load_fixture, micro_f1  # noqa: E402
from agents.protocol_auditor import parse_protocol  # noqa: E402
from agents.risk_models import outlook  # noqa: E402
from agents.synonyms import normalize  # noqa: E402
from agents.twin_generator import (  # noqa: E402
    make_twins,
    prespec_block,
    twin_distribution,
)

FHIR = ROOT / "data" / "fhir" / "synthea"
PROTO = ROOT / "data" / "raw" / "protocols" / "protocol_oncology_phase3.txt"


def load_bundle(pid):
    return json.loads((FHIR / f"{pid}.json").read_text())


def note_only_bundle():
    return {
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
                    "content": [{"text": "EGFR Exon 19 deletion confirmed on NGS."}],
                }
            },
        ],
    }


class Tier12Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = parse_protocol(PROTO.read_text())
        cls.crit = {
            "inclusion_criteria": cls.audit["inclusion_criteria"],
            "exclusion_criteria": cls.audit["exclusion_criteria"],
        }

    def test_synonym_paraphrase(self):
        self.assertIn("myocardial infarction", normalize("history of MI"))
        self.assertEqual(normalize("NSCLC"), "non-small cell lung cancer")

    def test_notes_present(self):
        notes = clinical_notes(load_bundle("patient_003_review"))
        self.assertTrue(any("EGFR" in n["text"] for n in notes))

    def test_inclusion_note_evidence(self):
        crit = {
            "inclusion_criteria": [
                {
                    "id": "INC-99",
                    "category": "Biomarker",
                    "raw_text": "EGFR Exon 19 deletion documented",
                    "variable": "egfr",
                    "operator": "==",
                    "value": "positive",
                }
            ],
            "exclusion_criteria": [],
        }
        ev = evaluate(crit, note_only_bundle())["inclusion_evaluations"][0]
        self.assertTrue(ev["passed"])
        self.assertFalse(ev["missing_data"])
        self.assertIn("note (Assessment)", ev["clinical_evidence_found"])

    def test_exclusion_note_evidence(self):
        b = load_bundle("patient_002_control")
        b["entry"].append(
            {
                "resource": {
                    "resourceType": "DocumentReference",
                    "status": "current",
                    "type": {"text": "H&P"},
                    "content": [{"text": "Known brain metastases, untreated."}],
                }
            }
        )
        res = evaluate(self.crit, b)
        exc = [
            e for e in res["exclusion_evaluations"] if e["criterion_id"] == "EXC-02"
        ][0]
        self.assertTrue(exc["triggered"])
        self.assertIn("note", exc["clinical_evidence_found"])

    def test_forecast_contract(self):
        f = forecast(
            [
                {"accrual": 2.0, "months_observed": 6},
                {"accrual": 1.0, "months_observed": 6},
            ],
            450,
            0,
            24.0,
        )
        self.assertLessEqual(f["p10"], f["p50"])
        self.assertLessEqual(f["p50"], f["p90"])
        self.assertGreater(f["p10"], 0)
        self.assertGreaterEqual(f["prob_by_deadline"], 0)
        self.assertLessEqual(f["prob_by_deadline"], 1)
        self.assertEqual(f["simulations"], 20000)

    def test_forecast_deterministic(self):
        sites = [{"accrual": 2.0, "months_observed": 6}]
        self.assertEqual(
            forecast(sites, 100, 10, 12.0, seed=9),
            forecast(sites, 100, 10, 12.0, seed=9),
        )

    def test_forecast_monotone(self):
        fast = forecast([{"accrual": 5.0, "months_observed": 12}], 100, seed=5)
        slow = forecast([{"accrual": 0.2, "months_observed": 12}], 100, seed=5)
        self.assertLess(fast["p50"], slow["p50"])

    def test_outlook_contract(self):
        o = outlook(self.audit, {"total_score": 20.0})
        self.assertGreaterEqual(o["success_probability"], 0.01)
        self.assertLessEqual(o["success_probability"], 0.95)
        self.assertAlmostEqual(sum(o["failure_breakdown"].values()), 1.0, places=2)
        # 5 drivers: the 5th labels fitted-vs-bootloader coefficient source.
        self.assertEqual(len(o["drivers"]), 5)

    def test_twins_contract(self):
        t = twin_distribution(
            self.crit, load_bundle("patient_001_breast_cancer"), n=100, seed=7
        )
        self.assertEqual(t["n"], 100)
        self.assertEqual(sum(t["counts"].values()), 100)
        self.assertGreaterEqual(t["eligible_pct"], 0)
        self.assertLessEqual(t["eligible_pct"], 100)

    def test_twins_cap_2000(self):
        self.assertEqual(
            len(make_twins(load_bundle("patient_001_breast_cancer"), 5000)),
            2000,
        )

    def test_twins_wilson_ci(self):
        t = twin_distribution(
            self.crit, load_bundle("patient_001_breast_cancer"), n=100, seed=7
        )
        lo, hi = t["eligible_ci95"]
        self.assertLessEqual(lo, t["eligible_pct"])
        self.assertLessEqual(t["eligible_pct"], hi)
        self.assertGreaterEqual(lo, 0)
        self.assertLessEqual(hi, 100)

    def test_twins_flip_drivers(self):
        t = twin_distribution(
            self.crit, load_bundle("patient_001_breast_cancer"), n=100, seed=7
        )
        self.assertIsInstance(t["flips"], list)
        self.assertTrue(t["flips"])
        for f in t["flips"]:
            for k in ("criterion_id", "kind", "flips", "flip_rate"):
                self.assertIn(k, f)
            self.assertLessEqual(f["flips"], t["n"])
            self.assertGreaterEqual(f["flip_rate"], 0)
            self.assertLessEqual(f["flip_rate"], 1)

    def test_twins_jitter_zero_matches_base(self):
        b = load_bundle("patient_001_breast_cancer")
        base = evaluate(self.crit, b)["overall_status"]
        t = twin_distribution(self.crit, b, n=50, seed=7, jitter=0.0)
        self.assertEqual(t["counts"].get(base), 50)
        self.assertTrue(all(f["flips"] == 0 for f in t["flips"]))

    def test_twins_prespec(self):
        p = prespec_block(5000, 7, 0.9)
        self.assertEqual(p["n"], 2000)
        self.assertEqual(p["jitter"], 0.5)
        self.assertEqual(p["not_for"], "efficacy or safety")
        t = twin_distribution(
            self.crit, load_bundle("patient_001_breast_cancer"), n=50, seed=7
        )
        self.assertEqual(t["prespec"]["seed"], 7)
        self.assertEqual(t["prespec"]["n"], 50)

    def test_twins_deterministic(self):
        kw = {
            "criteria": self.crit,
            "bundle": load_bundle("patient_001_breast_cancer"),
            "n": 100,
            "seed": 7,
        }
        t1 = twin_distribution(**kw)
        t2 = twin_distribution(**kw)
        self.assertEqual(t1["counts"], t2["counts"])
        self.assertEqual(t1["flips"], t2["flips"])

    def test_mcode_histology_non_small_cell(self):
        p = mcode_profile(load_bundle("patient_001_breast_cancer"))["profile"]
        self.assertEqual(p["histology"], "non-small cell")

    def test_mcode_egfr_lab_not_biomarker(self):
        p = mcode_profile(load_bundle("patient_005_diabetes"))["profile"]
        self.assertNotIn("EGFR", p["biomarkers"])

    def test_mcode_protocol_text_not_cancer(self):
        b = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {
                            "text": "Polyp size greatest dimension by CAP cancer protocols"
                        },
                    }
                }
            ]
        }
        self.assertEqual(mcode_profile(b)["profile"]["cancer_type"], "not documented")

    def test_mcode_lung(self):
        p = mcode_profile(load_bundle("patient_001_breast_cancer"))["profile"]
        self.assertIn("non-small cell lung cancer", p["cancer_type"].lower())
        self.assertIn("EGFR", p["biomarkers"])
        self.assertEqual(p["stage"], "IV (inferred: metastatic)")
        self.assertEqual(p["ecog"], "1")

    def test_mcode_breast(self):
        p = mcode_profile(load_bundle("patient_004_her2"))["profile"]
        self.assertIn("breast", p["cancer_type"].lower())
        self.assertIn("HER2", p["biomarkers"])
        self.assertEqual(p["ecog"], "0")

    def test_n2c2_fixture_perfect(self):
        self.assertEqual(micro_f1(load_fixture())["micro_f1"], 1.0)


if __name__ == "__main__":
    unittest.main()
