"""Ops tools tests: extended KRIs, monitoring plan, SIV list, rollup."""

import unittest

from backend.agents.kri_monitor import site_kris
from backend.agents.ops_tools import (
    milestone_rollup,
    monitoring_plan,
    siv_checklist,
)

ROWS = [
    {
        "month": "2026-01",
        "screened": 20,
        "enrolled": 15,
        "open_queries": 4,
        "deviations": 1,
        "sae": 0,
    }
]


class KriExtensionTests(unittest.TestCase):
    def test_old_rows_unaffected(self):
        out = site_kris(ROWS, 3)
        self.assertEqual(len(out["kris"]), 5)
        self.assertEqual(out["worst"], "ok")  # enrolled 15/3, no gap

    def test_consent_kri_fires(self):
        rows = [{**ROWS[0], "consent_deviations": 3, "eligibility_deviations": 0}]
        out = site_kris(rows, 20)
        by_name = {k["kri"]: k for k in out["kris"]}
        self.assertEqual(by_name["consent_deviation_pct"]["value"], 15.0)
        self.assertEqual(by_name["consent_deviation_pct"]["status"], "alert")
        self.assertEqual(by_name["eligibility_deviation_pct"]["status"], "ok")

    def test_overdue_query_kri(self):
        rows = [{**ROWS[0], "open_queries": 4, "overdue_queries": 3}]
        out = site_kris(rows, 20)
        by_name = {k["kri"]: k for k in out["kris"]}
        self.assertEqual(by_name["query_overdue_pct"]["value"], 75.0)
        self.assertEqual(by_name["query_overdue_pct"]["status"], "alert")


class MonitoringPlanTests(unittest.TestCase):
    def test_tiers_map_to_sdv(self):
        out = monitoring_plan(
            {"id": "P1", "title": "T"},
            [
                {"site_id": "S1", "tier": "critical", "reason": "x"},
                {"site_id": "S2", "tier": "bogus"},
            ],
        )
        self.assertEqual(out["sites"][0]["tier"], "critical")
        self.assertIn("100%", out["sites"][0]["sdv"])
        self.assertEqual(out["sites"][1]["tier"], "minor")
        self.assertIn("Monitoring plan", out["markdown"])


class SivTests(unittest.TestCase):
    def test_criteria_become_items(self):
        out = siv_checklist(
            {
                "inclusion_criteria": [{"raw_text": "Age 18 or older"}],
                "exclusion_criteria": [{"raw_text": "Pregnant"}],
            }
        )
        joined = " ".join(out["items"])
        self.assertIn("Age 18", joined)
        self.assertIn("Pregnant", joined)
        self.assertIn("SAE reporting", joined)


class BudgetTests(unittest.TestCase):
    def test_math(self):
        from backend.agents.ops_tools import budget_estimate

        out = budget_estimate(
            {
                "arms": [{"name": "A", "n_subjects": 10}],
                "visits": [
                    {
                        "name": "V1",
                        "n_per_subject": 2,
                        "procedures": [
                            {"name": "labs", "unit_cost": 50, "count_per_visit": 1},
                            {"name": "ecg", "unit_cost": 100, "count_per_visit": 2},
                        ],
                    }
                ],
                "fixed_costs": [{"name": "setup", "amount": 500}],
            }
        )
        self.assertEqual(out["per_subject"], 500.0)
        self.assertEqual(out["grand_total"], 5500.0)

    def test_missing_inputs(self):
        from backend.agents.ops_tools import budget_estimate

        with self.assertRaises(ValueError):
            budget_estimate({"arms": [], "visits": []})


class CodeWhysTests(unittest.TestCase):
    def test_code_known_and_unknown(self):
        from backend.agents.ops_tools import code_deviation, five_whys

        self.assertEqual(code_deviation("consent-violation")["cdisc_code"], "C158839")
        self.assertEqual(code_deviation("weird")["cdisc_code"], "C158842")
        self.assertEqual(len(five_whys("missing-assessment")["questions"]), 5)
        self.assertIn("effectiveness_check", five_whys("missing-assessment"))


class ReportPackTests(unittest.TestCase):
    def test_visit_report(self):
        from backend.agents.ops_tools import visit_report

        out = visit_report(
            [
                {
                    "severity": "major",
                    "type": "out-of-window",
                    "subject": "s",
                    "visit": "v",
                    "detail": "d",
                }
            ],
            {"site_id": "S1", "tier": "major"},
        )
        self.assertEqual(out["n_findings"], 1)
        self.assertIn("S1", out["markdown"])

    def test_inspection_pack(self):
        from backend.agents.ops_tools import inspection_pack

        out = inspection_pack(
            {"id": "P1", "title": "T"},
            {"deviations": 2, "queries": 3, "overdue": 1, "sae": 1},
            [],
        )
        self.assertEqual(len(out["exhibits"]), 8)
        self.assertTrue(any("[FILL" in e["status"] for e in out["exhibits"]))

    def test_dsmb_pack(self):
        from backend.agents.ops_tools import dsmb_pack

        out = dsmb_pack(
            {"id": "P1", "title": "T"},
            [{"stage": "activated"}, {"stage": "contract"}],
            {"total": 4, "open": 1, "sae": 1},
            {"ELIGIBLE": 5},
            1,
        )
        self.assertEqual(out["n_activated"], 1)
        self.assertIn("DSMB", out["markdown"])


class RollupTests(unittest.TestCase):
    def test_counts_and_actions(self):
        report = {
            "sites": [
                {
                    "site_id": "S1",
                    "stage": "activated",
                    "days_in_stage": 5,
                    "flags": [],
                },
                {
                    "site_id": "S2",
                    "stage": "contract",
                    "days_in_stage": 120,
                    "flags": ["CTA negotiation 120d exceeds ~90-day benchmark"],
                },
            ]
        }
        out = milestone_rollup(report)
        self.assertEqual(out["by_stage"]["activated"], 1)
        self.assertEqual(out["pct_activated"], 50.0)
        self.assertEqual(len(out["flagged"]), 1)
        self.assertIn("CTA", out["flagged"][0]["next_action"])

    def test_empty_report(self):
        out = milestone_rollup({})
        self.assertEqual(out["n_sites"], 0)
        self.assertEqual(out["flagged"], [])


if __name__ == "__main__":
    unittest.main()
