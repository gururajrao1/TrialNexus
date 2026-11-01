"""End-to-end problem-statement checks against the running API (stdlib only).

Start the server first:  uvicorn backend.app:app --port 8000
Run from the project root:  python tests/test_e2e_live.py
"""

import base64
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
FAILURES = []


def check(name, cond, detail=""):
    print(
        ("PASS " if cond else "FAIL ")
        + name
        + ((" — " + str(detail)) if detail else "")
    )
    if not cond:
        FAILURES.append(name)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as r:
        return r.status, r.read().decode("utf-8", "ignore")


def post(path, payload, timeout=30):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def delete(path):
    req = urllib.request.Request(BASE + path, method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def make_pdf_bytes(text):
    """Minimal single-page PDF (mirrors tests/test_ingest.py builder)."""
    safe = text.encode("latin-1", errors="replace").decode("latin-1")
    safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    ops = ["BT /F1 12 Tf 72 720 Td"]
    for i, line in enumerate(safe.splitlines()):
        if i:
            ops.append("0 -14 Td")
        ops.append("(%s) Tj" % (line or " "))
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


def wait_for_api():
    for _ in range(30):
        try:
            if get("/health")[0] == 200:
                return True
        except Exception:
            time.sleep(1)
    return False


def main():
    if not wait_for_api():
        print(
            "API not reachable at "
            + BASE
            + " — start it: uvicorn backend.app:app --port 8000"
        )
        return 2
    delete("/api/protocols/PDF-NSCLC-PROTOCOL")  # crash-leftover cleanup
    status, html = get("/")
    check(
        "UI serves with workflow tabs",
        status == 200
        and "stepper" in html
        and "tab-safety" in html
        and "pdfForm" in html
        and "pubmedForm" in html,
    )
    snap = json.loads(get("/api/snapshot")[1])
    check(
        "snapshot shows seeded state",
        snap["protocols"] >= 1
        and snap["sites"] >= 3
        and snap["fhir_bundles"] >= 3
        and snap["ae_records"] >= 4,
        snap,
    )
    demo = json.loads(get("/api/demo-data")[1])

    # 1. Protocol amendments
    a = post("/api/audit-protocol/PROT-TNX-001", {})
    check(
        "audit extracts 5 INC / 4 EXC",
        len(a["inclusion_criteria"]) == 5 and len(a["exclusion_criteria"]) == 4,
    )
    check(
        "audit flags schedule flaw + cost exposure",
        len(a["operational_flaws"]) >= 1 and a["amendment_exposure_usd"] > 0,
        (a["protocol_fragility_index"], a["amendment_exposure_usd"]),
    )

    # 2. Site selection
    s = post("/api/score-sites", {"sites": demo["sites"], "target_enrollment": 450})
    recs = {x["site_id"]: x["recommendation"] for x in s["evaluated_sites"]}
    check(
        "sites span GO/CONDITIONAL/NO-GO",
        recs.get("SITE-001") == "GO"
        and recs.get("SITE-003") == "CONDITIONAL"
        and recs.get("SITE-002") == "NO-GO",
        recs,
    )
    check(
        "portfolio timeline computed",
        s["portfolio_summary"]["projected_timeline_to_lpi_months"] > 0,
    )

    # 3. Cohort matching
    bundles = [b["bundle"] for b in demo["bundles"]]
    m = post("/api/match-cohort", {"protocol_id": "PROT-TNX-001", "bundles": bundles})
    by_id = {r["patient_id"]: r for r in m["matching_results"]}
    check("patient-001 ELIGIBLE", by_id["patient-001"]["overall_status"] == "ELIGIBLE")
    p2 = by_id["patient-002"]
    check(
        "patient-002 INELIGIBLE with cause",
        p2["overall_status"] == "INELIGIBLE"
        and any(not e["passed"] for e in p2["inclusion_evaluations"])
        and any(e["triggered"] for e in p2["exclusion_evaluations"]),
    )
    p3 = by_id["patient-003"]
    check(
        "patient-003 REVIEW_REQUIRED",
        p3["overall_status"] == "REVIEW_REQUIRED"
        and len(p3["physician_action_items"]) >= 2,
    )
    exc02 = [e for e in p3["exclusion_evaluations"] if e["criterion_id"] == "EXC-02"][0]
    check(
        "negation respected (brain note is not a trigger)",
        exc02["triggered"] is False,
        exc02["clinical_evidence_found"][:80],
    )

    # 4. Safety triage
    t = post("/api/triage-safety", {"records": demo["ae_records"]})["triaged_records"]
    d902 = [x for x in t if x["discrepancy_id"] == "DISC-902"][0]
    check(
        "SAE detected with 360h clock",
        d902["is_sae"] is True
        and d902["reporting_deadline_hours"] == 360
        and d902["regulatory_alert_required"] is True,
        d902["meddra_classification"]["soc"],
    )
    check(
        "routine cases stay routine",
        all(
            x["regulatory_alert_required"] is False
            for x in t
            if x["discrepancy_id"] != "DISC-902"
        ),
    )

    # 5. Diversity plan (original 3-patient cohort; pool now also holds finder seeds)
    dv = post("/api/diversity-plan", {"bundles": bundles[:3], "targets": None})
    check(
        "diversity mix computed",
        dv["n"] == 3 and "race" in dv["dimensions"] and len(dv["focus_areas"]) >= 1,
        dv["overall_status"],
    )

    # 6. History + export (match + triage above already persisted rows)
    hc = json.loads(get("/api/history/cohort?protocol_id=PROT-TNX-001")[1])[
        "evaluations"
    ]
    check("cohort history persisted", len(hc) >= 3, len(hc))
    hs = json.loads(get("/api/history/safety?protocol_id=UNASSIGNED")[1])["queries"]
    check("safety history persisted", len(hs) >= 4, len(hs))
    csv_c = get("/api/export/cohort.csv?protocol_id=PROT-TNX-001")[1]
    check("cohort CSV exports", "patient_fhir_id" in csv_c and "ELIGIBLE" in csv_c)
    csv_s = get("/api/export/safety.csv")[1]
    check("safety CSV exports", "reported_term" in csv_s and "Febrile" in csv_s)

    # 7. Structured export + burden
    st = json.loads(get("/api/protocol-structure/PROT-TNX-001")[1])
    check(
        "structure package M11-shaped",
        "M11" in st["m11Mapping"]
        and len(st["eligibility"]["inclusion"]) == 5
        and st["schedule"]["visit_days"] == [1, 14, 16],
    )
    bd = json.loads(get("/api/burden/PROT-TNX-001")[1])
    bscores = {v["day"]: v["score"] for v in bd["visits"]}
    check(
        "burden ranked Day1 > Day14 > Day16",
        bscores == {"1": 18, "14": 10, "16": 3} and bd["convertible_pct"] == 33.3,
        bscores,
    )

    # 8. Startup tracker
    su = json.loads(get("/api/startup")[1])
    check(
        "startup flags stale site",
        "SITE-002" in su["flagged_site_ids"]
        and "SITE-001" not in su["flagged_site_ids"],
        su["flagged_site_ids"],
    )
    adv = post("/api/startup/SITE-003/advance", {"stage": "activated", "note": "e2e"})
    check("startup advance works", adv["stage"] == "activated", adv["stage"])

    # 9. Monitoring
    mo = json.loads(get("/api/monitoring")[1])
    check(
        "monitoring flags SITE-002 only",
        "SITE-002" in mo["alert_site_ids"]
        and "SITE-001" not in mo["alert_site_ids"]
        and "SITE-003" not in mo["alert_site_ids"],
        mo["alert_site_ids"],
    )
    zb = {s["site_id"]: s["zero_enroll"]["band"] for s in mo["sites"]}
    check(
        "zero-enroll risk bands separate sites",
        zb.get("SITE-002") == "high" and zb.get("SITE-001") == "low",
        zb,
    )

    # 10. Trial finder
    b004 = [
        b["bundle"] for b in demo["bundles"] if b["name"] == "patient_004_her2.json"
    ][0]
    fr = post("/api/find-trials", {"bundle": b004})
    check(
        "finder ranks breast first for patient-004",
        fr["ranked"][0]["protocol_id"] == "PROT-TNX-002"
        and fr["ranked"][0]["status"] == "ELIGIBLE"
        and len(fr["ranked"]) == 3,
        [(t["protocol_id"], t["status"]) for t in fr["ranked"]],
    )

    # 11. External control
    ec = post(
        "/api/external-control",
        {"protocol_id": "PROT-TNX-001", "relax_ids": ["INC-04", "EXC-01"]},
    )
    check(
        "control pool grows with relaxation",
        {p["patient_id"] for p in ec["pool"]} == {"patient-001", "patient-002"}
        and "INC-04" in ec["methods_note"],
        len(ec["pool"]),
    )

    # 12. Tier 1+2: outlook, forecast, twins, mCODE, validity, complexity
    b001 = [b for b in bundles if b.get("id") == "patient-001"][0]
    o = json.loads(get("/api/trial-outlook/PROT-TNX-001")[1])
    check(
        "outlook returns success probability + breakdown",
        0.01 <= o["success_probability"] <= 0.95 and len(o["drivers"]) == 4,
        o["success_probability"],
    )
    fc = post(
        "/api/forecast",
        {
            "sites": [{"accrual": 2.0, "months_observed": 6}],
            "target_enrollment": 450,
            "deadline_months": 24.0,
        },
    )
    check(
        "forecast returns ordered percentiles",
        fc["p10"] <= fc["p50"] <= fc["p90"]
        and fc["p10"] > 0
        and 0 <= fc["prob_by_deadline"] <= 1,
        (fc["p50"], fc["prob_by_deadline"]),
    )
    tw = post(
        "/api/twins",
        {"protocol_id": "PROT-TNX-001", "bundle": b001, "n": 50, "seed": 7},
    )
    check(
        "twins distribution sums to n",
        tw["n"] == 50 and sum(tw["counts"].values()) == 50,
        tw["counts"],
    )
    mc = post("/api/mcode", {"bundle": b001})
    check(
        "mCODE profile extracted",
        "lung cancer" in mc["profile"]["cancer_type"].lower()
        and mc["completeness_pct"] > 0,
        mc["profile"]["cancer_type"],
    )
    nv = json.loads(get("/api/n2c2-status")[1])
    check(
        "validity benchmark reports fixture F1",
        nv["fixture_f1"] == 1.0
        and len(nv["criteria"]) == 13
        and nv["real_data_present"] is False,
        nv["fixture_f1"],
    )
    check(
        "audit carries readability complexity",
        a["complexity"]["flesch_ease"] > 0
        and "entity_density_per_100w" in a["complexity"],
        a["complexity"]["flesch_kincaid_grade"],
    )

    # 13. S-track: sweep, forensics, retention, enrichment, priors, outcomes
    sw = post(
        "/api/relax-sweep",
        {
            "protocol_id": "PROT-TNX-001",
            "twin_seed_bundle_id": "patient_001_breast_cancer",
            "twins_n": 20,
            "seed": 7,
        },
        timeout=120,
    )
    check(
        "sweep returns ladders over twins",
        sw["n_patients"] == 20
        and len(sw["criteria"]) == 5
        and any(s["ladder"] for c in sw["criteria"] for s in c["sub_sweeps"]),
        (sw["baseline_eligible_n"], sw["source"]),
    )
    fo = json.loads(get("/api/forensics?protocol_id=PROT-TNX-001")[1])
    check(
        "forensics aggregates stored runs",
        fo["n_evaluations"] >= 5 and len(fo["top_drivers"]) > 0,
        fo["n_evaluations"],
    )
    rt = post("/api/retention", {"protocol_id": "PROT-TNX-001", "bundle": b001})
    check(
        "retention scores with what-if",
        rt["band"] in ("low", "moderate", "high")
        and rt["what_if_remote"]["delta"] <= 0
        and len(rt["factors"]) >= 2,
        (rt["score"], rt["band"]),
    )
    check(
        "triage carries enrichment",
        all("enrichment" in x and "temporality" in x["enrichment"] for x in t),
        t[0]["enrichment"]["temporality"]["onset"],
    )
    fch = post(
        "/api/forecast",
        {
            "sites": [{"id": "SITE-001", "accrual": 0.1, "months_observed": 1}],
            "target_enrollment": 450,
            "use_site_history": True,
        },
    )
    check(
        "forecast blends observed site history",
        fch.get("site_sources", {}).get("0") == "observed" and fch["p50"] > 0,
        fch.get("site_sources"),
    )
    ob = json.loads(get("/api/outcome-benchmark?condition=NSCLC&phase=PHASE3")[1])
    check(
        "outcome benchmark returns registry shape",
        ob["source"] in ("live", "cache", "offline-fallback")
        and "top_outcomes" in ob
        and "median_enrollment" in ob,
        ob["source"],
    )
    check(
        "match carries provenance",
        all(
            "provenance" in e
            for r in m["matching_results"]
            for e in r["inclusion_evaluations"] + r["exclusion_evaluations"]
        ),
        by_id["patient-001"]["inclusion_evaluations"][0]["provenance"],
    )

    # 14. Gap-fill: PDF ingest + PubMed literature
    with open("data/raw/protocols/protocol_oncology_phase3.txt") as f:
        proto_text = f.read()
    pdf_b64 = base64.b64encode(make_pdf_bytes(proto_text)).decode()
    pa = post(
        "/api/audit-pdf",
        {"filename": "nsclc_protocol.pdf", "pdf_base64": pdf_b64},
        timeout=120,
    )
    check(
        "PDF audit matches text audit",
        pa["protocol_id"] == "PDF-NSCLC-PROTOCOL"
        and len(pa["inclusion_criteria"]) == 5
        and len(pa["exclusion_criteria"]) == 4
        and pa["pdf_source"]["pages"] >= 1,
        (pa["protocol_id"], pa["pdf_source"]["pages"]),
    )
    pb = json.loads(
        get("/api/pubmed?term=EGFR%20inhibitor%20hepatotoxicity&retmax=3")[1]
    )
    check(
        "pubmed returns literature shape",
        pb["source"] in ("live", "cache", "offline-fallback")
        and isinstance(pb["count"], int)
        and isinstance(pb["articles"], list)
        and all("pmid" in art for art in pb["articles"]),
        (pb["source"], pb["count"]),
    )
    # 15. R-track: signals, DCT, criteria, attrition, calibrated outlook
    sg = post("/api/safety-signals", {"records": demo["ae_records"]})
    liver = [p for p in sg["pairs"] if p["drug"] == "TNX-101" and p["n"] >= 3]
    check(
        "signals flag liver cluster as watch",
        sg["n_drugs"] == 2
        and len(liver) == 1
        and liver[0]["status"] == "watch"
        and liver[0]["prr"] >= 2,
        (liver[0]["event"], liver[0]["prr"]) if liver else sg["n_drugs"],
    )
    dc = json.loads(get("/api/dct-readiness/PROT-TNX-001")[1])
    check(
        "dct readiness grades visits",
        dc["readiness_score"] == 67
        and dc["total_visits"] == 3
        and dc["visits"][0]["verdict"] == "on-site",
        dc["readiness_score"],
    )
    cf = json.loads(get("/api/criteria-feedback/PROT-TNX-001")[1])
    check(
        "criteria feedback grades INC-04 worst",
        sum(cf["counts"].values()) == 9
        and any(w["id"] == "INC-04" and w["grade"] == "C" for w in cf["worst"]),
        cf["counts"],
    )
    at = json.loads(get("/api/attrition/PROT-TNX-001")[1])
    check(
        "attrition predicts bounded dropout",
        5.0 <= at["dropout_pct"] <= 60.0 and len(at["drivers"]) == 4,
        at["dropout_pct"],
    )
    check(
        "outlook calibrated log-odds drivers",
        o["success_probability"] == 0.3 and any("log-odds" in d for d in o["drivers"]),
        o["success_probability"],
    )
    rm = delete("/api/protocols/" + pa["protocol_id"])
    snap2 = json.loads(get("/api/snapshot")[1])
    check(
        "PDF protocol deletes cleanly",
        rm["deleted"] is True and snap2["protocols"] == 3,
        snap2["protocols"],
    )

    print(f"FAILURES: {len(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
