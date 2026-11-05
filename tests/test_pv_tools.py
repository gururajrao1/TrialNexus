"""PV shells tests: E2B XML, DSUR shell, risk register, signal review."""

import unittest

from backend.agents.pv_tools import (
    build_risk_register,
    dsur_shell,
    e2b_xml,
    review_signals,
)

RECORD = {
    "discrepancy_id": "D-1",
    "patient_id": "P-9",
    "suspect_drug": "osimertinib",
    "reported_term": "pneumonitis",
    "severity_grade": "Grade 3",
    "is_sae": True,
    "meddra_classification": {"soc": "Respiratory", "preferred_term": "Pneumonitis"},
}


class E2BTests(unittest.TestCase):
    def test_core_elements_present(self):
        out = e2b_xml(RECORD)
        self.assertIn("<reactionmeddrapt>Pneumonitis</reactionmeddrapt>", out["xml"])
        self.assertIn("<medicinalproduct>osimertinib</medicinalproduct>", out["xml"])
        self.assertIn("<serious>1</serious>", out["xml"])
        self.assertTrue(out["serious"])

    def test_non_serious_flag(self):
        out = e2b_xml({**RECORD, "is_sae": False})
        self.assertIn("<serious>2</serious>", out["xml"])

    def test_escapes_markup(self):
        out = e2b_xml({**RECORD, "reported_term": "rash <severe> & spreading"})
        self.assertNotIn("<severe>", out["xml"])
        self.assertIn("&lt;severe&gt;", out["xml"])

    def test_bad_shape(self):
        self.assertIn("error", e2b_xml("nope"))


class DsurTests(unittest.TestCase):
    def test_counts_and_fill_markers(self):
        queries = [
            {"resolution_status": "OPEN", "is_sae": True},
            {"resolution_status": "RESOLVED", "is_sae": False},
        ]
        out = dsur_shell(
            {"id": "P1", "title": "T"}, queries, [{"eligibility_status": "ELIGIBLE"}]
        )
        self.assertEqual(out["counts"]["safety_queries"], 2)
        self.assertEqual(out["counts"]["open_queries"], 1)
        self.assertEqual(out["counts"]["sae_queries"], 1)
        self.assertTrue(any("[FILL]" in s["body"] for s in out["sections"]))


class RiskRegisterTests(unittest.TestCase):
    def test_ranking_signal_first(self):
        signals = [
            {
                "drug": "b",
                "drug_label": "b",
                "event": "e1",
                "status": "monitored",
                "n": 10,
                "prr": 1.0,
            },
            {
                "drug": "a",
                "drug_label": "a",
                "event": "e2",
                "status": "signal",
                "n": 3,
                "prr": 4.0,
            },
        ]
        out = build_risk_register(signals)
        self.assertEqual(out["risks"][0]["drug"], "a")
        self.assertEqual(out["risks"][0]["owner"], "Safety physician")

    def test_skips_bad_rows(self):
        self.assertEqual(build_risk_register(["nope"])["risks"], [])


class NarrativeTests(unittest.TestCase):
    def test_narrative_shape(self):
        from backend.agents.pv_tools import sae_narrative

        out = sae_narrative(RECORD)
        self.assertIn("NARRATIVE", out["narrative"])
        self.assertIn("P-9", out["narrative"])
        self.assertIn("[FILL", out["narrative"])

    def test_narrative_rejects_shape(self):
        from backend.agents.pv_tools import sae_narrative

        with self.assertRaises(ValueError):
            sae_narrative([])


class ContraTests(unittest.TestCase):
    def test_hit_in_warning_section(self):
        from backend.agents.pv_tools import screen_concomitant

        out = screen_concomitant(
            {
                "Boxed Warning": "Avoid use with ketoconazole due to risk.",
                "Dosage": "Take daily with food.",
            },
            ["ketoconazole", "aspirin"],
        )
        self.assertEqual(len(out["hits"]), 1)
        self.assertEqual(out["hits"][0]["med"], "ketoconazole")

    def test_partial_word_no_hit(self):
        from backend.agents.pv_tools import screen_concomitant

        out = screen_concomitant({"Warnings": "Avoid ketoacidosis risk."}, ["keto"])
        self.assertEqual(out["hits"], [])


class EscalationTests(unittest.TestCase):
    def test_levels(self):
        from backend.agents.pv_tools import escalation_chains

        out = escalation_chains(
            {
                "escalation_list": [
                    {"id": "a", "days_overdue": 5},
                    {"id": "b", "days_overdue": 40},
                    {"id": "c", "days_overdue": 70},
                ]
            }
        )
        by_id = {c["id"]: c["level"] for c in out["chains"]}
        self.assertEqual(by_id, {"a": "site", "b": "cra+manager", "c": "sponsor+capa"})
        self.assertEqual(out["n_chains"], 3)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.signals = [
            {"drug": "a", "event": "e1", "status": "signal"},
            {"drug": "b", "event": "e2", "status": "watch"},
        ]

    def test_accept_and_monitor(self):
        out = review_signals(
            self.signals,
            [
                {"drug": "a", "event": "e1", "decision": "accept", "note": "seen"},
                {"drug": "b", "event": "e2", "decision": "monitor"},
            ],
        )
        self.assertEqual(out["n_reviewed"], 2)
        self.assertEqual(out["signals"][0]["review"], "accept")
        self.assertEqual(len(out["trail"]), 2)
        self.assertEqual(out["errors"], [])

    def test_unknown_pair_and_bad_verdict_reported(self):
        out = review_signals(
            self.signals,
            [
                {"drug": "z", "event": "e9", "decision": "accept"},
                {"drug": "a", "event": "e1", "decision": "maybe"},
            ],
        )
        self.assertEqual(out["n_reviewed"], 0)
        self.assertEqual(len(out["errors"]), 2)
        self.assertNotIn("review", out["signals"][0])


if __name__ == "__main__":
    unittest.main()
