"""Warning-letter index + cross-check tests (inline fixtures only).

The real letters live in git-ignored data/inbox/, so these tests use small
inline fixtures that exercise the same code paths: metadata extraction,
theme gating, and finding-to-violation ranking.
"""

import tempfile
import unittest
from pathlib import Path

from backend.agents.warning_letters import (
    cross_check,
    load_letters,
    parse_letter,
)

DEVICE_QS = """WARNING LETTER
CMS # 123456

March 4, 2025

Dear Ms. Example:

During an inspection of your firm, investigators determined that your firm
manufactures cardiac catheters. Your devices are adulterated under section
501(h) of the Act, 21 U.S.C. 351(h).

Design Control Violations

1. Failure to establish and maintain procedures for validating the device
design to ensure devices conform to user needs, as required by 21 CFR 820.30.
Your risk management documentation did not address known hazards, and your
risk management report omitted risk control measures for the wire.

2. Failure to establish and maintain CAPA procedures, as required by
21 CFR 820.100. Your CAPA closed with no effectiveness check, and the
corrective action did not prevent recurrence of the wire failures.
"""

PROMO = """WARNING LETTER

Recipient:
Jane Doe
Chief Executive Officer
Example Pharma Inc.
1 Main Street
Boston, MA 02101
United States

Issuing Office:
The Office of Prescription Drug Promotion
United States

Your promotional video is false or misleading because it promotes the drug
for an off-label use. The drug is misbranded under the Act. This
promotional piece overstates efficacy and promotes off-label use to
physicians, and the promotion was never submitted for review.
"""


class ParseLetterTests(unittest.TestCase):
    def test_device_metadata(self):
        letter = parse_letter(DEVICE_QS, "wl-device.txt")
        self.assertEqual(letter["cms"], "123456")
        self.assertEqual(letter["date"], "March 4, 2025")
        self.assertIn("design_control", letter["themes"])
        self.assertIn("capa", letter["themes"])
        self.assertTrue(
            any("21 CFR 820.30" in c for v in letter["violations"] for c in v["cfr"])
        )

    def test_recipient_block_metadata(self):
        letter = parse_letter(PROMO, "wl-promo.txt")
        self.assertEqual(letter["firm"], "Example Pharma")
        self.assertIn("Prescription Drug Promotion", letter["office"])
        self.assertEqual(letter["themes"], ["promotion"])

    def test_empty_text_parses_clean(self):
        letter = parse_letter("", "empty.txt")
        self.assertEqual(letter["themes"], [])
        self.assertEqual(letter["violations"], [])


class PromoCheckTests(unittest.TestCase):
    def test_off_indication_flagged(self):
        from backend.agents.warning_letters import check_promo_draft

        out = check_promo_draft(
            "Our drug cures diabetes and hypertension, ask your doctor",
            "Non-small cell lung cancer",
        )
        self.assertEqual(out["verdict"], "needs review")
        texts = [f["text"] for f in out["flags"]]
        self.assertIn("diabetes", texts)

    def test_clean_copy_passes(self):
        from backend.agents.warning_letters import check_promo_draft

        out = check_promo_draft(
            "A treatment for non-small cell lung cancer", "Non-small cell lung cancer"
        )
        self.assertEqual(out["verdict"], "no lexical flags")


class CrossCheckTests(unittest.TestCase):
    def setUp(self):
        self.letters = [
            parse_letter(DEVICE_QS, "wl-device.txt"),
            parse_letter(PROMO, "wl-promo.txt"),
        ]

    def test_capa_finding_hits_device_letter_first(self):
        hits = cross_check(
            "Site closed a CAPA with no effectiveness check", self.letters
        )
        self.assertTrue(hits)
        self.assertEqual(hits[0]["id"], "wl-device.txt")
        self.assertEqual(hits[0]["suggested_tier"], "major")
        self.assertIn("monitoring", hits[0]["panels"])

    def test_promo_finding_hits_promo_letter_first(self):
        hits = cross_check(
            "Draft promotes the drug off-label to physicians", self.letters
        )
        self.assertTrue(hits)
        self.assertEqual(hits[0]["id"], "wl-promo.txt")

    def test_unrelated_finding_matches_nothing(self):
        hits = cross_check("Sunny weather expected for the site picnic", self.letters)
        self.assertEqual(hits, [])


class LoadLettersTests(unittest.TestCase):
    def test_missing_dir_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_letters(Path(tmp) / "nope"), [])

    def test_loads_txt_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "warning-letter-01.txt").write_text(DEVICE_QS)
            (root / "notes.txt").write_text("not a letter")
            letters = load_letters(root)
            self.assertEqual(len(letters), 1)
            self.assertEqual(letters[0]["id"], "warning-letter-01.txt")


if __name__ == "__main__":
    unittest.main()
