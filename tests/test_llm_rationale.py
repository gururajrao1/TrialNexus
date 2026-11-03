"""Track 5 tests: LLM rationale annotations fail closed to rules."""

import unittest

from backend.agents.llm_rationale import (
    annotate_results,
    build_prompt,
    verify_response,
)


def _inc(passed=True, evidence="ANC 1.8 K/uL on Day 1 labs"):
    return {
        "criterion_id": "INC-01",
        "raw_text": "ANC >= 1.5",
        "passed": passed,
        "missing_data": False,
        "clinical_evidence_found": evidence,
    }


def _agree(evidence):
    return {
        "rationale": "Counts clear the bar.",
        "quotes": [evidence],
        "verdict": "met",
    }


class LlmRationaleTests(unittest.TestCase):
    def test_valid_agreeing_annotation(self):
        ev = _inc()["clinical_evidence_found"]
        out = annotate_results(
            {"inclusion_evaluations": [_inc()], "exclusion_evaluations": []},
            lambda _s, _u: _agree(ev),
        )
        got = out["inclusion_evaluations"][0]
        self.assertEqual(got["llm_rationale"]["text"], "Counts clear the bar.")
        self.assertIsNone(got["llm_warning"])
        self.assertTrue(got["llm_rationale"]["verdict_agrees"])

    def test_verdict_mismatch_rejected(self):
        ev = _inc()["clinical_evidence_found"]
        bad = dict(_agree(ev))
        bad["verdict"] = "not_met"
        out = annotate_results(
            {"inclusion_evaluations": [_inc()], "exclusion_evaluations": []},
            lambda _s, _u: bad,
        )
        got = out["inclusion_evaluations"][0]
        self.assertIsNone(got["llm_rationale"])
        self.assertEqual(got["llm_warning"], "verdict_mismatch")

    def test_nonverbatim_quote_rejected(self):
        bad = {"rationale": "Fine.", "quotes": ["invented text"], "verdict": "met"}
        out = annotate_results(
            {"inclusion_evaluations": [_inc()], "exclusion_evaluations": []},
            lambda _s, _u: bad,
        )
        got = out["inclusion_evaluations"][0]
        self.assertIsNone(got["llm_rationale"])
        self.assertEqual(got["llm_warning"], "untrusted")

    def test_malformed_rejected(self):
        for bad in (None, "text", {"rationale": "", "quotes": [], "verdict": "met"}):
            out = annotate_results(
                {"inclusion_evaluations": [_inc()], "exclusion_evaluations": []},
                lambda _s, _u: bad,
            )
            got = out["inclusion_evaluations"][0]
            self.assertIsNone(got["llm_rationale"])
            self.assertEqual(got["llm_warning"], "untrusted")

    def test_model_error_fails_closed(self):
        def boom(_s, _u):
            raise RuntimeError("no route")

        out = annotate_results(
            {"inclusion_evaluations": [_inc()], "exclusion_evaluations": []},
            boom,
        )
        got = out["inclusion_evaluations"][0]
        self.assertIsNone(got["llm_rationale"])
        self.assertEqual(got["llm_warning"], "untrusted")

    def test_disabled_layer(self):
        out = annotate_results(
            {"inclusion_evaluations": [_inc()], "exclusion_evaluations": []},
            None,
        )
        got = out["inclusion_evaluations"][0]
        self.assertIsNone(got["llm_rationale"])
        self.assertEqual(got["llm_warning"], "llm_disabled")
        # Deterministic verdict untouched.
        self.assertTrue(got["passed"])

    def test_top_k_cap_shared(self):
        evals = [_inc(evidence=f"lab value {i}") for i in range(5)]
        out = annotate_results(
            {
                "inclusion_evaluations": evals[:3],
                "exclusion_evaluations": [
                    {**e, "passed": True, "triggered": False} for e in evals[3:]
                ],
            },
            lambda _s, u: {
                "rationale": "ok",
                "quotes": ["lab value"],
                "verdict": "met",
            },
            max_criteria=2,
        )
        warnings = [
            e["llm_warning"]
            for e in out["inclusion_evaluations"] + out["exclusion_evaluations"]
        ]
        self.assertEqual(warnings.count("llm_skipped_top_k"), 3)
        self.assertEqual(
            sum(1 for e in out["inclusion_evaluations"] if e["llm_rationale"]), 2
        )

    def test_long_rationale_truncated(self):
        r, w = verify_response(
            {
                "rationale": " ".join(["word"] * 200),
                "quotes": ["ANC"],
                "verdict": "met",
            },
            "ANC 1.8",
            True,
        )
        self.assertIsNone(w)
        self.assertTrue(r["truncated"])
        self.assertEqual(len(r["text"].split()), 150)

    def test_prompt_states_verdict(self):
        p = build_prompt("INC-01", "ANC >= 1.5", "ANC 1.8", True)
        self.assertIn("deterministic outcome: met", p)
        self.assertIn("ANC 1.8", p)


if __name__ == "__main__":
    unittest.main()
