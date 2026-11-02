/* Frontend smoke: boots the ES-module UI against stub DOM + stub API.
   Catches bad module imports, unknown element ids, and shape mismatches
   without a browser. Run: node tests/test_ui_smoke.mjs (exit 0 = wired). */
import assert from "node:assert/strict";

const TABS = ["audit", "sites", "cohort", "safety", "diversity", "history",
  "startup", "monitoring", "finder", "external", "twins", "mcode", "validity"];
const IDS = new Set([
  "apiStatus", "snapshot", "sitesJson", "aeJson", "bundleList",
  "auditPid", "auditResult", "siteTarget", "siteCondition", "siteLive", "sitesResult",
  "cohortPid", "cohortResult", "safetyPid", "safetyResult",
  "diversityTargets", "diversityResult", "historyPid", "historyResult", "exportLinks",
  "startupSite", "startupStage", "startupNote", "startupResult",
  "monitoringResult", "finderBundle", "finderResult", "relaxIds", "externalResult",
  "twinsBundle", "twinsN", "twinsSeed", "twinsJitter", "twinsResult",
  "mcodeBundle", "mcodeResult", "validityResult",
  "dlStructure", "copyStructure", "globalPid", "runAllBtn", "runAllStatus",
  "sweepSeed", "sweepN", "sweepResult", "sweepForm",
  "retentionBundle", "retentionResult", "retentionForm",
  "outcomesCondition", "outcomesPhase", "outcomesResult", "outcomesForm",
  "forensicResult",
  "pdfFile", "pdfForm", "pubmedTerm", "pubmedResult", "pubmedForm",
  "signalForm", "signalsResult",
  "crfFields", "crfForm", "crfResult",
  "sitesFile", "aeFile", "crfFile",
  "loadSites", "sitesNote", "loadAe", "aeNote", "loadAging", "agingNote",
  "loadDev", "devNote", "loadCrf", "crfNote",
  "prescreenFiles", "prescreenForm", "prescreenResult", "prescreenUploadNote",
  "prescreenGene", "dlWorklist",
  "devJson", "devFile", "devWindow", "devForm", "devResult",
  "agingJson", "agingFile", "agingForm", "agingResult", "extBundleList",
]);
for (const t of TABS) { IDS.add("tabbtn-" + t); IDS.add("tab-" + t); IDS.add(t + "Form"); }

const listeners = new Map();
const elements = new Map();
function makeEl(id) {
  return {
    id, innerHTML: "", textContent: "", checked: false, hidden: true,
    options: [],
    value: { auditPid: "PROT-TNX-001", cohortPid: "PROT-TNX-001",
      safetyPid: "UNASSIGNED", siteTarget: "450",
      siteCondition: "Lung Cancer", twinsN: "500", globalPid: "PROT-TNX-001",
      relaxIds: "INC-04, EXC-01", diversityTargets: "{}" }[id] || "",
    classList: { add() {} },
    setAttribute() {},
    addEventListener(ev, fn) {
      if (!listeners.has(id)) listeners.set(id, {});
      const m = listeners.get(id);
      (m[ev] = m[ev] || []).push(fn);
    },
    querySelectorAll() { return []; },
  };
}
globalThis.document = {
  getElementById(id) {
    if (!IDS.has(id)) return null; // unknown id = wiring bug, like a real DOM
    if (!elements.has(id)) elements.set(id, makeEl(id));
    return elements.get(id);
  },
};

const AUDIT = {
  protocol_metadata: { title: "T", phase: "Phase 3", primary_indication: "I", target_enrollment: 1 },
  protocol_fragility_index: 20, amendment_exposure_usd: 1000, exposure_basis: "b",
  complexity: { flesch_ease: 50, flesch_kincaid_grade: 10, entity_density_per_100w: 5,
    long_criteria: [], basis: "b" },
  inclusion_criteria: [], exclusion_criteria: [], operational_flaws: [],
};
const SITE = { site_id: "S", site_name: "S", country: "C", feasibility_score: 80,
  recommendation: "GO", projected_monthly_accrual_rate: 2, competitors_used: 1,
  competitor_source: "cache",
  scoring_breakdown: { velocity_score: 1, competition_penalty: 0,
    regulatory_efficiency: 1, capacity_score: 1 }, identified_risks: [] };
const seen = [];
globalThis.fetch = async (url) => {
  const path = String(url).split("?")[0];
  seen.push(path);
  const routes = {
    "/health": { mode: "zero-cost-local" },
    "/api/snapshot": { protocols: 1, sites: 1, fhir_bundles: 1, ae_records: 1 },
    "/api/demo-data": { sites: [], bundles: [{ name: "b.json", bundle: {} }], ae_records: [] },
    "/api/diversity-defaults": { targets: {} },
    "/api/audit-protocol/PROT-TNX-001": AUDIT,
    "/api/protocol-structure/PROT-TNX-001": { study: { title: "T" },
      eligibility: { inclusion: [], exclusion: [] }, schedule: { visit_days: [] } },
    "/api/burden/PROT-TNX-001": { total_score: 1, verdict: "v", convertible_pct: 0,
      visits: [], basis: "b" },
    "/api/trial-outlook/PROT-TNX-001": { success_probability: 0.4,
      failure_breakdown: { enrollment_failure: 0.2, safety_failure: 0.2, efficacy_failure: 0.2 },
      drivers: [], basis: "b" },
    "/api/score-sites": { evaluated_sites: [SITE],
      portfolio_summary: { total_sites_analyzed: 1, selected_sites_count: 1,
        projected_timeline_to_lpi_months: 5 } },
    "/api/forecast": { p10: 1, p50: 2, p90: 3, mean: 2, simulations: 10, seed: 42 },
    "/api/match-cohort": { matching_results: [{ patient_id: "p", overall_status: "ELIGIBLE",
      match_percentage: 100,
      inclusion_evaluations: [{ criterion_id: "INC-01", passed: true,
        clinical_evidence_found: "e", missing_data: false }],
      exclusion_evaluations: [], physician_action_items: [] }] },
    "/api/triage-safety": { triaged_records: [{ discrepancy_id: "D", patient_id: "P",
      reported_term: "t", meddra_classification: { soc: "s", preferred_term: "p" },
      severity_grade: "Grade 1", is_sae: false, regulatory_alert_required: false,
      reporting_deadline_hours: null,
      site_query: { query_target: "q", query_text: "t", auto_close_condition: "c" } }] },
    "/api/diversity-plan": { n: 1, overall_status: "ready",
      dimensions: { race: [{ group: "g", n: 1, actual_pct: 1, goal_pct: 1, gap_pp: 0,
        status: "s", need_to_enroll: 0 }] }, focus_areas: [], note: "n" },
    "/api/history/cohort": { evaluations: [{ patient_fhir_id: "p", eligibility_status: "s",
      inclusion_match_score: 1, exclusion_conflict_count: 0, evaluated_at: "d" }] },
    "/api/history/safety": { queries: [{ reported_term: "t", suspected_meddra_soc: "s",
      severity: "s", is_sae: false, reporting_timeline_hours: 1, resolution_status: "s" }] },
    "/api/startup": { sites: [{ site_id: "S", site_name: "S", country: "C", stage: "s",
        days_in_stage: 1, days_since_identified: 2, flags: [] }], as_of: "d",
      benchmarks: { contract_days: 1, irb_days: 1, activation_days: 1 }, flagged_site_ids: [] },
    "/api/monitoring": { sites: [{ site_id: "S", worst: "ok",
        kris: [{ kri: "k", value: 1, detail: "d", status: "ok" }], action: "a",
        zero_enroll: { score: 0, band: "low", factors: [] } }],
      alert_site_ids: [], note: "n" },
    "/api/find-trials": { patient_id: "p", ranked: [{ title: "t", status: "ELIGIBLE",
      match_percentage: 90, protocol_id: "P", phase: "1", top_reasons: ["r"] }] },
    "/api/external-control": { pool: [{ patient_id: "p", strict_status: "s",
        relaxed_status: "r", match_percentage: 1 }], near_miss: [],
      comparability: { pool_mix: { race: [{ group: "g", n: 1, actual_pct: 1 }] } },
      methods_note: "m" },
    "/api/twins": { n: 0, seed: 7, jitter: 0.15,
      counts: { ELIGIBLE: 0, INELIGIBLE: 0, REVIEW_REQUIRED: 0 },
      eligible_pct: 0, eligible_ci95: [0, 0], mc_se: 0, base_status: "ELIGIBLE",
      flips: [{ criterion_id: "INC-01", kind: "inclusion", flips: 0, flip_rate: 0 }],
      note: "n" },
    "/api/mcode": { profile: { cancer_type: "c", stage: "s", histology: "h",
      biomarkers: [], ecog: "0", metastasis_sites: [] }, completeness_pct: 0, gaps: [],
      note: "n" },
    "/api/n2c2-status": { fixture_f1: 1, criteria: [], real_data_present: false,
      instructions: "i" },
    "/api/relax-sweep": { source: "s", n_patients: 1, baseline_eligible_n: 1,
      criteria: [{ id: "INC-04", raw_text: "r", marginal_flips: [], marginal_n: 0,
        sub_sweeps: [{ variable: "v", operator: ">=", base: 1, unit: "u",
          ladder: [{ threshold: 0.9, eligible_n: 1, newly_n: 0, newly_eligible: [] }] }] }],
      note: "n" },
    "/api/retention": { score: 10, band: "low",
      factors: [{ factor: "f", points: 1, modifiable: true }],
      what_if_remote: { convertible_visits: 1, score: 9, band: "low", delta: -1 },
      basis: "b" },
    "/api/forensics": { n_evaluations: 1,
      inclusions: [{ criterion_id: "INC-01", fail_rate: 0, missing_rate: 0, n: 1 }],
      exclusions: [],
      top_drivers: [{ criterion_id: "INC-01", kind: "k", rate: 0, n: 0 }],
      note: "n" },
    "/api/dct-readiness/PROT-TNX-001": { readiness_score: 67, remote_capable_n: 2,
      total_visits: 3, econsent_mentioned: false,
      visits: [{ day: "1", procedures: [], modalities: [], verdict: "on-site" }],
      basis: "b" },
    "/api/criteria-feedback/PROT-TNX-001": { design_score: 64,
      counts: { A: 2, B: 6, C: 1 }, worst: [], basis: "b" },
    "/api/attrition/PROT-TNX-001": { dropout_pct: 20, interval_pct: [15, 25],
      drivers: [], basis: "b" },
    "/api/csm": { sites: [{ site_id: "S", n_flagged: 0, signals: [] }], basis: "b" },
    "/api/lock-readiness/PROT-TNX-001": { buckets: {}, n_open: 0, n_resolved: 0,
      checks: [], overall: "green", basis: "b" },
    "/api/lock-readiness/UNASSIGNED": { buckets: {}, n_open: 0, n_resolved: 0,
      checks: [], overall: "green", basis: "b" },
    "/api/query-aging/UNASSIGNED": { rows: [], owner_matrix: {},
      escalation_list: [], n_open: 0, n_overdue: 0, basis: "b" },
    "/api/query-aging/PROT-TNX-001": { rows: [], owner_matrix: {},
      escalation_list: [], n_open: 0, n_overdue: 0, basis: "b" },
    "/api/adaptive-design": { spending: "obf", alpha: 0.05,
      looks: [{ t: 0.5, alpha_spent: 0, z_efficacy: 0, p_efficacy: 0 }], basis: "b" },
    "/api/consent-check/PROT-TNX-001": { score: 90, n_sentences: 1,
      long_sentences: [], jargon_hits: [], suggestions: [], basis: "b" },
  };
  if (path.startsWith("/api/live-studies")) {
    return { ok: true,
      json: async () => ({ condition: "x", phase: "", studies: [], source: "cache" }) };
  }
  if (path.startsWith("/api/outcome-benchmark")) {
    return { ok: true,
      json: async () => ({ n_completed: 10, source: "cache", with_results_pct: 50,
        sampled_n: 10, median_enrollment: 200, top_outcomes: [] }) };
  }
  if (!(path in routes)) throw new Error("unstubbed endpoint: " + path);
  return { ok: true, json: async () => routes[path] };
};

await import("../frontend/js/boot.js");
await new Promise((r) => setTimeout(r, 500)); // let the boot chain settle

const results = [...TABS.map((t) => t + "Result"),
  "sweepResult", "retentionResult", "forensicResult"];
for (const id of results) {
  const html = elements.get(id)?.innerHTML || "";
  assert.ok(html.length > 0, id + " was never rendered");
  assert.ok(!html.includes('class="error"'), id + " rendered an error: " + html.slice(0, 120));
}
for (const ep of ["/api/audit-protocol/PROT-TNX-001", "/api/score-sites",
    "/api/match-cohort", "/api/triage-safety", "/api/n2c2-status"]) {
  assert.ok(seen.includes(ep), "panel never called " + ep);
}
assert.ok((elements.get("snapshot")?.innerHTML || "").includes("Protocols"));
// tab switching still wired
for (const fn of listeners.get("tabbtn-sites")?.click || []) fn();
assert.equal(elements.get("tab-sites").hidden, false);
assert.equal(elements.get("tab-audit").hidden, true);
console.log("ui-smoke-ok: all panels rendered, 0 errors, tabs switch");
