"""C-track tests: CSM stats, lock readiness, adaptive design, consent."""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from backend.agents.adaptive_design import group_sequential
from backend.agents.consent_helper import check_consent
from backend.agents.crf_trace import trace_criteria
from backend.agents.csm import csm_screen, funnel_flags, poisson_sf, robust_z
from backend.agents.lock_readiness import lock_readiness, query_aging
from backend.database import (
    init_db,
    insert_safety_query,
    list_safety_queries,
    update_safety_resolution,
)


class CsmTests(unittest.TestCase):
    def test_robust_z_outlier(self):
        self.assertAlmostEqual(robust_z(10.0, [1, 1, 1, 1, 10]), 2.0, places=1)
        self.assertEqual(robust_z(5.0, [5, 5, 5]), 0.0)
        self.assertEqual(robust_z(9.0, [1, 2]), 0.0)

    def test_poisson_tails(self):
        self.assertEqual(poisson_sf(0, 3.0), 1.0)
        self.assertLess(poisson_sf(10, 1.0), 0.001)
        self.assertGreater(poisson_sf(1, 5.0), 0.99)

    def test_funnel(self):
        self.assertEqual(funnel_flags(0.9, 100, 0.1), "out99")
        self.assertEqual(funnel_flags(0.1, 100, 0.1), "in")

    def test_screen_flags_outlier_site(self):
        rows = []
        for sid, dev in (("A", 0), ("B", 0), ("C", 12)):
            rows.append(
                {
                    "site_id": sid,
                    "enrolled": 10,
                    "screened": 12,
                    "open_queries": 2,
                    "deviations": dev,
                    "sae": 0,
                }
            )
        r = csm_screen(rows)
        by_id = {s["site_id"]: s for s in r["sites"]}
        self.assertGreater(by_id["C"]["n_flagged"], 0)
        dev_flags = [
            s for s in by_id["C"]["signals"] if s["kri"] == "dev" and s["flag"]
        ]
        self.assertEqual(len(dev_flags), 1)
        self.assertEqual(dev_flags[0]["direction"], "high")


class LockTests(unittest.TestCase):
    def test_buckets_and_rag(self):
        qs = [
            {
                "id": "a",
                "created_at": "2026-10-01 10:00:00",
                "resolution_status": "TRIAGED",
            },
            {
                "id": "b",
                "created_at": "2026-10-28 10:00:00",
                "resolution_status": "TRIAGED",
            },
            {
                "id": "c",
                "created_at": "2026-10-29 10:00:00",
                "resolution_status": "RESOLVED",
            },
            {
                "id": "d",
                "created_at": "2026-10-29 10:00:00",
                "resolution_status": "TRIAGED",
                "is_sae": True,
            },
        ]
        r = lock_readiness(qs, date(2026, 11, 1))
        self.assertEqual(r["buckets"]["31-60"], 1)
        self.assertEqual(r["buckets"]["0-7"], 2)
        self.assertEqual(r["n_open"], 3)
        self.assertEqual(r["n_resolved"], 1)
        self.assertEqual(r["overall"], "red")
        self.assertIn("a", r["stale_ids"])

    def test_resolve_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            init_db(db)
            insert_safety_query(
                {
                    "id": "q1",
                    "protocol_id": "PX",
                    "reported_term": "X",
                    "severity": "MILD",
                },
                db_path=db,
            )
            self.assertTrue(update_safety_resolution("q1", "RESOLVED", db_path=db))
            rows = list_safety_queries("PX", db_path=db)
            self.assertEqual(rows[0]["resolution_status"], "RESOLVED")
            self.assertFalse(update_safety_resolution("nope", "RESOLVED", db_path=db))


class QueryAgingTests(unittest.TestCase):
    def test_routing_and_breach(self):
        qs = [
            {
                "id": "sae-1",
                "created_at": "2026-10-20 10:00:00",
                "resolution_status": "TRIAGED",
                "is_sae": True,
            },
            {
                "id": "old-1",
                "created_at": "2026-09-01 10:00:00",
                "resolution_status": "OPEN",
            },
            {
                "id": "fresh-1",
                "created_at": "2026-10-30 10:00:00",
                "resolution_status": "TRIAGED",
            },
            {
                "id": "done-1",
                "created_at": "2026-08-01 10:00:00",
                "resolution_status": "RESOLVED",
            },
        ]
        r = query_aging(qs, date(2026, 11, 1))
        by_id = {row["id"]: row for row in r["rows"]}
        self.assertEqual(by_id["sae-1"]["owner"], "drug safety")
        self.assertEqual(by_id["sae-1"]["sla_days"], 7)
        self.assertEqual(by_id["sae-1"]["days_overdue"], 5)
        self.assertEqual(by_id["sae-1"]["escalation"], "overdue")
        self.assertEqual(by_id["old-1"]["owner"], "site coordinator")
        self.assertEqual(by_id["old-1"]["sla_days"], 30)
        self.assertEqual(by_id["old-1"]["days_overdue"], 31)
        self.assertEqual(by_id["old-1"]["escalation"], "escalate")
        self.assertEqual(by_id["fresh-1"]["escalation"], "on-track")
        self.assertNotIn("done-1", by_id)
        self.assertEqual(r["owner_matrix"]["drug safety"]["8-30"], 1)
        self.assertEqual(r["owner_matrix"]["site coordinator"]["61-90"], 1)
        self.assertEqual([e["id"] for e in r["escalation_list"]], ["old-1", "sae-1"])
        self.assertEqual(r["n_overdue"], 2)
        breach = {b["owner"]: b for b in r["owner_breach"]}
        self.assertEqual(breach["drug safety"]["breach_rate"], 1.0)
        self.assertEqual(breach["site coordinator"]["breach_rate"], 0.5)
        for b in r["owner_breach"]:
            lo, hi = b["ci95"]
            self.assertLessEqual(lo, b["breach_rate"])
            self.assertLessEqual(b["breach_rate"], hi)
            self.assertGreaterEqual(lo, 0)
            self.assertLessEqual(hi, 1)

    def test_empty_queries(self):
        r = query_aging([], date(2026, 11, 1))
        self.assertEqual(r["rows"], [])
        self.assertEqual(r["escalation_list"], [])
        self.assertEqual(r["n_overdue"], 0)


class CrfTraceTests(unittest.TestCase):
    def _criteria(self):
        return {
            "inclusion_criteria": [
                {
                    "id": "INC-01",
                    "variable": "absolute neutrophil count",
                    "operator": ">=",
                    "value": 1.5,
                    "unit": "K/uL",
                    "raw_text": "ANC >= 1.5 K/uL",
                },
                {
                    "id": "INC-02",
                    "variable": "hemoglobin",
                    "operator": ">=",
                    "value": 9.0,
                    "unit": "g/dL",
                    "raw_text": "Hemoglobin >= 9 g/dL",
                },
            ],
            "exclusion_criteria": [
                {
                    "id": "EXC-01",
                    "variable": "myocardial infarction",
                    "operator": "=",
                    "value": "history",
                    "unit": "",
                    "raw_text": "History of MI within 6 months",
                },
            ],
        }

    def test_covered_and_missing(self):
        r = trace_criteria(
            self._criteria(), ["anc_result", "hemoglobin_g_dl", "visit_date"]
        )
        by_id = {row["id"]: row for row in r["rows"]}
        self.assertEqual(by_id["INC-01"]["status"], "covered")
        self.assertIn("anc_result", by_id["INC-01"]["matched_fields"])
        self.assertEqual(by_id["INC-02"]["status"], "covered")
        self.assertEqual(by_id["EXC-01"]["status"], "missing")
        self.assertEqual(r["summary"]["covered"], 2)
        self.assertEqual(r["summary"]["missing"], 1)
        self.assertEqual(r["stale"], [])

    def test_stale_after_amendment(self):
        current = self._criteria()
        previous = [
            {"id": "INC-01", "raw_text": "ANC >= 1.0 K/uL"},
            {"id": "INC-09", "raw_text": "Removed criterion"},
        ]
        r = trace_criteria(current, ["anc_result"], previous_criteria=previous)
        kinds = {(s["id"], s["change"]) for s in r["stale"]}
        self.assertIn(("INC-09", "removed"), kinds)
        self.assertIn(("INC-01", "changed"), kinds)


class AdaptiveTests(unittest.TestCase):
    def test_obf_textbook(self):
        o = group_sequential([0.5, 1.0], 0.05, "obf")["looks"]
        self.assertAlmostEqual(o[0]["z_efficacy"], 2.76, delta=0.05)
        self.assertAlmostEqual(o[1]["z_efficacy"], 2.00, delta=0.05)
        self.assertAlmostEqual(o[1]["alpha_spent"], 0.05, places=3)

    def test_pocock_textbook(self):
        p = group_sequential([0.5, 1.0], 0.05, "pocock")["looks"]
        self.assertAlmostEqual(p[0]["z_efficacy"], 2.16, delta=0.05)
        self.assertAlmostEqual(p[1]["z_efficacy"], 2.24, delta=0.05)

    def test_requires_final_look(self):
        with self.assertRaises(ValueError):
            group_sequential([0.5], 0.05, "obf")


class ConsentTests(unittest.TestCase):
    def test_jargon_and_length(self):
        c = check_consent(
            "You will be randomized to receive the drug or placebo. "
            "Pharmacokinetics will be studied with many blood samples drawn "
            "over several very long and completely unnecessary extra words here."
        )
        terms = {h["term"] for h in c["jargon_hits"]}
        self.assertIn("randomized", terms)
        self.assertIn("placebo", terms)
        self.assertEqual(len(c["long_sentences"]), 1)
        self.assertLess(c["score"], 100)
        self.assertGreaterEqual(c["score"], 0)
        plain = check_consent("You get the drug by vein. We watch for side effects.")
        self.assertEqual(plain["score"], 100)

    def test_overlapping_terms_count_once(self):
        c = check_consent("Report a serious adverse event at once.")
        terms = {h["term"] for h in c["jargon_hits"]}
        self.assertIn("serious adverse event", terms)
        self.assertNotIn("adverse event", terms)
        self.assertEqual(c["score"], 97)


if __name__ == "__main__":
    unittest.main()
