import unittest


class CsvMapTests(unittest.TestCase):
    def test_visits_aliases(self):
        from backend.agents.inbox import map_csv_records

        out = map_csv_records(
            "Site,Subject ID,Visit,Planned Day,Actual Day,Consent Date\n"
            "SITE-001,P-1,Week 8,56,63,2026-08-01\n",
            "visits",
        )
        self.assertEqual(out["n_rows"], 1)
        rec = out["records"][0]
        self.assertEqual(rec["site_id"], "SITE-001")
        self.assertEqual(rec["subject"], "P-1")
        self.assertEqual(rec["planned_day"], "56")
        self.assertEqual(rec["actual_day"], "63")
        self.assertIn("mapped_columns", out)

    def test_queries_aliases_and_truthy(self):
        from backend.agents.inbox import map_csv_records

        out = map_csv_records(
            "Query ID,Open Date,Status,SAE\nQ-1,2026-09-01,OPEN,yes\nQ-2,2026-09-02,RESOLVED,\n",
            "queries",
        )
        self.assertEqual(out["n_rows"], 2)
        self.assertTrue(out["records"][0]["is_sae"])
        self.assertFalse(out["records"][1]["is_sae"])
        self.assertEqual(out["records"][1]["resolution_status"], "RESOLVED")

    def test_bad_target_and_no_columns(self):
        from backend.agents.inbox import map_csv_records

        bad = map_csv_records("a,b\n1,2\n", "nope")
        self.assertIn("error", bad)
        self.assertEqual(bad["records"], [])
        none = map_csv_records("foo,bar\n1,2\n", "queries")
        self.assertIn("error", none)
        self.assertIn("foo", none["unmapped_columns"])
        empty = map_csv_records("", "visits")
        self.assertIn("error", empty)


class ProtocolDiffTests(unittest.TestCase):
    A = (
        "Trial T\nPhase 3\nTarget enrollment: 100\n"
        "Inclusion criteria:\n1. Age 18 or older.\n2. EGFR mutation.\n"
        "Exclusion criteria:\n1. Pregnant.\n"
    )
    B = (
        "Trial T amended\nPhase 3\nTarget enrollment: 200\n"
        "Inclusion criteria:\n1. Age 21 or older.\n2. EGFR mutation.\n3. ECOG 0-1.\n"
        "Exclusion criteria:\n"
    )

    def test_added_rewritten_dropped_and_meta(self):
        from backend.agents.protocol_auditor import diff_protocols

        d = diff_protocols(self.A, self.B, "v1", "v2")
        changes = {(c["id"], c["change"]) for c in d["criteria_changes"]}
        self.assertIn(("INC-01", "rewritten"), changes)
        self.assertIn(("INC-03", "added"), changes)
        self.assertIn(("EXC-01", "dropped"), changes)
        self.assertTrue(
            any(m["field"] == "target_enrollment" for m in d["metadata_changes"])
        )
        self.assertGreater(d["n_changes"], 0)

    def test_empty_raises(self):
        from backend.agents.protocol_auditor import diff_protocols

        with self.assertRaises(ValueError):
            diff_protocols("", self.B)


class FunnelTests(unittest.TestCase):
    def test_status_mix_and_weeks(self):
        from backend.agents.failure_forensics import screening_funnel

        out = screening_funnel(
            [
                {
                    "eligibility_status": "ELIGIBLE",
                    "evaluated_at": "2026-09-01T10:00:00",
                },
                {
                    "eligibility_status": "INELIGIBLE",
                    "evaluated_at": "2026-09-01T11:00:00",
                },
                {
                    "eligibility_status": "REVIEW_REQUIRED",
                    "evaluated_at": "2026-09-08T10:00:00",
                },
                {"weird": True},
            ]
        )
        self.assertEqual(out["n_evaluations"], 4)
        self.assertEqual(out["by_status"]["ELIGIBLE"], 1)
        self.assertEqual(out["by_status"]["unknown"], 1)
        self.assertEqual(out["conversion_pct"], 25.0)
        self.assertEqual(len(out["by_week"]), 2)

    def test_empty(self):
        from backend.agents.failure_forensics import screening_funnel

        out = screening_funnel([])
        self.assertEqual(out["n_evaluations"], 0)
        self.assertEqual(out["conversion_pct"], 0.0)


class QueryLetterTests(unittest.TestCase):
    def test_fields_and_fill(self):
        from backend.agents.pv_tools import query_letter

        out = query_letter(
            {
                "discrepancy_id": "D-1",
                "patient_id": "P-9",
                "suspect_drug": "osimertinib",
                "reported_term": "rash",
                "severity_grade": "Grade 2",
                "site_query": {
                    "query_target": "SITE-001 coordinator",
                    "query_text": "Confirm onset date.",
                    "auto_close_condition": "onset date entered",
                },
            }
        )
        self.assertIn("SITE-001 coordinator", out["body"])
        self.assertIn("Confirm onset date.", out["body"])
        self.assertIn("[FILL", out["body"])
        self.assertEqual(out["subject"], "Data query D-1")

    def test_non_dict_raises(self):
        from backend.agents.pv_tools import query_letter

        with self.assertRaises(ValueError):
            query_letter("nope")


class DigestCloseoutTests(unittest.TestCase):
    def test_digest_ranks_overdue_first(self):
        from backend.agents.ops_tools import morning_digest

        out = morning_digest(
            [
                {
                    "protocol_id": "A",
                    "open_queries": 1,
                    "overdue_queries": 0,
                    "sae_queries": 0,
                },
                {
                    "protocol_id": "B",
                    "open_queries": 5,
                    "overdue_queries": 3,
                    "sae_queries": 1,
                },
            ],
            [{"site_id": "S1", "stage": "contract", "flags": ["slow"]}],
            [{"protocol_id": "A", "recruiting_competitors": 50, "source": "live"}],
        )
        self.assertEqual(out["overdue_queries"], 3)
        self.assertEqual(out["items"][0]["protocol_id"], "B")
        self.assertEqual(out["n_competition_alerts"], 1)

    def test_closeout_marks_tmf_fills(self):
        from backend.agents.ops_tools import closeout_pack, inspection_pack

        out = closeout_pack(
            {"id": "P", "title": "T"}, {"queries": 4, "sae": 1, "deviations": 2}
        )
        self.assertEqual(len(out["exhibits"]), 7)
        self.assertTrue(any("[FILL" in e["status"] for e in out["exhibits"]))
        self.assertTrue(out["ready"])
        linked = [e for e in out["exhibits"] if e.get("panel")]
        self.assertTrue(linked)
        self.assertTrue(all(e["status"] != "[FILL]" for e in linked))
        insp = inspection_pack(
            {"id": "P", "title": "T"},
            {"queries": 1, "overdue": 0, "sae": 0, "deviations": 1},
            [],
        )
        self.assertTrue(any(e.get("panel") == "safety" for e in insp["exhibits"]))


if __name__ == "__main__":
    unittest.main()
