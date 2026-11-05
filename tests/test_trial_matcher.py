"""Trial matcher tests: parse, split, explain, rank, offline. No network."""

import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.agents import trial_matcher
from backend.agents.trial_matcher import (
    _distill,
    explain_criterion,
    match_description,
    match_trials,
    parse_study,
    referral_letter,
    screening_questions,
    search_ctgov,
    snapshot_lines,
    split_eligibility,
    travel_check,
)

CRITERIA = """Inclusion Criteria:
1. Age 18 years or older with EGFR-mutant lung adenocarcinoma
2. Prior osimertinib treatment with documented progression
3. ECOG performance status 0 or 1

Exclusion Criteria:
1. Untreated symptomatic brain metastases
2. Prior treatment with amivantamab"""


def _study(
    nct="NCT00000001",
    title="EGFR lung cancer study",
    conditions=("Non-Small Cell Lung Cancer",),
    summary="A study of a new drug for EGFR-mutant lung cancer.",
    eligibility=CRITERIA,
    status="RECRUITING",
    phase=("Phase 2",),
):
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": title},
            "statusModule": {"overallStatus": status},
            "conditionsModule": {"conditions": list(conditions)},
            "designModule": {"phases": list(phase)},
            "descriptionModule": {"briefSummary": summary},
            "eligibilityModule": {
                "eligibilityCriteria": eligibility,
                "sex": "ALL",
                "minimumAge": "18 Years",
                "maximumAge": "",
            },
            "contactsLocationsModule": {
                "locations": [
                    {
                        "city": "Boston",
                        "state": "Massachusetts",
                        "country": "United States",
                    }
                ]
            },
        }
    }


DESC = (
    "66-year-old woman, EGFR-mutant lung adenocarcinoma, "
    "prior osimertinib with progression, ECOG 1"
)


class ParseTests(unittest.TestCase):
    def test_parse_slims_record(self):
        s = parse_study(_study())
        self.assertEqual(s["nct_id"], "NCT00000001")
        self.assertIn("Non-Small Cell Lung Cancer", s["conditions"])
        self.assertEqual(s["locations"], ["Boston, Massachusetts, United States"])
        self.assertTrue(s["url"].endswith("NCT00000001"))

    def test_parse_empty_record(self):
        s = parse_study({})
        self.assertEqual(s["nct_id"], "")
        self.assertEqual(s["locations"], [])

    def test_split_inclusion_exclusion(self):
        parts = split_eligibility(CRITERIA)
        self.assertEqual(len(parts["inclusion"]), 3)
        self.assertEqual(len(parts["exclusion"]), 2)
        self.assertTrue(parts["inclusion"][0].startswith("Age 18"))

    def test_split_empty(self):
        self.assertEqual(split_eligibility(""), {"inclusion": [], "exclusion": []})

    def test_bare_leading_number_survives(self):
        parts = split_eligibility("Inclusion Criteria:\n18 years or older")
        self.assertEqual(parts["inclusion"], ["18 years or older"])

    def test_header_with_trailing_text_dropped(self):
        parts = split_eligibility(
            "Inclusion Criteria: Initial\nAdults with lung cancer"
        )
        self.assertEqual(parts["inclusion"], ["Adults with lung cancer"])


class ExplainTests(unittest.TestCase):
    def test_likely_met(self):
        r = explain_criterion(
            "Prior osimertinib treatment with documented progression", DESC
        )
        self.assertEqual(r["verdict"], "likely met")
        self.assertIn("osimertinib", r["plain"])

    def test_number_goes_to_team(self):
        r = explain_criterion("Age 18 years or older", DESC)
        self.assertEqual(r["verdict"], "check with the team")

    def test_exclusion_overlap_conflicts(self):
        r = explain_criterion(
            "Symptomatic brain metastases",
            "lung cancer with symptomatic brain metastases",
            exclusion=True,
        )
        self.assertEqual(r["verdict"], "possible conflict")

    def test_unknown_goes_to_team(self):
        r = explain_criterion("Adequate hepatic function per labs", DESC)
        self.assertEqual(r["verdict"], "check with the team")


def _echo_model(log):
    """Stub model: valid drafts for notes; rerank must be overridden per test."""

    def call(system, user):
        log.append(system)
        if system == trial_matcher.RERANK_SYSTEM:
            raise AssertionError("rerank stub not provided")
        crit = re.search(r"criterion: ([^\n]+)", user)
        verdict = re.search(r"deterministic outcome: ([^\n]+)", user)
        text = crit.group(1) if crit else ""
        word = next((w for w in text.split() if len(w) >= 4), text[:12])
        return {
            "plain": "Model says: " + text[:60],
            "quotes": [word],
            "verdict": verdict.group(1).strip() if verdict else "",
        }

    return call


class ModelLayerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(
            trial_matcher, "REALWORLD_CACHE", Path(self.tmp.name) / "cache.json"
        )
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def _stub(self, studies):
        def http_get(params, timeout):
            return {"studies": studies, "totalCount": len(studies)}

        return http_get

    def test_draft_accepted(self):
        log = []
        note = explain_criterion(
            "Prior osimertinib treatment with documented progression",
            DESC,
            call_model=_echo_model(log),
            budget=[5],
        )
        self.assertTrue(note["draft"])
        self.assertTrue(note["plain"].startswith("Model says:"))
        self.assertNotIn("model_warning", note)
        self.assertEqual(len(log), 1)

    def test_verdict_mismatch_rejected(self):
        def bad(system, user):
            return {
                "plain": "All good here.",
                "quotes": ["osimertinib"],
                "verdict": "wrong verdict",
            }

        note = explain_criterion(
            "Prior osimertinib treatment with documented progression",
            DESC,
            call_model=bad,
            budget=[5],
        )
        self.assertFalse(note["draft"])
        self.assertEqual(note["model_warning"], "model_verdict_mismatch")

    def test_model_exception_falls_back(self):
        def boom(system, user):
            raise ConnectionError("down")

        note = explain_criterion(
            "Prior osimertinib treatment", DESC, call_model=boom, budget=[5]
        )
        self.assertFalse(note["draft"])
        self.assertEqual(note["model_warning"], "model_untrusted")

    def test_budget_cap_shared(self):
        res = match_trials(
            DESC,
            max_trials=1,
            http_get=self._stub([_study()]),
            call_model=_echo_model([]),
            model_budget=1,
        )
        drafts = sum(1 for t in res["trials"] for n in t["notes"] if n.get("draft"))
        self.assertEqual(drafts, 1)
        self.assertIn("model_skipped_budget", res["model_warnings"])
        self.assertEqual(res["explain_source"], "model-assisted")

    def test_disabled_layer_is_template(self):
        res = match_trials(DESC, max_trials=1, http_get=self._stub([_study()]))
        self.assertEqual(res["explain_source"], "template")
        self.assertFalse(res["reranked"])
        self.assertEqual(res["model_warnings"], [])

    def _two(self):
        other = _study(
            nct="NCT00000002",
            title="EGFR lung cancer study two",
            conditions=("Non-Small Cell Lung Cancer",),
            summary="Second EGFR lung cancer study.",
            eligibility="Inclusion Criteria:\nAdults with lung cancer",
        )
        return [_study(), other]

    def _rerank_stub(self, order, reasons):
        def call(system, user):
            if system == trial_matcher.RERANK_SYSTEM:
                return {"order": order, "reasons": reasons}
            return _echo_model([])(system, user)

        return call

    def test_rerank_success(self):
        studies = self._two()
        call = self._rerank_stub(
            ["NCT00000002", "NCT00000001"],
            {
                "NCT00000002": "Ranked first because 'EGFR lung cancer study two' fits best.",
                "NCT00000001": "Second: 'EGFR lung cancer study' is also relevant.",
            },
        )
        res = match_trials(
            DESC,
            max_trials=2,
            http_get=self._stub(studies),
            call_model=call,
            model_budget=20,
            allow_rerank=True,
        )
        self.assertTrue(res["reranked"])
        self.assertEqual(
            [t["nct_id"] for t in res["trials"]], ["NCT00000002", "NCT00000001"]
        )
        self.assertIn("rerank_reason", res["trials"][0])

    def test_rerank_bad_permutation_rejected(self):
        studies = self._two()
        call = self._rerank_stub(
            ["NCT00000001"], {"NCT00000001": "Only one 'EGFR lung cancer study'."}
        )
        res = match_trials(
            DESC,
            max_trials=2,
            http_get=self._stub(studies),
            call_model=call,
            model_budget=20,
            allow_rerank=True,
        )
        self.assertFalse(res["reranked"])
        self.assertIn("model_rerank_rejected", res["model_warnings"])

    def test_rerank_reason_without_quote_rejected(self):
        studies = self._two()
        call = self._rerank_stub(
            ["NCT00000002", "NCT00000001"],
            {"NCT00000002": "Trust me.", "NCT00000001": "Also trust me."},
        )
        res = match_trials(
            DESC,
            max_trials=2,
            http_get=self._stub(studies),
            call_model=call,
            model_budget=20,
            allow_rerank=True,
        )
        self.assertFalse(res["reranked"])
        self.assertIn("model_rerank_rejected", res["model_warnings"])


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(
            trial_matcher, "REALWORLD_CACHE", Path(self.tmp.name) / "cache.json"
        )
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def _stub(self, studies):
        def http_get(params, timeout):
            self.assertIn("query.term", params)
            return {"studies": studies, "totalCount": len(studies)}

        return http_get

    def test_ranking_prefers_relevant_study(self):
        other = _study(
            nct="NCT00000002",
            title="Diabetes foot ulcer study",
            conditions=("Diabetic Foot Ulcer",),
            summary="Wound care for diabetic foot ulcers.",
            eligibility="Inclusion Criteria:\n1. Adults with foot ulcers",
        )
        res = match_trials(DESC, max_trials=2, http_get=self._stub([other, _study()]))
        self.assertEqual(res["source"], "live")
        self.assertEqual(res["trials"][0]["nct_id"], "NCT00000001")
        self.assertGreater(res["trials"][0]["score"], res["trials"][1]["score"])

    def test_verdict_never_claims_eligible(self):
        res = match_trials(DESC, max_trials=1, http_get=self._stub([_study()]))
        t = res["trials"][0]
        self.assertNotIn("eligible", t["verdict"].lower().replace("eligibility", ""))
        self.assertIn("study team", t["summary"])
        self.assertIn("not medical advice", res["disclaimer"])

    def test_offline_fallback(self):
        def boom(params, timeout):
            raise ConnectionError("down")

        res = match_trials(DESC, http_get=boom)
        self.assertEqual(res["source"], "offline-fallback")
        self.assertEqual(res["trials"], [])

    def test_cache_reused_when_network_dies(self):
        res1 = match_trials(DESC, max_trials=1, http_get=self._stub([_study()]))
        self.assertEqual(res1["source"], "live")

        def boom(params, timeout):
            raise ConnectionError("down")

        res2 = match_trials(DESC, max_trials=1, http_get=boom)
        self.assertEqual(res2["source"], "cache")
        self.assertEqual(len(res2["trials"]), 1)

    def test_empty_description_rejected(self):
        with self.assertRaises(ValueError):
            match_trials("   ", http_get=self._stub([]))

    def test_search_ctgov_empty_query(self):
        out = search_ctgov("   ", http_get=self._stub([]))
        self.assertEqual(out["studies"], [])

    def test_distill_drops_noise(self):
        self.assertEqual(
            _distill(DESC),
            [
                "egfr",
                "mutation",
                "lung",
                "adenocarcinoma",
                "prior",
                "osimertinib",
                "progression",
                "ecog",
            ],
        )

    def test_ladder_backs_off_to_shorter_terms(self):
        calls = []

        def http_get(params, timeout):
            calls.append(params["query.term"])
            if len(calls) == 1:
                return {"studies": [], "totalCount": 0}
            return {"studies": [_study()], "totalCount": 1}

        res = match_trials(DESC, max_trials=1, http_get=http_get)
        self.assertEqual(res["source"], "live")
        self.assertEqual(len(calls), 2)
        self.assertLess(len(calls[1].split()), len(calls[0].split()))

    def test_widened_when_location_dropped(self):
        def http_get(params, timeout):
            if "query.locn" in params:
                return {"studies": [], "totalCount": 0}
            return {"studies": [_study()], "totalCount": 1}

        res = match_trials(DESC, location="Boston", max_trials=1, http_get=http_get)
        self.assertTrue(res["widened"])
        self.assertEqual(res["trials"][0]["nct_id"], "NCT00000001")


class ArtifactsTests(unittest.TestCase):
    def test_travel_nearby(self):
        study = {
            "locations": [
                "Boston, Massachusetts, United States",
                "Austin, Texas, United States",
            ]
        }
        out = travel_check(study, "Boston")
        self.assertEqual(out["nearby"], ["Boston, Massachusetts, United States"])
        self.assertIn("1 of 2", out["note"])

    def test_travel_no_match(self):
        study = {"locations": ["Austin, Texas, United States"]}
        out = travel_check(study, "Boston")
        self.assertEqual(out["nearby"], [])
        self.assertIn("No listed site", out["note"])

    def test_travel_no_location(self):
        out = travel_check({"locations": ["Austin, Texas"]}, "")
        self.assertIn("add your city", out["note"])

    def test_snapshot_three_facts(self):
        study = parse_study(_study())
        snap = snapshot_lines(study)
        self.assertEqual(len(snap), 3)
        self.assertTrue(any("Boston" in s for s in snap))

    def test_referral_letter_shape(self):
        study = {
            **parse_study(_study()),
            "notes": [{"verdict": "likely met", "plain": "ok", "quote": "q"}],
        }
        out = referral_letter(study, DESC, "Jane")
        self.assertIn("NCT00000001", out["letter"])
        self.assertIn("Jane", out["letter"])
        self.assertIn("matching aid", out["letter"])

    def test_screening_questions_split(self):
        out = screening_questions(parse_study(_study()))
        kinds = [q["kind"] for q in out["questions"]]
        self.assertIn("inclusion", kinds)
        self.assertIn("exclusion", kinds)
        self.assertTrue(all(q["question"] for q in out["questions"]))


class TrialGptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(
            trial_matcher, "REALWORLD_CACHE", Path(self.tmp.name) / "cache.json"
        )
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_synonym_overlap_likely_met(self):
        note = explain_criterion(
            "Patients with EGFR mutation positive tumors", "EGFR-mutant lung cancer"
        )
        self.assertEqual(note["verdict"], "likely met")
        self.assertIn("mutation", note["matched_terms"])

    def test_pregnancy_na_for_male(self):
        note = explain_criterion(
            "Pregnant or breastfeeding women are excluded",
            "58-year-old man with diabetes",
            exclusion=True,
        )
        self.assertEqual(note["verdict"], "not applicable")

    def test_pregnancy_not_na_for_female(self):
        note = explain_criterion(
            "Pregnant or breastfeeding women are excluded",
            "58-year-old woman with diabetes",
            exclusion=True,
        )
        self.assertNotEqual(note["verdict"], "not applicable")

    def test_na_sits_out_scoring(self):
        raw = _study(
            eligibility="Inclusion Criteria:\nAdults with lung cancer\n\n"
            "Exclusion Criteria:\nPregnant or breastfeeding"
        )
        res = match_description(parse_study(raw), "58-year-old man with diabetes")
        self.assertEqual(len(res["notes"]), 2)
        self.assertEqual(res["n_checked"], 1)
        self.assertEqual(
            [n["verdict"] for n in res["notes"]].count("not applicable"), 1
        )

    def test_conflict_penalizes_score(self):
        clean = _study(eligibility="Inclusion Criteria:\nAdults with lung cancer")
        clash = _study(
            nct="NCT00000009",
            eligibility="Inclusion Criteria:\nAdults with lung cancer\n\n"
            "Exclusion Criteria:\nPrior osimertinib treatment",
        )
        a = match_description(parse_study(clean), DESC)
        b = match_description(parse_study(clash), DESC)
        self.assertLess(b["score"], a["score"])
        self.assertLess(b["exclusion_clear_rate"], 1.0)
        self.assertEqual(b["verdict"], "needs clinician review")

    def test_fields_param_sent(self):
        seen = []

        def http_get(params, timeout):
            seen.append(params)
            return {"studies": [_study()], "totalCount": 1}

        match_trials(DESC, max_trials=1, http_get=http_get)
        self.assertTrue(seen)
        self.assertIn("NCTId", seen[0].get("fields", ""))
        self.assertIn("EligibilityCriteria", seen[0].get("fields", ""))


if __name__ == "__main__":
    unittest.main()
