"""TrialNexus smoke tests. Stdlib only (unittest). Run from project root:

python -m unittest discover -s tests -v
"""

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.agents.cohort_matcher import evaluate_cohort  # noqa: E402
from backend.agents.protocol_auditor import parse_protocol  # noqa: E402
from backend.agents.safety_triage import triage_records  # noqa: E402
from backend.agents.site_scout import score_sites  # noqa: E402
from backend.database import (  # noqa: E402
    get_protocol,
    get_schema_version,
    init_db,
    insert_patient_evaluation,
    insert_protocol,
    insert_safety_query,
    list_patient_evaluations,
    list_safety_queries,
    list_sites,
    table_counts,
    upsert_site,
)
from backend.router import ZeroCostRouter  # noqa: E402

PROTOCOL_FILE = ROOT / "data" / "raw" / "protocols" / "protocol_oncology_phase3.txt"
FHIR_DIR = ROOT / "data" / "fhir" / "synthea"


class RouterOfflineTest(unittest.TestCase):
    def test_offline_falls_back_to_deterministic_stub(self):
        router = ZeroCostRouter(base_url="http://127.0.0.1:9/v1")  # unroutable
        out = asyncio.run(router.execute_query("sys", "user"))
        self.assertEqual(out["engine"], "deterministic-local")


class ProtocolParseTest(unittest.TestCase):
    @unittest.skipUnless(PROTOCOL_FILE.exists(), "seed protocol missing")
    def test_sample_protocol_parses(self):
        audit = parse_protocol(PROTOCOL_FILE.read_text())
        self.assertEqual(len(audit["inclusion_criteria"]), 5)
        self.assertEqual(len(audit["exclusion_criteria"]), 4)
        self.assertEqual(audit["inclusion_criteria"][0]["id"], "INC-01")
        self.assertEqual(audit["protocol_metadata"]["phase"], "Phase 3")
        self.assertGreaterEqual(audit["protocol_fragility_index"], 0)
        self.assertLessEqual(audit["protocol_fragility_index"], 100)
        self.assertGreaterEqual(len(audit["operational_flaws"]), 1)  # Day 14/16 clash
        self.assertGreater(audit["amendment_exposure_usd"], 0)
        self.assertIn("Tufts", audit["exposure_basis"])


class DatabaseTest(unittest.TestCase):
    def test_init_and_crud_in_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            init_db(db)
            insert_protocol("P1", "T", "Phase 1", "Ind", "raw text", db)
            self.assertEqual(get_protocol("P1", db)["title"], "T")
            upsert_site(
                {
                    "id": "S1",
                    "name": "N",
                    "country": "C",
                    "city": "City",
                    "historical_activation_days": 60,
                    "regulatory_tier": "Tier 1",
                    "active_competing_trials": 1,
                },
                db,
            )
            self.assertEqual(len(list_sites(db)), 1)
            counts = table_counts(db)
            self.assertEqual(counts["protocols"], 1)
            self.assertEqual(counts["sites"], 1)
            self.assertEqual(get_schema_version(db), 2)
            insert_patient_evaluation(
                {
                    "id": "E1",
                    "protocol_id": "P1",
                    "patient_fhir_id": "PT-1",
                    "eligibility_status": "ELIGIBLE",
                    "inclusion_match_score": 100.0,
                    "exclusion_conflict_count": 0,
                    "rationale": {"a": 1},
                },
                db,
            )
            insert_safety_query(
                {
                    "id": "Q1",
                    "protocol_id": "P1",
                    "patient_id": "PT-1",
                    "reported_term": "Nausea",
                    "suspected_meddra_soc": "GI",
                    "severity": "MILD",
                    "is_sae": False,
                    "reporting_timeline_hours": None,
                    "query_text": "q",
                    "resolution_status": "TRIAGED",
                },
                db,
            )
            self.assertEqual(len(list_patient_evaluations("P1", db_path=db)), 1)
            self.assertEqual(len(list_safety_queries("P1", db_path=db)), 1)
            self.assertEqual(len(list_patient_evaluations("NOPE", db_path=db)), 0)


class CohortTest(unittest.TestCase):
    @unittest.skipUnless(PROTOCOL_FILE.exists(), "seed protocol missing")
    def test_eligible_and_ineligible_patients(self):
        p1 = FHIR_DIR / "patient_001_breast_cancer.json"
        p2 = FHIR_DIR / "patient_002_control.json"
        p3 = FHIR_DIR / "patient_003_review.json"
        if not (p1.exists() and p2.exists() and p3.exists()):
            self.skipTest("seed FHIR bundles missing")
        audit = parse_protocol(PROTOCOL_FILE.read_text())
        criteria = {
            "inclusion_criteria": audit["inclusion_criteria"],
            "exclusion_criteria": audit["exclusion_criteria"],
        }
        bundles = [
            json.loads(p1.read_text()),
            json.loads(p2.read_text()),
            json.loads(p3.read_text()),
        ]
        res = evaluate_cohort(criteria, bundles)["matching_results"]
        by_id = {r["patient_id"]: r for r in res}
        self.assertEqual(by_id["patient-001"]["overall_status"], "ELIGIBLE")
        self.assertEqual(by_id["patient-001"]["match_percentage"], 100.0)
        self.assertEqual(by_id["patient-002"]["overall_status"], "INELIGIBLE")
        self.assertTrue(
            any(not e["passed"] for e in by_id["patient-002"]["inclusion_evaluations"])
        )
        self.assertTrue(
            any(e["triggered"] for e in by_id["patient-002"]["exclusion_evaluations"])
        )
        self.assertEqual(by_id["patient-003"]["overall_status"], "REVIEW_REQUIRED")
        self.assertGreaterEqual(len(by_id["patient-003"]["physician_action_items"]), 2)
        exc02 = [
            e
            for e in by_id["patient-003"]["exclusion_evaluations"]
            if e["criterion_id"] == "EXC-02"
        ][0]
        self.assertFalse(exc02["triggered"])  # negated brain note is not evidence


class SiteSafetyTest(unittest.TestCase):
    def test_site_scoring_and_triage(self):
        sites = [
            {
                "id": "SITE-001",
                "name": "A",
                "country": "USA",
                "historical_activation_days": 75,
                "regulatory_tier": "Tier 1",
                "active_competing_trials": 3,
                "past_accrual_per_month": 2.8,
                "staff_capacity_score": 90,
            },
            {
                "id": "SITE-002",
                "name": "B",
                "country": "India",
                "historical_activation_days": 140,
                "regulatory_tier": "Tier 3",
                "active_competing_trials": 7,
                "past_accrual_per_month": 1.2,
                "staff_capacity_score": 60,
            },
        ]
        out = score_sites(sites, 450)
        recs = {s["site_id"]: s["recommendation"] for s in out["evaluated_sites"]}
        self.assertEqual(recs["SITE-001"], "GO")
        self.assertEqual(recs["SITE-002"], "NO-GO")
        self.assertEqual(out["portfolio_summary"]["total_sites_analyzed"], 2)

        triaged = triage_records(
            [
                {
                    "discrepancy_id": "D1",
                    "patient_id": "P",
                    "reported_term": "Febrile neutropenia with inpatient hospitalization",
                    "severity": "SEVERE",
                    "unexpected": True,
                },
                {
                    "discrepancy_id": "D2",
                    "patient_id": "P",
                    "reported_term": "Mild nausea post-infusion",
                    "severity": "MILD",
                },
            ]
        )["triaged_records"]
        self.assertTrue(triaged[0]["is_sae"])
        self.assertTrue(triaged[0]["regulatory_alert_required"])
        self.assertEqual(triaged[0]["reporting_deadline_hours"], 360)
        self.assertFalse(triaged[1]["is_sae"])
        self.assertFalse(triaged[1]["regulatory_alert_required"])


class KRITest(unittest.TestCase):
    def test_thresholds(self):
        from backend.agents.kri_monitor import portfolio_kris

        rows = {
            "GOOD": [
                {
                    "month": "2025-05",
                    "enrolled": 3,
                    "screened": 4,
                    "open_queries": 3,
                    "deviations": 1,
                    "sae": 0,
                }
            ],
            "BAD": [
                {
                    "month": "2025-05",
                    "enrolled": 0,
                    "screened": 2,
                    "open_queries": 8,
                    "deviations": 5,
                    "sae": 1,
                }
            ],
        }
        r = portfolio_kris(rows, {"GOOD": 3, "BAD": 3})
        by_id = {s["site_id"]: s for s in r["sites"]}
        self.assertEqual(by_id["GOOD"]["worst"], "ok")
        self.assertEqual(by_id["BAD"]["worst"], "alert")
        self.assertIn("BAD", r["alert_site_ids"])
        self.assertNotIn("GOOD", r["alert_site_ids"])


class FinderTest(unittest.TestCase):
    def test_ranking_prefers_right_trial(self):
        from backend.agents.trial_finder import rank_trials

        specs = [
            ("PROT-TNX-001", "protocol_oncology_phase3.txt"),
            ("PROT-TNX-002", "protocol_breast_phase2.txt"),
            ("PROT-TNX-003", "protocol_diabetes_phase2.txt"),
        ]
        protocols = []
        for pid, fname in specs:
            f = PROTOCOL_FILE.parent / fname
            if not f.exists():
                self.skipTest("seed protocols missing")
            a = parse_protocol(f.read_text())
            protocols.append(
                {
                    "id": pid,
                    "title": pid,
                    "phase": "",
                    "criteria": {
                        "inclusion_criteria": a["inclusion_criteria"],
                        "exclusion_criteria": a["exclusion_criteria"],
                    },
                }
            )
        b004 = json.loads((FHIR_DIR / "patient_004_her2.json").read_text())
        r004 = rank_trials(b004, protocols)
        self.assertEqual(len(r004["ranked"]), 3)
        self.assertEqual(r004["ranked"][0]["protocol_id"], "PROT-TNX-002")
        self.assertEqual(r004["ranked"][0]["status"], "ELIGIBLE")
        b005 = json.loads((FHIR_DIR / "patient_005_diabetes.json").read_text())
        r005 = rank_trials(b005, protocols)
        self.assertEqual(r005["ranked"][0]["protocol_id"], "PROT-TNX-003")
        self.assertEqual(r005["ranked"][0]["status"], "ELIGIBLE")


class ExternalControlTest(unittest.TestCase):
    def test_pool_grows_with_relaxation(self):
        from backend.agents.external_control import build_external_control

        if not PROTOCOL_FILE.exists():
            self.skipTest("seed protocol missing")
        a = parse_protocol(PROTOCOL_FILE.read_text())
        crit = {
            "inclusion_criteria": a["inclusion_criteria"],
            "exclusion_criteria": a["exclusion_criteria"],
        }
        bundles = []
        for f in sorted(FHIR_DIR.glob("*.json")):
            bundles.append(json.loads(f.read_text()))
        self.assertGreaterEqual(len(bundles), 5)
        r = build_external_control(crit, bundles, ["INC-04", "EXC-01"])
        self.assertEqual(
            {p["patient_id"] for p in r["pool"]}, {"patient-001", "patient-002"}
        )
        self.assertEqual(len(r["near_miss"]), 3)
        self.assertIn("INC-04", r["methods_note"])
        self.assertIn("race", r["comparability"]["pool_mix"])


class StructureExportTest(unittest.TestCase):
    @unittest.skipUnless(PROTOCOL_FILE.exists(), "seed protocol missing")
    def test_structure_package(self):
        from backend.agents.structured_export import build_structure

        raw = PROTOCOL_FILE.read_text()
        s = build_structure(parse_protocol(raw), "PROT-TNX-001", raw)
        self.assertIn("M11", s["m11Mapping"])
        self.assertEqual(len(s["eligibility"]["inclusion"]), 5)
        self.assertEqual(len(s["eligibility"]["exclusion"]), 4)
        self.assertEqual(s["schedule"]["visit_days"], [1, 14, 16])
        self.assertEqual(s["study"]["id"], "PROT-TNX-001")


class BurdenTest(unittest.TestCase):
    @unittest.skipUnless(PROTOCOL_FILE.exists(), "seed protocol missing")
    def test_seed_burden(self):
        from backend.agents.burden_scorer import score_burden

        b = score_burden(PROTOCOL_FILE.read_text())
        scores = {v["day"]: v["score"] for v in b["visits"]}
        self.assertEqual(scores, {"1": 18, "14": 10, "16": 3})
        self.assertEqual(b["convertible_pct"], 33.3)
        self.assertTrue(b["verdict"].startswith("High"))


class StartupTrackerTest(unittest.TestCase):
    def test_flags_and_advance_in_temp_copy(self):
        import tempfile

        from backend.agents.startup_tracker import startup_report
        from backend.database import list_startup, upsert_startup_site

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            init_db(db)
            upsert_startup_site("S1", "identified", day="2025-01-01", db_path=db)
            upsert_startup_site("S1", "feasibility", day="2025-02-01", db_path=db)
            upsert_startup_site("S2", "activated", day="2025-05-01", db_path=db)
            r = startup_report(list_startup(db), [], today="2026-01-01")
            self.assertIn("S1", r["flagged_site_ids"])
            self.assertNotIn("S2", r["flagged_site_ids"])
            upsert_startup_site("S1", "contract", day="2026-01-01", db_path=db)
            r2 = startup_report(list_startup(db), [], today="2026-01-01")
            row = [s for s in r2["sites"] if s["site_id"] == "S1"][0]
            self.assertEqual(row["stage"], "contract")


class LiveLookupTest(unittest.TestCase):
    def test_ctgov_lookup_never_crashes(self):
        import tempfile
        from unittest import mock

        from backend.agents import site_scout

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(site_scout, "CACHE", Path(tmp) / "cache.json"):
                r = site_scout.fetch_ctgov_competitors(
                    "xyz-no-such-condition-123", "Atlantis", timeout=6.0
                )
        self.assertIn(r["source"], ("live", "cache", "offline-fallback"))
        self.assertIsInstance(r["count"], int)
        self.assertGreaterEqual(r["count"], 0)


class DiversityTest(unittest.TestCase):
    def test_seed_cohort_mix(self):
        from backend.agents.diversity_planner import plan_diversity

        bundles = [
            json.loads((FHIR_DIR / f).read_text())
            for f in (
                "patient_001_breast_cancer.json",
                "patient_002_control.json",
                "patient_003_review.json",
            )
        ]
        r = plan_diversity(bundles)
        self.assertEqual(r["n"], 3)
        by = {d: {x["group"]: x for x in rows} for d, rows in r["dimensions"].items()}
        self.assertEqual(by["sex"]["female"]["n"], 2)
        self.assertEqual(by["sex"]["male"]["n"], 1)
        self.assertEqual(by["race"]["White"]["n"], 1)
        self.assertEqual(by["race"]["Asian"]["n"], 1)
        self.assertEqual(by["race"]["Black or African American"]["n"], 1)
        self.assertEqual(by["ethnicity"]["Hispanic or Latino"]["n"], 1)
        self.assertGreaterEqual(len(r["focus_areas"]), 1)
        self.assertIn(r["overall_status"], ("ready", "watch", "needs-work"))


class StaticUITest(unittest.TestCase):
    def test_frontend_files_present_and_wired(self):
        fe = ROOT / "frontend"
        for name in ("index.html", "styles.css", "app.js"):
            self.assertTrue((fe / name).exists(), f"missing frontend/{name}")
        html = (fe / "index.html").read_text()
        for marker in (
            "app.js",
            "styles.css",
            "tab-audit",
            "tab-sites",
            "tab-cohort",
            "tab-safety",
            "snapshot",
            "stepper",
            "tab-startup",
            "tab-diversity",
            "tab-history",
            "tab-monitoring",
            "tab-finder",
            "tab-external",
        ):
            self.assertIn(marker, html)
        app_src = (ROOT / "backend" / "app.py").read_text()
        routes_src = "".join(
            p.read_text() for p in (ROOT / "backend" / "routes").glob("*.py")
        )
        src = app_src + routes_src
        self.assertIn("StaticFiles", src)
        self.assertIn("/api/snapshot", src)
        self.assertIn("/api/demo-data", src)


if __name__ == "__main__":
    unittest.main()
