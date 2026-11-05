"""End-to-end problem-statement checks against the running API (stdlib only).

Start the server first:  uvicorn backend.app:app --port 8000
Run from the project root:  python tests/test_e2e_live.py
"""

import base64
import json
import sys
import time
import urllib.error
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
    protos = json.loads(get("/api/protocols")[1])
    check(
        "protocol dropdown lists seeded protocols",
        isinstance(protos, list)
        and len(protos) >= 1
        and all("protocol_id" in p and "title" in p for p in protos),
        [p["protocol_id"] for p in protos] if isinstance(protos, list) else protos,
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
        0.01 <= o["success_probability"] <= 0.95 and len(o["drivers"]) == 5,
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
    pq = post(
        "/api/prescreen-queue",
        {
            "protocol_id": "PROT-TNX-001",
            "entries": [
                {"name": f"seed-{i}", "bundle": b} for i, b in enumerate(bundles)
            ],
        },
    )
    pq_status = [x["status"] for x in pq["rows"]]
    pq_ordered, seen_elig = "REVIEW_REQUIRED" in pq_status, False
    for x in pq["rows"]:
        if x["status"] == "ELIGIBLE":
            seen_elig = True
        elif seen_elig and (x["status"] == "REVIEW_REQUIRED" or x["near_miss"]):
            pq_ordered = False
    check(
        "prescreen ranks review before eligible",
        pq_ordered,
        pq_status,
    )
    dw = post(
        "/api/deviation-watch",
        {
            "records": [
                {
                    "site_id": "SITE-002",
                    "subject": "s1",
                    "visit": "V2",
                    "planned_day": 14,
                    "actual_day": 30,
                    "assessments_required": ["ECG"],
                    "assessments_done": [],
                }
            ],
            "window_days": 3,
        },
    )
    check(
        "deviation watch flags SITE-002 with SDV tier",
        dw["summary"]["n_findings"] >= 2
        and dw["by_site"][0]["tier"] == "100% critical fields",
        dw["summary"],
    )
    qa = post(
        "/api/query-aging",
        {
            "records": [
                {
                    "id": "Q-OLD",
                    "created_at": "2020-01-01",
                    "resolution_status": "OPEN",
                }
            ]
        },
    )
    check(
        "query upload routes escalations without touching DB",
        qa["escalation_list"]
        and qa["escalation_list"][0]["id"] == "Q-OLD"
        and qa["escalation_list"][0]["escalation"] == "critical",
        qa["n_overdue"],
    )
    cx = json.loads(get("/api/clinvar?gene=EGFR")[1])
    check(
        "clinvar lookup returns gene card",
        cx["gene"] == "EGFR"
        and cx["source"] in ("live", "cache", "offline-fallback")
        and isinstance(cx["variants"], list),
        cx["source"],
    )
    fx = json.loads(get("/api/faers?drug=osimertinib")[1])
    check(
        "openfda lookup returns report count",
        fx["drug"] == "osimertinib"
        and fx["source"] in ("live", "cache", "offline-fallback")
        and isinstance(fx["reports"], int),
        (fx["source"], fx["reports"]),
    )
    gc = json.loads(get("/api/gene-card?gene=EGFR")[1])
    check(
        "gene card fuses mygene, civic and clinvar",
        gc["gene"] == "EGFR"
        and isinstance(gc.get("civic_description", ""), str)
        and isinstance(gc.get("variant_highlights", {}).get("variants", []), list)
        and gc["sources"]["mygene"] in ("live", "cache", "offline-fallback"),
        gc["sources"],
    )
    ds = json.loads(get("/api/drug-safety?drug=ibuprofen")[1])
    check(
        "drug safety card carries faers, label and recalls",
        isinstance(ds["faers"]["reports"], int)
        and isinstance(ds["label"]["has_boxed"], bool)
        and isinstance(ds["recalls"]["count"], int),
        (ds["faers"]["reports"], ds["recalls"]["count"]),
    )
    lv = json.loads(get("/api/live-studies?condition=Non-Small+Cell+Lung+Cancer")[1])
    check(
        "live studies returns recruiting trials with locations",
        isinstance(lv["studies"], list)
        and lv["source"] in ("live", "cache", "offline-fallback"),
        (len(lv["studies"]), lv["source"]),
    )
    inv = json.loads(get("/api/inbox")[1])
    check(
        "inbox inventory lists slots without touching user data",
        set(("sites", "ae", "visits", "queries", "ecrf")) <= set(inv["slots"])
        and isinstance(inv["bundles"], list),
        sorted(inv["slots"]),
    )
    tm = post(
        "/api/trial-match",
        {"description": "EGFR lung cancer", "max_trials": 2},
        timeout=90,
    )
    check(
        "trial matcher returns explained live trials",
        isinstance(tm.get("trials"), list)
        and (len(tm["trials"]) > 0 or tm["source"] == "offline-fallback"),
        (tm["source"], tm.get("searched_terms", "")),
    )
    if tm.get("trials"):
        first = tm["trials"][0]
        check(
            "matcher trial carries snapshot and travel",
            isinstance(first.get("snapshot"), list)
            and isinstance(first.get("travel", {}).get("note", ""), str),
            first.get("nct_id", "?"),
        )
        ref = post(
            "/api/trial-referral", {"trial": first, "description": "EGFR lung cancer"}
        )
        check(
            "referral letter built from matched trial",
            first.get("nct_id", "") in ref.get("letter", ""),
            len(ref.get("letter", "")),
        )
        qs = post("/api/trial-questions", {"trial": first})
        check(
            "screening questions built from criteria",
            isinstance(qs.get("questions"), list),
            len(qs.get("questions", [])),
        )
    eb = post(
        "/api/e2b",
        {
            "record": {
                "discrepancy_id": "E2E-1",
                "patient_id": "P1",
                "suspect_drug": "osimertinib",
                "reported_term": "rash",
                "severity_grade": "Grade 2",
                "is_sae": False,
                "meddra_classification": {"soc": "Skin", "preferred_term": "Rash"},
            }
        },
    )
    check(
        "E2B export renders ICSR XML",
        "<medicinalproduct>osimertinib</medicinalproduct>" in eb.get("xml", ""),
        eb.get("message_id"),
    )
    du = json.loads(get("/api/dsur/PROT-TNX-001")[1])
    check(
        "DSUR shell counts database queries",
        isinstance(du.get("sections"), list)
        and any("[FILL]" in s.get("body", "") for s in du["sections"]),
        du.get("counts"),
    )
    rr = post(
        "/api/risk-register",
        {
            "signals": [
                {
                    "drug": "a",
                    "drug_label": "a",
                    "event": "e",
                    "status": "signal",
                    "n": 3,
                    "prr": 4.0,
                }
            ]
        },
    )
    check(
        "risk register ranks a signal first",
        rr.get("risks", [{}])[0].get("drug") == "a"
        and rr["risks"][0].get("owner") == "Safety physician",
        rr["risks"][0].get("risk_score"),
    )
    rv = post(
        "/api/signal-review",
        {
            "signals": [{"drug": "a", "event": "e", "status": "signal"}],
            "decisions": [
                {"drug": "a", "event": "e", "decision": "monitor", "note": "watch"}
            ],
        },
    )
    check(
        "signal review records dispositions",
        rv.get("n_reviewed") == 1 and rv.get("errors") == [],
        rv.get("trail"),
    )
    mp = post(
        "/api/monitoring-plan",
        {
            "protocol": {"id": "PROT-TNX-001"},
            "site_tiers": [{"site_id": "S1", "tier": "critical"}],
        },
    )
    check(
        "monitoring plan maps tiers to SDV depth",
        "100%" in mp.get("markdown", ""),
        len(mp.get("markdown", "")),
    )
    sv = post(
        "/api/siv-checklist",
        {
            "criteria": {
                "inclusion_criteria": [{"raw_text": "Age 18 or older"}],
                "exclusion_criteria": [],
            }
        },
    )
    check(
        "SIV checklist enumerates items",
        any("Age 18" in i for i in sv.get("items", [])),
        sv.get("n_items"),
    )
    mr = json.loads(get("/api/milestone-rollup")[1])
    check(
        "milestone rollup counts pipeline stages",
        isinstance(mr.get("by_stage"), dict),
        mr.get("pct_activated"),
    )
    rm = delete("/api/protocols/" + pa["protocol_id"])
    snap2 = json.loads(get("/api/snapshot")[1])
    check(
        "PDF protocol deletes cleanly",
        rm["deleted"] is True and snap2["protocols"] == 3,
        snap2["protocols"],
    )
    pw = post(
        "/api/power",
        {
            "kind": "proportions",
            "p1": 0.5,
            "p2": 0.4,
            "alpha": 0.05,
            "power": 0.8,
            "dropout": 0.1,
        },
    )
    check(
        "power sizes two proportions with dropout",
        pw.get("n_per_group_with_dropout", 0) >= pw.get("n_per_group", 1) > 0,
        pw.get("total"),
    )
    ni = post("/api/ni-margin", {"historical_effect": 0.3, "margin": 0.1})
    check(
        "NI margin preserves over half of M1",
        ni.get("pass") is True and ni.get("preserved_fraction", 0) > 0.5,
        ni.get("preserved_fraction"),
    )
    bd = post(
        "/api/budget",
        {
            "spec": {
                "arms": [{"name": "A", "n_subjects": 10}],
                "visits": [
                    {
                        "name": "V1",
                        "n_per_subject": 2,
                        "procedures": [
                            {"name": "labs", "unit_cost": 50, "count_per_visit": 1}
                        ],
                    }
                ],
                "fixed_costs": [{"name": "setup", "amount": 500}],
            }
        },
    )
    check(
        "budget multiplies user rates only",
        bd.get("grand_total") == 1500.0 and bd.get("per_subject") == 100.0,
        bd.get("grand_total"),
    )
    sn = post(
        "/api/sae-narrative",
        {
            "record": {
                "discrepancy_id": "E2E-1",
                "patient_id": "P1",
                "suspect_drug": "osimertinib",
                "reported_term": "rash",
                "severity_grade": "Grade 2",
                "is_sae": True,
                "meddra_classification": {"soc": "Skin", "preferred_term": "Rash"},
            }
        },
    )
    check(
        "SAE narrative drafts from triaged fields",
        "SERIOUS ADVERSE EVENT NARRATIVE" in sn.get("narrative", "")
        and "[FILL]" in sn.get("narrative", ""),
        len(sn.get("narrative", "")),
    )
    cs = post(
        "/api/contra-screen",
        {
            "label_sections": {"warnings": "Do not use with warfarin."},
            "meds": ["warfarin", "metformin"],
        },
    )
    check(
        "contra screen points at the warning section",
        len(cs.get("hits", [])) == 1 and cs["hits"][0]["med"] == "warfarin",
        cs.get("hits"),
    )
    live = post(
        "/api/contra-screen",
        {"drug": "ibuprofen", "meds": ["aspirin"], "fetch_live": True},
    )
    check(
        "contra fetch_live reports an honest label source",
        live.get("label_source") in ("live", "cache", "offline-fallback")
        and isinstance(live.get("hits"), list),
        live.get("label_source"),
    )
    ec = post(
        "/api/escalation-chains",
        {
            "aging": {
                "escalation_list": [
                    {"id": "Q-1", "days_overdue": 65},
                    {"id": "Q-2", "days_overdue": 5},
                ]
            }
        },
    )
    check(
        "escalation chains route by overdue band",
        ec.get("n_chains") == 2
        and {c["id"]: c["level"] for c in ec["chains"]}
        == {"Q-1": "sponsor+capa", "Q-2": "site"},
        ec.get("n_chains"),
    )
    pc = post(
        "/api/promo-check",
        {
            "draft": "the most effective new cure for lung cancer today",
            "indication": "treatment of EGFR-mutant non-small cell lung cancer",
        },
    )
    check(
        "promo check flags off-indication terms",
        pc.get("verdict") == "needs review" and len(pc.get("flags", [])) > 0,
        pc.get("flags"),
    )
    vr = post(
        "/api/visit-report",
        {
            "findings": [
                {
                    "site_id": "S1",
                    "subject": "a",
                    "visit": "V2",
                    "type": "out-of-window",
                    "severity": "major",
                    "detail": "9 days late",
                }
            ],
            "site_tier": {"site_id": "S1", "tier": "watch"},
        },
    )
    check(
        "visit report counts findings by severity",
        vr.get("n_findings") == 1
        and "Monitoring visit report" in vr.get("markdown", ""),
        vr.get("by_severity"),
    )
    cd = post(
        "/api/code-deviation",
        {"deviation_type": "consent-violation", "detail": "re-consent missed"},
    )
    check(
        "CDISC map codes consent violations",
        cd.get("cdisc_code") == "C158839",
        cd.get("cdisc_label"),
    )
    fw = post(
        "/api/five-whys",
        {"deviation_type": "missing-assessment", "detail": "week-8 scan skipped"},
    )
    check(
        "5-whys scaffold asks five with an effectiveness check",
        len(fw.get("questions", [])) == 5 and "effectiveness_check" in fw,
        len(fw.get("questions", [])),
    )
    pf = json.loads(get("/api/portfolio")[1])
    check(
        "portfolio rolls up seeded protocols",
        pf.get("n_protocols", 0) >= 1
        and all("protocol_id" in p for p in pf.get("protocols", [])),
        pf.get("n_protocols"),
    )
    ds = post("/api/dsmb-pack", {"protocol_id": "PROT-TNX-001"})
    check(
        "DSMB pack shells enrollment and safety",
        "DSMB report pack" in ds.get("markdown", "") and ds.get("n_sites", 0) >= 1,
        ds.get("protocol_id"),
    )
    ip = post(
        "/api/inspection-pack",
        {
            "protocol_id": "PROT-TNX-001",
            "n_deviations": 2,
            "open_items": ["file week-8 report"],
        },
    )
    check(
        "inspection pack compiles exhibits with TMF fills",
        len(ip.get("exhibits", [])) == 8
        and ip.get("open_items") == ["file week-8 report"],
        len(ip.get("exhibits", [])),
    )
    dg = post("/api/digest", {"threshold": 10000, "country": "United States"})
    check(
        "digest composes query pressure with honest counts",
        dg.get("open_queries", -1) >= 0 and isinstance(dg.get("items"), list),
        dg.get("open_queries"),
    )
    im = post(
        "/api/import-map",
        {
            "text": "Site,Subject,Visit,Planned Day,Actual Day\nS1,P1,V2,14,22\n",
            "target": "visits",
        },
    )
    check(
        "CSV import maps CTMS headers to feed rows",
        im.get("n_rows") == 1
        and im["records"][0].get("site_id") == "S1"
        and im["records"][0].get("actual_day") == "22",
        im.get("mapped_columns"),
    )
    try:
        post("/api/import-map", {"text": "a,b\n1,2\n", "target": "visits"})
        im_bad_code = None
    except urllib.error.HTTPError as exc:
        im_bad_code = exc.code
    check(
        "CSV import rejects unrecognized columns with 422",
        im_bad_code == 422,
        im_bad_code,
    )
    pd = post(
        "/api/protocol-diff",
        {
            "a_text": "Trial T\nPhase 3\nInclusion criteria:\n1. Age 18 or older.\n",
            "b_text": "Trial T\nPhase 3\nInclusion criteria:\n1. Age 21 or older.\n2. ECOG 0-1.\n",
            "a_name": "v1",
            "b_name": "v2",
        },
    )
    check(
        "protocol diff separates rewrites from adds",
        {c["change"] for c in pd.get("criteria_changes", [])} == {"rewritten", "added"},
        pd.get("n_changes"),
    )
    ac = post(
        "/api/diversity-actuals",
        {"bundles": bundles[:3], "targets": None},
    )
    check(
        "diversity actuals counts enrolled mix",
        ac.get("enrolled_n") == 3 and isinstance(ac.get("dimensions"), dict),
        ac.get("enrolled_n"),
    )
    fn = json.loads(get("/api/funnel?protocol_id=PROT-TNX-001")[1])
    check(
        "funnel reports conversion from stored evaluations",
        fn.get("n_evaluations", 0) >= 0
        and "conversion_pct" in fn
        and isinstance(fn.get("by_status"), dict),
        fn.get("conversion_pct"),
    )
    ql = post(
        "/api/query-letter",
        {
            "record": {
                "discrepancy_id": "E2E-1",
                "patient_id": "P1",
                "suspect_drug": "osimertinib",
                "reported_term": "rash",
                "severity_grade": "Grade 2",
                "site_query": {
                    "query_target": "SITE-001",
                    "query_text": "Confirm onset date.",
                    "auto_close_condition": "onset entered",
                },
            }
        },
    )
    check(
        "query letter drafts to, subject, and question",
        "SITE-001" in ql.get("body", "")
        and "Confirm onset date." in ql.get("body", ""),
        ql.get("subject"),
    )
    co = post("/api/closeout-pack", {"protocol_id": "PROT-TNX-001", "n_deviations": 1})
    check(
        "closeout pack mirrors inspection honesty contract",
        len(co.get("exhibits", [])) == 7
        and any("[FILL" in e.get("status", "") for e in co["exhibits"]),
        len(co.get("exhibits", [])),
    )

    print(f"FAILURES: {len(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
