"""R-track tests: signals, DCT, criteria feedback, zero-enroll, attrition, outlook."""

import unittest

from backend.agents.attrition import predict_attrition
from backend.agents.criteria_feedback import design_feedback, grade_criterion
from backend.agents.dct_readiness import dct_readiness
from backend.agents.kri_monitor import zero_enroll_risk
from backend.agents.risk_models import outlook
from backend.agents.signal_detection import (
    contingency,
    detect_signals,
    prr_chi2,
    ror_ci,
)


def _tri(drug, pt, soc="S"):
    return {
        "suspect_drug": drug,
        "meddra_classification": {"preferred_term": pt, "soc": soc},
    }


class SignalTests(unittest.TestCase):
    def test_math_on_known_table(self):
        prr, chi2 = prr_chi2(20, 80, 5, 495)
        self.assertAlmostEqual(prr, 20.0, places=1)
        self.assertAlmostEqual(chi2, 75.3, places=0)
        ror, low, _high = ror_ci(20, 80, 5, 495)
        self.assertAlmostEqual(ror, 24.75, places=1)
        self.assertGreater(low, 1.0)

    def test_zero_cell_correction(self):
        a, b, c, d = contingency([("D", "E")], "D", "E")
        self.assertEqual((a, b, c, d), (1.5, 0.5, 0.5, 0.5))

    def test_statuses(self):
        tri = [_tri("TNX", "Liver") for _ in range(3)]
        tri += [_tri("TNX", "Other"), _tri("PBO", "Other"), _tri("PBO", "Other2")]
        rows = {
            r["event"]: r for r in detect_signals(tri)["pairs"] if r["drug"] == "TNX"
        }
        self.assertEqual(rows["Liver"]["status"], "watch")
        self.assertEqual(rows["Liver"]["n"], 3)
        solo = detect_signals([_tri("TNX", "Liver")])
        self.assertEqual(solo["pairs"][0]["status"], "insufficient-comparator")


class DctTests(unittest.TestCase):
    def test_verdicts_and_score(self):
        b = {
            "visits": [
                {"day": "1", "procedures": ["pk draws x6"], "pk_units": 6},
                {"day": "14", "procedures": ["labs"], "pk_units": 0},
                {"day": "16", "procedures": [], "pk_units": 0},
            ]
        }
        d = dct_readiness(b, "consent obtained Day -7")
        self.assertEqual(
            [v["verdict"] for v in d["visits"]],
            ["on-site", "remote-capable", "remote-capable"],
        )
        self.assertEqual(d["readiness_score"], 67)
        self.assertTrue(d["econsent_mentioned"])


class CriteriaTests(unittest.TestCase):
    def test_grades(self):
        vague = grade_criterion(
            {
                "id": "X",
                "raw_text": "Adequate organ function per investigator judgment.",
            }
        )
        self.assertEqual(vague["grade"], "C")
        clean = grade_criterion(
            {"id": "Y", "raw_text": "Serum creatinine <= 1.5 mg/dL at screening."}
        )
        self.assertEqual(clean["grade"], "A")
        bundled = grade_criterion(
            {
                "id": "Z",
                "raw_text": "ANC >= 1.5 /uL, platelets >= 100 /uL.",
                "sub_rules": [{}, {}],
            }
        )
        self.assertEqual(bundled["grade"], "B")
        f = design_feedback(
            {
                "inclusion_criteria": [
                    {"id": "Y", "raw_text": "Serum creatinine <= 1.5 mg/dL."}
                ],
                "exclusion_criteria": [],
            }
        )
        self.assertEqual(f["design_score"], 100)


class ZeroEnrollTests(unittest.TestCase):
    def test_bands(self):
        bad = [{"enrolled": e} for e in (1, 0, 1, 0)]
        good = [{"enrolled": e} for e in (3, 3, 4, 3)]
        self.assertEqual(zero_enroll_risk(bad, 3)["band"], "high")
        self.assertEqual(zero_enroll_risk(good, 3)["band"], "low")
        self.assertEqual(zero_enroll_risk([], 3)["band"], "elevated")


class AttritionTests(unittest.TestCase):
    def test_shape_and_monotone(self):
        light = {"visits": [{"day": "1"}, {"day": "8"}], "total_score": 6}
        heavy = {
            "visits": [{"day": str(i)} for i in range(8)],
            "total_score": 40,
        }
        a_light = predict_attrition(light, {"remote_capable_n": 2}, 0)
        a_heavy = predict_attrition(heavy, {"remote_capable_n": 0}, 2)
        self.assertGreater(a_heavy["dropout_pct"], a_light["dropout_pct"])
        self.assertLessEqual(a_light["dropout_pct"], 60)
        self.assertGreaterEqual(a_light["dropout_pct"], 5)
        lo, hi = a_light["interval_pct"]
        self.assertLess(lo, a_light["dropout_pct"])
        self.assertGreater(hi, a_light["dropout_pct"])
        no_relief = predict_attrition(light, {"remote_capable_n": 0}, 0)
        self.assertGreater(no_relief["dropout_pct"], a_light["dropout_pct"])


class OutlookTests(unittest.TestCase):
    def _audit(self, frag, phase="Phase 3"):
        return {
            "protocol_metadata": {"phase": phase},
            "protocol_fragility_index": frag,
            "exclusion_criteria": [{"category": "Cardiac"}],
        }

    def test_calibrated_contract(self):
        o = outlook(self._audit(20.5), {"total_score": 31})
        self.assertGreaterEqual(o["success_probability"], 0.01)
        self.assertLessEqual(o["success_probability"], 0.95)
        self.assertAlmostEqual(sum(o["failure_breakdown"].values()), 1.0, places=2)
        self.assertEqual(len(o["drivers"]), 4)
        self.assertIn("log-odds", " ".join(o["drivers"]))

    def test_monotone_in_fragility(self):
        lo = outlook(self._audit(10), {"total_score": 20})["success_probability"]
        hi = outlook(self._audit(80), {"total_score": 20})["success_probability"]
        self.assertGreater(lo, hi)


if __name__ == "__main__":
    unittest.main()
