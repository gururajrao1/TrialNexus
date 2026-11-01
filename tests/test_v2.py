"""V2 regression: multi-rule lines, washout windows, unit conversion, note ECOG."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

from agents.cohort_matcher import evaluate_patient as evaluate  # noqa: E402
from agents.protocol_auditor import (  # noqa: E402
    _parse_rules,
    _washout_days,
    parse_protocol,
)

FHIR = ROOT / "data" / "fhir" / "synthea"
PROTO = ROOT / "data" / "raw" / "protocols" / "protocol_oncology_phase3.txt"

INC04 = (
    "Adequate bone marrow reserve: Absolute Neutrophil Count (ANC) >= 1.5 x 10^9/L, "
    "Platelets >= 100 x 10^9/L, Hemoglobin >= 9.0 g/dL."
)
INC05 = "Serum creatinine <= 1.5x Upper Limit of Normal (ULN) or calculated CrCl >= 50 mL/min."


def load_bundle(pid):
    return json.loads((FHIR / f"{pid}.json").read_text())


def make_bundle(obs=(), meds=(), notes=(), pid="vx"):
    entries = [
        {"resource": {"resourceType": "Patient", "id": pid, "birthDate": "1980-01-01"}}
    ]
    for text, value, unit in obs:
        r = {"resourceType": "Observation", "code": {"text": text}}
        if value is not None:
            r["valueQuantity"] = {"value": value, "unit": unit}
        r["effectiveDateTime"] = "2025-05-20"
        entries.append({"resource": r})
    for text, dt in meds:
        r = {
            "resourceType": "MedicationStatement",
            "medicationCodeableConcept": {"text": text},
            "status": "active",
        }
        if dt:
            r["effectiveDateTime"] = dt
        entries.append({"resource": r})
    for section, text in notes:
        entries.append(
            {
                "resource": {
                    "resourceType": "DocumentReference",
                    "status": "current",
                    "type": {"text": section},
                    "content": [{"text": text}],
                }
            }
        )
    return {"id": pid, "entry": entries}


def one_inc(crit):
    return {"inclusion_criteria": [crit], "exclusion_criteria": []}


def one_exc(crit):
    return {"inclusion_criteria": [], "exclusion_criteria": [crit]}


class V2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        audit = parse_protocol(PROTO.read_text())
        cls.by_id = {c["id"]: c for c in audit["inclusion_criteria"]}
        cls.exc = {c["id"]: c for c in audit["exclusion_criteria"]}

    def test_auditor_splits_marrow_panel(self):
        rules, logic = _parse_rules(INC04)
        self.assertEqual(len(rules), 3)
        self.assertEqual(logic, "all")
        self.assertIn("anc", rules[0]["variable"].lower())
        self.assertIn("platelet", rules[1]["variable"].lower())
        self.assertIn("hemoglobin", rules[2]["variable"].lower())
        self.assertEqual(rules[2]["unit"], "g/dL")

    def test_auditor_or_logic(self):
        rules, logic = _parse_rules(INC05)
        self.assertEqual(len(rules), 2)
        self.assertEqual(logic, "any")

    def test_auditor_washout_parse(self):
        self.assertEqual(_washout_days("Prior TKI within 180 days of Day 1."), 180)
        self.assertEqual(_washout_days("No chemo within 4 weeks."), 28)
        self.assertEqual(_washout_days("No chemo within 6 months."), 180)
        self.assertIsNone(_washout_days("No window here."))

    def test_multi_rule_all_pass(self):
        ev = evaluate(
            one_inc(self.by_id["INC-04"]), load_bundle("patient_001_breast_cancer")
        )["inclusion_evaluations"][0]
        self.assertTrue(ev["passed"])
        self.assertFalse(ev["missing_data"])
        self.assertIn("ANC", ev["clinical_evidence_found"])
        self.assertIn("Platelets", ev["clinical_evidence_found"])
        self.assertIn("Hemoglobin", ev["clinical_evidence_found"])

    def test_multi_rule_all_fail(self):
        ev = evaluate(
            one_inc(self.by_id["INC-04"]), load_bundle("patient_002_control")
        )["inclusion_evaluations"][0]
        self.assertFalse(ev["passed"])
        self.assertFalse(ev["missing_data"])

    def test_multi_rule_any_pass(self):
        b = make_bundle(
            obs=[("Creatinine", 2.0, "mg/dL"), ("Creatinine clearance", 80, "mL/min")]
        )
        ev = evaluate(one_inc(self.by_id["INC-05"]), b)["inclusion_evaluations"][0]
        self.assertTrue(ev["passed"])

    def test_multi_rule_any_fail(self):
        b = make_bundle(
            obs=[("Creatinine", 2.0, "mg/dL"), ("Creatinine clearance", 40, "mL/min")]
        )
        ev = evaluate(one_inc(self.by_id["INC-05"]), b)["inclusion_evaluations"][0]
        self.assertFalse(ev["passed"])
        self.assertFalse(ev["missing_data"])

    def test_washout_triggered(self):
        self.assertEqual(self.exc["EXC-01"]["washout_days"], 180)
        ev = evaluate(one_exc(self.exc["EXC-01"]), load_bundle("patient_002_control"))[
            "exclusion_evaluations"
        ][0]
        self.assertTrue(ev["triggered"])
        self.assertIn("22 days", ev["clinical_evidence_found"])

    def test_washout_clear_old(self):
        b = make_bundle(meds=[("Osimertinib 80mg daily", "2024-01-01")])
        ev = evaluate(one_exc(self.exc["EXC-01"]), b)["exclusion_evaluations"][0]
        self.assertFalse(ev["triggered"])
        self.assertFalse(ev["missing_data"])

    def test_washout_undated_conservative(self):
        b = make_bundle(meds=[("Osimertinib 80mg daily", None)])
        ev = evaluate(one_exc(self.exc["EXC-01"]), b)["exclusion_evaluations"][0]
        self.assertTrue(ev["triggered"])

    def test_creatinine_units(self):
        crit = {
            "id": "INC-99",
            "category": "Renal",
            "raw_text": "Creatinine <= 1.5 mg/dL",
            "variable": "Creatinine",
            "operator": "<=",
            "value": 1.5,
            "unit": "mg/dL",
        }
        hi = make_bundle(obs=[("Creatinine", 150, "umol/L")])
        ev_hi = evaluate(one_inc(crit), hi)["inclusion_evaluations"][0]
        self.assertFalse(ev_hi["passed"])
        lo = make_bundle(obs=[("Creatinine", 100, "umol/L")])
        ev_lo = evaluate(one_inc(crit), lo)["inclusion_evaluations"][0]
        self.assertTrue(ev_lo["passed"])

    def test_note_ecog(self):
        crit = {
            "id": "INC-03",
            "category": "Performance Status",
            "raw_text": "ECOG 0 or 1",
            "variable": "ECOG",
            "operator": "IN",
            "value": [0, 1],
            "unit": None,
        }
        b = make_bundle(notes=[("Assessment", "ECOG 1, doing well.")])
        ev = evaluate(one_inc(crit), b)["inclusion_evaluations"][0]
        self.assertTrue(ev["passed"])
        self.assertIn("from clinical note", ev["clinical_evidence_found"])
        kps = make_bundle(notes=[("Assessment", "Karnofsky 90%, independent.")])
        ev_kps = evaluate(one_inc(crit), kps)["inclusion_evaluations"][0]
        self.assertTrue(ev_kps["passed"])

    def test_note_ecog_negation_safe(self):
        crit = {
            "id": "INC-03",
            "category": "Performance Status",
            "raw_text": "ECOG 0 or 1",
            "variable": "ECOG",
            "operator": "IN",
            "value": [0, 1],
            "unit": None,
        }
        b = make_bundle(notes=[("Assessment", "ECOG not recorded today.")])
        ev = evaluate(one_inc(crit), b)["inclusion_evaluations"][0]
        self.assertFalse(ev["passed"])
        self.assertTrue(ev["missing_data"])


if __name__ == "__main__":
    unittest.main()
