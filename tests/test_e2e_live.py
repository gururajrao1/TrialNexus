"""End-to-end checks for the MVP (4 cookbook agents) against the running API.

Start the server first:  uvicorn backend.app:app --port 8000
Run from the project root:  python tests/test_e2e_live.py
"""

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
FAILURES = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ((" — " + str(detail)) if detail else ""))
    if not cond:
        FAILURES.append(name)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as r:
        return r.status, r.read().decode("utf-8", "ignore")


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


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
        print("API not reachable at " + BASE + " — start it: uvicorn backend.app:app --port 8000")
        return 2
    status, html = get("/")
    check("UI serves with 4 workflow tabs only",
          status == 200 and "stepper" in html and "tab-safety" in html
          and "tab-diversity" not in html and "tab-external" not in html)
    snap = json.loads(get("/api/snapshot")[1])
    check("snapshot shows seeded state", snap["protocols"] >= 1 and snap["sites"] >= 3
          and snap["fhir_bundles"] >= 3 and snap["ae_records"] >= 4, snap)
    demo = json.loads(get("/api/demo-data")[1])

    # 1. Protocol amendments
    a = post("/api/audit-protocol/PROT-TNX-001", {})
    check("audit extracts 5 INC / 4 EXC",
          len(a["inclusion_criteria"]) == 5 and len(a["exclusion_criteria"]) == 4)
    check("audit flags schedule flaw + cost exposure", len(a["operational_flaws"]) >= 1
          and a["amendment_exposure_usd"] > 0,
          (a["protocol_fragility_index"], a["amendment_exposure_usd"]))

    # 2. Site selection
    s = post("/api/score-sites", {"sites": demo["sites"], "target_enrollment": 450})
    recs = {x["site_id"]: x["recommendation"] for x in s["evaluated_sites"]}
    check("sites span GO/CONDITIONAL/NO-GO", recs.get("SITE-001") == "GO"
          and recs.get("SITE-003") == "CONDITIONAL" and recs.get("SITE-002") == "NO-GO", recs)
    check("portfolio timeline computed",
          s["portfolio_summary"]["projected_timeline_to_lpi_months"] > 0)

    # 3. Cohort matching
    bundles = [b["bundle"] for b in demo["bundles"]]
    m = post("/api/match-cohort", {"protocol_id": "PROT-TNX-001", "bundles": bundles})
    by_id = {r["patient_id"]: r for r in m["matching_results"]}
    check("patient-001 ELIGIBLE", by_id["patient-001"]["overall_status"] == "ELIGIBLE")
    p2 = by_id["patient-002"]
    check("patient-002 INELIGIBLE with cause", p2["overall_status"] == "INELIGIBLE"
          and any(not e["passed"] for e in p2["inclusion_evaluations"])
          and any(e["triggered"] for e in p2["exclusion_evaluations"]))
    p3 = by_id["patient-003"]
    check("patient-003 REVIEW_REQUIRED", p3["overall_status"] == "REVIEW_REQUIRED"
          and len(p3["physician_action_items"]) >= 2)
    exc02 = [e for e in p3["exclusion_evaluations"] if e["criterion_id"] == "EXC-02"][0]
    check("negation respected (brain note is not a trigger)", exc02["triggered"] is False,
          exc02["clinical_evidence_found"][:80])

    # 4. Safety triage
    t = post("/api/triage-safety", {"records": demo["ae_records"]})["triaged_records"]
    d902 = [x for x in t if x["discrepancy_id"] == "DISC-902"][0]
    check("SAE detected with 360h clock", d902["is_sae"] is True
          and d902["reporting_deadline_hours"] == 360
          and d902["regulatory_alert_required"] is True,
          d902["meddra_classification"]["soc"])
    check("routine cases stay routine",
          all(x["regulatory_alert_required"] is False for x in t
              if x["discrepancy_id"] != "DISC-902"))

    print("FAILURES: %d" % len(FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
