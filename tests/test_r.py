"""R-track tests: signals, DCT, criteria feedback, zero-enroll, attrition, outlook."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.agents.attrition import predict_attrition
from backend.agents.criteria_feedback import design_feedback, grade_criterion
from backend.agents.dct_readiness import dct_readiness
from backend.agents.kri_monitor import zero_enroll_risk
from backend.agents.logreg import auc_score, fit_logreg, predict_proba
from backend.agents.risk_models import fitted_coefficients, outlook
from backend.agents.signal_detection import (
    bh_adjust,
    chi2_p,
    contingency,
    detect_signals,
    ic_shrunk,
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

    def test_chi2_p_known(self):
        self.assertAlmostEqual(chi2_p(4.0), 0.0455, places=3)
        self.assertEqual(chi2_p(0.0), 1.0)

    def test_bh_known_vector(self):
        self.assertEqual(
            [round(q, 3) for q in bh_adjust([0.01, 0.04, 0.5])],
            [0.03, 0.06, 0.5],
        )
        self.assertEqual(bh_adjust([]), [])

    def test_bh_gate_small_screen(self):
        tri = [_tri("TNX", "Liver") for _ in range(3)]
        tri += [_tri("TNX", "Other"), _tri("PBO", "Other"), _tri("PBO", "Other2")]
        for r in detect_signals(tri)["pairs"]:
            self.assertIsNone(r["q_value"])

    def test_bh_applied_large_screen(self):
        tri = []
        for i in range(5):
            tri += [_tri("TNX", f"E{i}") for _ in range(4)]
            tri += [_tri("PBO", f"E{i}") for _ in range(4)]
        tri += [_tri("TNX", "Hot") for _ in range(12)]
        tri += [_tri("PBO", "Cold") for _ in range(12)]
        rows = detect_signals(tri)["pairs"]
        self.assertGreaterEqual(len(rows), 10)
        by_event = {r["event"]: r for r in rows if r["drug"] == "TNX"}
        self.assertIsNotNone(by_event["Hot"]["q_value"])
        for r in rows:
            q = r["q_value"]
            self.assertIsNotNone(q)
            self.assertGreaterEqual(q, 0.0)
            self.assertLessEqual(q, 1.0)

    def test_shrinker_damps_explosive_prr(self):
        import math

        a, b, c, d = 1.5, 0.5, 0.5, 100.0
        prr, _ = prr_chi2(a, b, c, d)
        self.assertGreater(prr, 50.0)
        ic = ic_shrunk(a, b, c, d)
        self.assertLess(ic, math.log2(prr))

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


class FittedCoefficientsTests(unittest.TestCase):
    def _doc(self):
        return {
            "weights": {
                "fragility": -2.0,
                "burden": -1.0,
                "safety_excl": -0.5,
                "bias": 1.0,
            },
            "trained_on": "test-slice",
            "test_auc": 0.8,
        }

    def test_fail_closed(self):
        self.assertIsNone(fitted_coefficients("/nonexistent/path.json"))
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{bad json")
            name = f.name
        try:
            self.assertIsNone(fitted_coefficients(name))
        finally:
            os.unlink(name)

    def test_outlook_prefers_fitted(self):
        import json as _json

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            _json.dump(self._doc(), f)
            name = f.name
        try:
            with mock.patch("backend.agents.risk_models.FITTED_OUTLOOK", Path(name)):
                o = outlook(
                    {"protocol_fragility_index": 20.5},
                    {"total_score": 31},
                )
            self.assertIn("fitted coefficients", o["drivers"][-1])
            self.assertIn("test-slice", o["drivers"][-1])
        finally:
            os.unlink(name)


class LogRegTests(unittest.TestCase):
    def _blobs(self):
        import random

        rng = random.Random(11)
        X, y = [], []
        for _ in range(60):
            X.append([rng.gauss(0, 1), rng.gauss(0, 1)])
            y.append(0)
        for _ in range(60):
            X.append([rng.gauss(4, 1), rng.gauss(4, 1)])
            y.append(1)
        return X, y

    def test_fit_separates_blobs(self):
        X, y = self._blobs()
        w, b = fit_logreg(X, y, l2=0.1, iters=2000, lr=0.1)
        preds = [1 if p >= 0.5 else 0 for p in predict_proba(X, w, b)]
        acc = sum(1 for a, c in zip(preds, y) if a == c) / len(y)
        self.assertGreaterEqual(acc, 0.95)

    def test_auc_known(self):
        self.assertAlmostEqual(
            auc_score([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]), 0.75, places=6
        )
        self.assertEqual(auc_score([0.5, 0.5], [0, 1]), 0.5)

    def test_deterministic(self):
        X, y = self._blobs()
        self.assertEqual(fit_logreg(X, y), fit_logreg(X, y))


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

    def test_trend_cox_stuart(self):
        declining = [{"enrolled": e} for e in (12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1)]
        t = zero_enroll_risk(declining, 5)["trend"]
        self.assertEqual(t["direction"], "declining")
        self.assertLess(t["p_value"], 0.05)
        flat = [{"enrolled": 3}] * 8
        t = zero_enroll_risk(flat, 3)["trend"]
        self.assertEqual(t["direction"], "stable")
        self.assertEqual(t["p_value"], 1.0)


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
        # 5 drivers: the 5th labels fitted-vs-bootloader coefficient source.
        self.assertEqual(len(o["drivers"]), 5)
        self.assertIn("log-odds", " ".join(o["drivers"]))
        self.assertIn("bootloader priors", o["drivers"][-1])

    def test_monotone_in_fragility(self):
        lo = outlook(self._audit(10), {"total_score": 20})["success_probability"]
        hi = outlook(self._audit(80), {"total_score": 20})["success_probability"]
        self.assertGreater(lo, hi)


if __name__ == "__main__":
    unittest.main()
