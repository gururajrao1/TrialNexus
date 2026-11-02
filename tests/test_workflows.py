"""Workflow tests: prescreen queue ranking + deviation watch rules.

Pure-function coverage for the B2/B5 coordinators; endpoints are
exercised by the live e2e suite. No network, no database.
"""

import unittest

from backend.agents.deviation_watch import watch_deviations
from backend.agents.prescreen_queue import rank_prescreen


def _result(pid, status, match, missing=(), fails=(), triggered=()):
    inc = [
        {
            "criterion_id": c,
            "passed": False,
            "missing_data": True,
            "clinical_evidence_found": "no labs on file",
        }
        for c in missing
    ]
    inc += [
        {
            "criterion_id": c,
            "passed": False,
            "missing_data": False,
            "clinical_evidence_found": "low value",
        }
        for c in fails
    ]
    if status == "ELIGIBLE":
        inc = [
            {
                "criterion_id": "INC-01",
                "passed": True,
                "missing_data": False,
                "clinical_evidence_found": "ok",
            }
        ]
    return {
        "patient_id": pid,
        "overall_status": status,
        "match_percentage": match,
        "inclusion_evaluations": inc,
        "exclusion_evaluations": [
            {
                "criterion_id": c,
                "triggered": True,
                "missing_data": False,
                "clinical_evidence_found": "present",
            }
            for c in triggered
        ],
        "physician_action_items": [],
    }


class PrescreenTests(unittest.TestCase):
    def test_review_leads_eligible_weighted_by_drivers(self):
        results = [
            _result("p-elig", "ELIGIBLE", 100.0),
            _result("p-rev", "REVIEW_REQUIRED", 80.0, missing=("INC-04", "INC-01")),
            _result("p-rev2", "REVIEW_REQUIRED", 60.0, missing=("INC-09",)),
        ]
        drivers = [
            {"criterion_id": "INC-04", "rate": 50.0},
            {"criterion_id": "INC-01", "rate": 20.0},
        ]
        r = rank_prescreen(results, drivers)
        ids = [x["patient_id"] for x in r["rows"]]
        self.assertEqual(ids, ["p-rev", "p-rev2", "p-elig"])
        by_id = {x["patient_id"]: x for x in r["rows"]}
        self.assertAlmostEqual(by_id["p-rev"]["priority_score"], 2.7)
        self.assertEqual(by_id["p-rev"]["n_missing"], 2)
        self.assertEqual(r["summary"]["n_review"], 2)
        self.assertEqual(r["summary"]["n_eligible"], 1)

    def test_near_miss_included_multi_fail_excluded(self):
        results = [
            _result("p-near", "INELIGIBLE", 90.0, fails=("INC-04",)),
            _result("p-out", "INELIGIBLE", 40.0, fails=("INC-04", "INC-01")),
        ]
        r = rank_prescreen(results)
        ids = [x["patient_id"] for x in r["rows"]]
        self.assertEqual(ids, ["p-near"])
        self.assertTrue(r["rows"][0]["near_miss"])
        self.assertEqual(r["summary"]["n_near_miss"], 1)

    def test_empty(self):
        r = rank_prescreen([])
        self.assertEqual(r["rows"], [])
        self.assertEqual(r["summary"]["n_review"], 0)


class DeviationTests(unittest.TestCase):
    def test_window_missing_consent(self):
        recs = [
            {
                "site_id": "S1",
                "subject": "a",
                "visit": "V2",
                "planned_day": 14,
                "actual_day": 22,
                "assessments_required": ["ECG", "labs"],
                "assessments_done": ["ECG"],
                "consent_date": "2026-02-01",
                "visit_date": "2026-01-20",
            },
            {
                "site_id": "S1",
                "subject": "b",
                "visit": "V1",
                "planned_day": 1,
                "actual_day": 2,
                "assessments_required": ["ECG"],
                "assessments_done": ["ECG"],
                "consent_date": "2026-01-01",
                "visit_date": "2026-01-02",
            },
        ]
        r = watch_deviations(recs, window_days=3)
        kinds = {(f["subject"], f["type"], f["severity"]) for f in r["findings"]}
        self.assertIn(("a", "out-of-window", "major"), kinds)
        self.assertIn(("a", "missing-assessment", "major"), kinds)
        self.assertIn(("a", "consent-violation", "critical"), kinds)
        self.assertNotIn("b", {f["subject"] for f in r["findings"]})
        self.assertEqual(r["by_site"][0]["tier"], "100% critical fields")
        self.assertEqual(r["summary"]["n_findings"], 3)

    def test_deviation_site_rate_signal(self):
        recs = []
        for i in range(10):
            recs.append(
                {
                    "site_id": "S1",
                    "subject": f"s1-{i}",
                    "visit": "V1",
                    "planned_day": 1,
                    "actual_day": 22 if i < 8 else 2,
                    "assessments_required": [],
                    "assessments_done": [],
                }
            )
        for i in range(10):
            recs.append(
                {
                    "site_id": "S2",
                    "subject": f"s2-{i}",
                    "visit": "V1",
                    "planned_day": 1,
                    "actual_day": 2,
                    "assessments_required": [],
                    "assessments_done": [],
                }
            )
        r = watch_deviations(recs, window_days=3)
        sig = {s["site_id"]: s for s in r["site_signals"]}
        self.assertEqual(sig["S1"]["direction"], "high")
        self.assertLess(sig["S1"]["p_value"], 0.05)
        self.assertTrue(sig["S1"]["flag"])
        self.assertFalse(sig["S2"]["flag"])

    def test_clean_site_samples(self):
        r = watch_deviations(
            [
                {
                    "site_id": "S9",
                    "subject": "z",
                    "visit": "V1",
                    "planned_day": 1,
                    "actual_day": 1,
                    "assessments_required": [],
                    "assessments_done": [],
                }
            ]
        )
        self.assertEqual(r["findings"], [])
        self.assertEqual(r["by_site"], [])
        self.assertEqual(r["summary"]["n_records"], 1)


if __name__ == "__main__":
    unittest.main()
