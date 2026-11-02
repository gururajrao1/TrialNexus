"""Generate demo/protocol_demo.pdf (stdlib only). Re-run anytime to refresh."""

PROTOCOL_TEXT = """PROTOCOL TITLE: A Phase III Study of Compound TNX-101 in NSCLC
PHASE: Phase 3
TARGET ENROLLMENT: 450
INCLUSION CRITERIA:
1. Male or female patients aged >= 18 years and <= 75 years.
2. ECOG Performance Status of 0 or 1.
3. Absolute neutrophil count >= 1.5 K/uL at screening.
4. Documented EGFR sensitizing mutation by local testing.
EXCLUSION CRITERIA:
1. Prior treatment with third-generation EGFR tyrosine kinase inhibitors.
2. History of interstitial lung disease within 12 months.
3. Pregnant or breastfeeding women.
"""


def make_pdf_bytes(text: str) -> bytes:
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
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
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
        b"trailer\n<< /Size " + str(len(objs) + 1).encode() + b" /Root 1 0 R >>\nstartxref\n" + str(xref_at).encode() + b"\n%%EOF"
    )
    return bytes(out)


if __name__ == "__main__":
    from pathlib import Path

    dest = Path(__file__).parent / "protocol_demo.pdf"
    dest.write_bytes(make_pdf_bytes(PROTOCOL_TEXT))
    print(f"wrote {dest} ({dest.stat().st_size} bytes)")
