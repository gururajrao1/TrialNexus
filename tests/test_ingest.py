"""Gap-fill tests: PDF ingestion, PubMed lookup, token auth.

Proves the three former known limits stay closed. The PDF builder emits
a minimal uncompressed PDF in-memory so no binary fixture ships.
"""

import os
import tempfile
import unittest
from pathlib import Path

from backend.agents.pdf_ingest import extract_pdf_text
from backend.agents.pubmed import (
    fetch_pubmed,
    parse_esearch_xml,
    parse_esummary_xml,
)
from backend.agents.real_data import (
    fetch_clinvar,
    fetch_drug_label,
    fetch_faers,
    fetch_gene_card,
    fetch_live_studies,
    fetch_recalls,
    genes_in_text,
    parse_civic_gene,
    parse_clinvar_esummary,
    parse_enforcement,
    parse_faers_total,
    parse_label_doc,
    parse_live_studies,
    parse_mygene_hit,
    parse_myvariant_hits,
)
from backend.auth import authorized
from backend.database import (
    delete_protocol,
    get_protocol,
    init_db,
    insert_patient_evaluation,
    insert_protocol,
)

PROTOCOL_SNIPPET = """PROTOCOL TITLE: A Phase III Study of Compound TNX-101 in NSCLC
PHASE: Phase 3
TARGET ENROLLMENT: 450
INCLUSION CRITERIA:
1. Male or female patients aged >= 18 years and <= 75 years.
2. ECOG Performance Status of 0 or 1.
EXCLUSION CRITERIA:
1. Prior treatment with third-generation EGFR tyrosine kinase inhibitors.
"""


def make_pdf_bytes(text: str) -> bytes:
    """Minimal single-page PDF with uncompressed text (pypdf-readable)."""
    safe = text.encode("latin-1", errors="replace").decode("latin-1")
    safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    ops = ["BT /F1 12 Tf 72 720 Td"]
    for i, line in enumerate(safe.splitlines()):
        if i:
            ops.append("0 -14 Td")
        ops.append(f"({line or ' '}) Tj")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
        b" /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += str(off).zfill(10).encode() + b" 00000 n \n"
    out += (
        b"trailer\n<< /Size "
        + str(len(objs) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_at).encode()
        + b"\n%%EOF"
    )
    return bytes(out)


class PdfIngestTests(unittest.TestCase):
    def test_round_trip_keeps_criteria_lines(self):
        pdf = extract_pdf_text(make_pdf_bytes(PROTOCOL_SNIPPET))
        self.assertEqual(pdf["pages"], 1)
        self.assertFalse(pdf["truncated"])
        self.assertIn("aged >= 18 years", pdf["text"])
        self.assertIn("tyrosine kinase inhibitors", pdf["text"])

    def test_non_pdf_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            extract_pdf_text(b"just some text, not a pdf")
        self.assertIn("not a PDF", str(ctx.exception))

    def test_empty_text_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            extract_pdf_text(make_pdf_bytes(""))
        self.assertIn("no extractable text", str(ctx.exception).lower())


ESEARCH_FIXTURE = """<?xml version="1.0"?>
<eSearchResult><Count>2</Count><RetMax>2</RetMax>
<IdList><Id>12345</Id><Id>67890</Id></IdList></eSearchResult>"""

ESUMMARY_FIXTURE = """<?xml version="1.0"?>
<eSummaryResult><DocSum><Id>12345</Id>
<Item Name="Title" Type="String">Hepatotoxicity of kinase inhibitors</Item>
<Item Name="FullJournalName" Type="String">J Clin Oncol</Item>
<Item Name="PubDate" Type="String">2023 Jan</Item>
</DocSum><DocSum><Id>67890</Id>
<Item Name="Title" Type="String">Liver injury review</Item>
<Item Name="FullJournalName" Type="String">Hepatology</Item>
<Item Name="PubDate" Type="String">2022</Item>
</DocSum></eSummaryResult>"""


CLINVAR_FIXTURE = """<?xml version="1.0"?>
<eSummaryResult><DocSum><Id>12345</Id>
<Item Name="VariationName" Type="String">EGFR c.2573T&gt;G (p.Leu858Arg)</Item>
<Item Name="Condition" Type="String">Lung cancer</Item>
<Item Name="ClinicalSignificance" Type="String">Pathogenic</Item>
</DocSum></eSummaryResult>"""


class PubMedTests(unittest.TestCase):
    def test_parsers_offline(self):
        count, pmids = parse_esearch_xml(ESEARCH_FIXTURE)
        self.assertEqual((count, pmids), (2, ["12345", "67890"]))
        cards = parse_esummary_xml(ESUMMARY_FIXTURE)
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]["journal"], "J Clin Oncol")
        self.assertEqual(cards[0]["year"], "2023")
        self.assertEqual(parse_esearch_xml("garbage"), (0, []))
        self.assertEqual(parse_esummary_xml("garbage"), [])

    def test_fetch_never_crashes(self):
        r = fetch_pubmed("EGFR tyrosine kinase inhibitor hepatotoxicity", 2)
        self.assertIn(r["source"], ("live", "cache", "offline-fallback"))
        self.assertIsInstance(r["count"], int)
        self.assertIsInstance(r["articles"], list)
        for a in r["articles"]:
            self.assertIn("pmid", a)


class RealDataTests(unittest.TestCase):
    def test_genes_in_text(self):
        self.assertEqual(
            genes_in_text("EGFR L858R and HER2 amplification, ANC normal"),
            ["EGFR", "ERBB2"],
        )
        self.assertEqual(genes_in_text("no biomarkers mentioned"), [])
        self.assertEqual(genes_in_text("History of MI"), [])

    def test_clinvar_parser_offline(self):
        cards = parse_clinvar_esummary(CLINVAR_FIXTURE)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["id"], "12345")
        self.assertIn("EGFR", cards[0]["variation"])
        self.assertEqual(parse_clinvar_esummary("garbage"), [])

    def test_faers_parser_offline(self):
        self.assertEqual(parse_faers_total('{"meta": {"results": {"total": 42}}}'), 42)
        self.assertEqual(parse_faers_total("garbage"), 0)
        self.assertEqual(parse_faers_total("{}"), 0)

    def test_fetchers_never_crash(self):
        c = fetch_clinvar("EGFR", 1)
        self.assertIn(c["source"], ("live", "cache", "offline-fallback"))
        self.assertIsInstance(c["count"], int)
        self.assertIsInstance(c["variants"], list)
        f = fetch_faers("osimertinib", "Pneumonitis")
        self.assertIn(f["source"], ("live", "cache", "offline-fallback"))
        self.assertIsInstance(f["reports"], int)


class RealWorldWave2Tests(unittest.TestCase):
    def test_gene_parsers_offline(self):
        mg = parse_mygene_hit(
            {
                "hits": [
                    {
                        "symbol": "EGFR",
                        "name": "epidermal growth factor receptor",
                        "summary": "Receptor tyrosine kinase.",
                    }
                ]
            }
        )
        self.assertEqual(mg["symbol"], "EGFR")
        self.assertIn("Receptor", mg["summary"])
        self.assertEqual(
            parse_mygene_hit({}), {"symbol": "", "name": "", "summary": ""}
        )
        cv = parse_civic_gene(
            {"data": {"gene": {"name": "EGFR", "description": "Key driver."}}}
        )
        self.assertEqual(cv["description"], "Key driver.")
        self.assertEqual(
            parse_civic_gene({"data": {}}), {"name": "", "description": ""}
        )
        mv = parse_myvariant_hits(
            {
                "hits": [
                    {
                        "_id": "chr7:g.1A>T",
                        "clinvar": {
                            "clinical_significance": "Pathogenic",
                            "trait": "Lung cancer",
                        },
                    },
                    {"_id": "x"},
                ]
            }
        )
        self.assertEqual(mv[0]["significance"], "Pathogenic")
        self.assertEqual(mv[1]["significance"], "unclassified")
        self.assertEqual(parse_myvariant_hits("garbage"), [])

    def test_label_recall_parsers_offline(self):
        lb = parse_label_doc(
            {
                "results": [
                    {
                        "openfda": {"brand_name": ["ADVIL"]},
                        "boxed_warning": [""],
                        "warnings": ["Do not use."],
                    }
                ]
            }
        )
        self.assertEqual(lb["brand"], "ADVIL")
        self.assertFalse(lb["has_boxed"])
        self.assertTrue(lb["has_warnings"])
        self.assertEqual(
            parse_label_doc({}),
            {
                "brand": "",
                "has_boxed": False,
                "boxed_warning": "",
                "has_warnings": False,
            },
        )
        en = parse_enforcement(
            {
                "meta": {"results": {"total": 2}},
                "results": [
                    {
                        "recall_number": "D-123",
                        "reason_for_recall": "Mislabel",
                        "classification": "Class II",
                        "status": "Ongoing",
                        "recalling_firm": "X",
                    }
                ],
            }
        )
        self.assertEqual(en["count"], 2)
        self.assertEqual(en["latest"]["classification"], "Class II")
        self.assertEqual(parse_enforcement({}), {"count": 0, "latest": {}})

    def test_studies_parser_offline(self):
        st = parse_live_studies(
            {
                "studies": [
                    {
                        "protocolSection": {
                            "identificationModule": {
                                "nctId": "NCT1",
                                "briefTitle": "T",
                            },
                            "statusModule": {"overallStatus": "RECRUITING"},
                            "contactsLocationsModule": {
                                "locations": [
                                    {"city": "Boston", "country": "United States"},
                                    {"city": "Lyon", "country": "France"},
                                ]
                            },
                        }
                    }
                ]
            }
        )
        self.assertEqual(st[0]["nct"], "NCT1")
        self.assertEqual(st[0]["city"], "Boston")
        self.assertEqual(st[0]["n_locations"], 2)
        self.assertEqual(parse_live_studies({}), [])

    def test_wave2_fetchers_never_crash(self):
        g = fetch_gene_card("EGFR")
        self.assertIn(g["sources"]["mygene"], ("live", "cache", "offline-fallback"))
        self.assertIsInstance(g["clinvar"], dict)
        lb = fetch_drug_label("ibuprofen")
        self.assertIn(
            lb.get("source", "offline-fallback"), ("live", "cache", "offline-fallback")
        )
        self.assertIsInstance(lb["has_boxed"], bool)
        rc = fetch_recalls("ibuprofen")
        self.assertIn(
            rc.get("source", "offline-fallback"), ("live", "cache", "offline-fallback")
        )
        self.assertIsInstance(rc["count"], int)
        ls = fetch_live_studies("Non-Small Cell Lung Cancer")
        self.assertIn(ls["source"], ("live", "cache", "offline-fallback"))
        self.assertIsInstance(ls["studies"], list)


class AuthTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("TRIALNEXUS_API_TOKEN")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("TRIALNEXUS_API_TOKEN", None)
        else:
            os.environ["TRIALNEXUS_API_TOKEN"] = self._old

    def test_open_by_default(self):
        os.environ.pop("TRIALNEXUS_API_TOKEN", None)
        self.assertTrue(authorized("/api/snapshot", None))
        self.assertTrue(authorized("/health", None))

    def test_middleware_wiring(self):
        from starlette.testclient import TestClient

        from backend.app import app

        client = TestClient(app, raise_server_exceptions=False)
        os.environ.pop("TRIALNEXUS_API_TOKEN", None)
        self.assertEqual(client.get("/api/snapshot").status_code, 200)
        os.environ["TRIALNEXUS_API_TOKEN"] = "s3cret"
        try:
            denied = client.get("/api/snapshot")
            self.assertEqual(denied.status_code, 401)
            body = denied.json()
            self.assertEqual(body["detail"], "API token required")
            ok = client.get("/api/snapshot", headers={"Authorization": "Bearer s3cret"})
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(client.get("/health").status_code, 200)
        finally:
            os.environ.pop("TRIALNEXUS_API_TOKEN", None)

    def test_guarded_when_set(self):
        os.environ["TRIALNEXUS_API_TOKEN"] = "s3cret"
        self.assertTrue(authorized("/api/snapshot", "Bearer s3cret"))
        self.assertTrue(authorized("/api/snapshot", "bearer s3cret"))
        self.assertFalse(authorized("/api/snapshot", None))
        self.assertFalse(authorized("/api/snapshot", "Bearer wrong"))
        self.assertFalse(authorized("/api/snapshot", "Token s3cret"))
        self.assertTrue(authorized("/", None))
        self.assertTrue(authorized("/health", None))


class DeleteProtocolTests(unittest.TestCase):
    def test_delete_cascades_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            init_db(db)
            insert_protocol("PX", "T", "P1", "I", "raw", db_path=db)
            insert_patient_evaluation(
                {
                    "id": "e1",
                    "protocol_id": "PX",
                    "patient_fhir_id": "p",
                    "eligibility_status": "ELIGIBLE",
                    "inclusion_match_score": 100.0,
                    "exclusion_conflict_count": 0,
                    "rationale": {},
                },
                db_path=db,
            )
            self.assertTrue(delete_protocol("PX", db_path=db))
            self.assertIsNone(get_protocol("PX", db_path=db))
            self.assertFalse(delete_protocol("PX", db_path=db))


if __name__ == "__main__":
    unittest.main()
