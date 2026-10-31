/* Core panel runners: audit, sites, cohort, safety. */
import { $, esc, fail, getJSON, postJSON } from "./api.js";
import { COHORT_BADGE, SITE_BADGE, critTable, evalTable, preJSON, table } from "./ui.js";
import { selectedBundles } from "./data.js";

let lastStructure = null;

export async function runAudit() {
  const el = $("auditResult");
  try {
    const a = await postJSON("/api/audit-protocol/" + encodeURIComponent($("auditPid").value.trim()), {});
    const f = a.protocol_fragility_index;
    const band = f < 30 ? "Low" : (f < 60 ? "Moderate" : "High");
    const lit = Math.round(Math.min(100, f) / 10);
    const segCls = f < 30 ? "on-low" : (f < 60 ? "on-mid" : "on-high");
    let segs = '<div class="segs" role="img" aria-label="fragility ' + esc(f) + ' of 100">';
    for (let i = 0; i < 10; i++) segs += '<i class="' + (i < lit ? segCls : "") + '"></i>';
    segs += "</div>";
    el.innerHTML =
      "<h3>" + esc(a.protocol_metadata.title) + "</h3>" +
      "<p>Phase " + esc(a.protocol_metadata.phase) + " — " + esc(a.protocol_metadata.primary_indication) +
      " — target n=" + esc(a.protocol_metadata.target_enrollment) + "</p>" +
      '<p>Fragility index: <span class="score">' + esc(f) + '</span> / 100 — ' + esc(band) + " amendment risk</p>" + segs +
      "<p>Amendment exposure: <strong>$" + esc(Number(a.amendment_exposure_usd).toLocaleString("en-US")) + "</strong> <span class='muted'>(" + esc(a.exposure_basis) + ")</span></p>" +
      "<p>Readability: Flesch ease <strong>" + esc(a.complexity.flesch_ease) +
      "</strong>, grade <strong>" + esc(a.complexity.flesch_kincaid_grade) +
      "</strong>, entity density " + esc(a.complexity.entity_density_per_100w) + "/100w" +
      (a.complexity.long_criteria.length ? " — long criteria: #" + a.complexity.long_criteria.join(", #") : "") +
      " <span class='muted'>(" + esc(a.complexity.basis) + ")</span></p>" +
      "<h3>Inclusion criteria</h3>" + critTable(a.inclusion_criteria) +
      "<h3>Exclusion criteria</h3>" + critTable(a.exclusion_criteria) +
      "<h3>Operational flaws</h3>" +
      (a.operational_flaws.length
        ? "<ul class='tight'>" + a.operational_flaws.map((x) =>
            "<li><strong>" + esc(x.domain) + ":</strong> " + esc(x.description) +
            "<br>Remediation: " + esc(x.suggested_remediation) + "</li>").join("") + "</ul>"
        : "<p>None detected.</p>");
    const pid2 = $("auditPid").value.trim();
    const st = await getJSON("/api/protocol-structure/" + encodeURIComponent(pid2));
    lastStructure = st;
    el.innerHTML += "<h3>Structured export (M11-inspired)</h3>" +
      "<p>" + esc(st.study.title) + " — " + esc(st.eligibility.inclusion.length) + " INC / " +
      esc(st.eligibility.exclusion.length) + " EXC coded, visits Day " +
      esc(st.schedule.visit_days.join(", ")) + "</p>" +
      "<p><button type='button' id='dlStructure'>Download JSON</button> " +
      "<button type='button' id='copyStructure'>Copy JSON</button></p>" +
      "<details class='evidence'><summary>Full structure</summary>" + preJSON(st) + "</details>";
    const bd = await getJSON("/api/burden/" + encodeURIComponent(pid2));
    el.innerHTML += "<h3>Visit burden &amp; DCT fit</h3>" +
      "<p>Total burden <strong>" + esc(bd.total_score) + "</strong> — " + esc(bd.verdict) +
      " — " + esc(bd.convertible_pct) + "% of visits remote-convertible</p>" +
      table(bd.visits.map((v) => ({ day: "Day " + v.day,
        procedures: v.procedures.join(", ") || "routine visit", score: v.score,
        remote: v.convertible ? "YES — " + v.reason : "NO — " + v.reason })),
        [["day", "Visit"], ["procedures", "Procedures"], ["score", "Burden"], ["remote", "Remote fit"]]) +
      "<p class='muted'>" + esc(bd.basis) + "</p>";
    const o = await getJSON("/api/trial-outlook/" + encodeURIComponent(pid2));
    el.innerHTML += "<h3>Trial outlook</h3>" +
      "<p>Success probability: <strong>" + esc(Math.round(o.success_probability * 100)) + "%</strong></p>" +
      table([{ k: "Enrollment failure", v: o.failure_breakdown.enrollment_failure },
             { k: "Safety failure", v: o.failure_breakdown.safety_failure },
             { k: "Efficacy failure", v: o.failure_breakdown.efficacy_failure }],
        [["k", "Failure mode"], ["v", "Share"]]) +
      "<ul class='tight'>" + o.drivers.map((d) => "<li>" + esc(d) + "</li>").join("") + "</ul>" +
      "<p class='muted'>" + esc(o.basis) + "</p>";
    $("dlStructure").addEventListener("click", () => {
      const blob = new Blob([JSON.stringify(lastStructure, null, 1)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "protocol_structure.json";
      a.click();
      URL.revokeObjectURL(a.href);
    });
    $("copyStructure").addEventListener("click", async () => {
      await navigator.clipboard.writeText(JSON.stringify(lastStructure, null, 1));
    });
  } catch (err) { fail(el, err); }
}

export async function runSites() {
  const el = $("sitesResult");
  try {
    const sites = JSON.parse($("sitesJson").value);
    const target = parseInt($("siteTarget").value, 10) || 0;
    const r = await postJSON("/api/score-sites", { sites, target_enrollment: target,
      live_lookup: $("siteLive").checked, condition: $("siteCondition").value });
    el.innerHTML = r.evaluated_sites.map((s) =>
      '<div class="record"><h3>' + esc(s.site_name) +
      ' <span class="badge ' + (SITE_BADGE[s.recommendation] || "") + '">' + esc(s.recommendation) + "</span> " +
      '<span class="score">' + esc(s.feasibility_score) + "</span></h3>" +
      "<p>Projected accrual: " + esc(s.projected_monthly_accrual_rate) + " patients/month — " + esc(s.country) + "</p>" +
      "<p>Competitors: " + esc(s.competitors_used) + " <span class='chip'>" + esc(s.competitor_source) + "</span></p>" +
      table([s.scoring_breakdown], [["velocity_score", "Velocity"], ["competition_penalty", "Competition penalty"],
        ["regulatory_efficiency", "Regulatory"], ["capacity_score", "Capacity"]]) +
      (s.identified_risks.length ? "<p>Risks: " + esc(s.identified_risks.join("; ")) + "</p>" : "") +
      "</div>").join("") +
      "<h3>Portfolio</h3><p>Analyzed <strong>" + esc(r.portfolio_summary.total_sites_analyzed) +
      "</strong> — selected <strong>" + esc(r.portfolio_summary.selected_sites_count) +
      "</strong> — projected <strong>" + esc(r.portfolio_summary.projected_timeline_to_lpi_months) +
      " months</strong> to last patient in.</p>";
    const fc = await postJSON("/api/forecast", { sites: r.evaluated_sites.map((s) =>
      ({ accrual: s.projected_monthly_accrual_rate, months_observed: 6 })), target_enrollment: target });
    el.innerHTML += "<h3>Enrollment forecast (Poisson-Gamma)</h3>" +
      "<p>Months to target — P10 <strong>" + esc(fc.p10) + "</strong>, P50 <strong>" +
      esc(fc.p50) + "</strong>, P90 <strong>" + esc(fc.p90) + "</strong> (mean " +
      esc(fc.mean) + "; " + esc(fc.simulations) + " simulations, seed " + esc(fc.seed) + ")</p>";
  } catch (err) { fail(el, err); }
}

export async function runCohort() {
  const el = $("cohortResult");
  try {
    const r = await postJSON("/api/match-cohort",
      { protocol_id: $("cohortPid").value.trim(), bundles: selectedBundles() });
    el.innerHTML = r.matching_results.map((p) =>
      '<div class="record"><h3>' + esc(p.patient_id) +
      ' <span class="badge ' + (COHORT_BADGE[p.overall_status] || "") + '">' + esc(p.overall_status) + "</span> " +
      '<span class="score">' + esc(p.match_percentage) + "%</span></h3>" +
      "<details class='evidence'><summary>Inclusion evaluations (" + p.inclusion_evaluations.length + ")</summary>" +
      evalTable(p.inclusion_evaluations, false) + "</details>" +
      "<details class='evidence'><summary>Exclusion evaluations (" + p.exclusion_evaluations.length + ")</summary>" +
      evalTable(p.exclusion_evaluations, true) + "</details>" +
      (p.physician_action_items.length
        ? "<p>Action items:</p><ul class='tight'>" + p.physician_action_items.map((a) => "<li>" + esc(a) + "</li>").join("") + "</ul>"
        : "<p>No action items.</p>") +
      "</div>").join("") || "<p>No bundles selected.</p>";
  } catch (err) { fail(el, err); }
}

export async function runSafety() {
  const el = $("safetyResult");
  try {
    const records = JSON.parse($("aeJson").value);
    const r = await postJSON("/api/triage-safety",
      { records, protocol_id: $("safetyPid").value.trim() || "UNASSIGNED" });
    el.innerHTML = r.triaged_records.map((t) =>
      '<div class="record"><h3>' + esc(t.discrepancy_id) +
      ' <span class="badge ' + (t.is_sae ? "b-sae" : "b-routine") + '">' + (t.is_sae ? "SAE" : "non-SAE") + "</span> " +
      (t.regulatory_alert_required
        ? '<span class="badge b-sae">alert ' + esc(t.reporting_deadline_hours) + "h</span>"
        : '<span class="badge b-routine">routine</span>') + "</h3>" +
      (t.is_sae ? '<div class="alert-sae">Serious adverse event — expedited clock: ' +
        (t.regulatory_alert_required ? esc(t.reporting_deadline_hours) + "h to report" : "standard reporting") + "</div>" : "") +
      "<p>" + esc(t.reported_term) + " — " + esc(t.meddra_classification.soc) + " / " +
      esc(t.meddra_classification.preferred_term) + " — " + esc(t.severity_grade) + "</p>" +
      "<details class='evidence'><summary>Site query</summary><p>To: <strong>" + esc(t.site_query.query_target) +
      "</strong></p><p>" + esc(t.site_query.query_text) + "</p><p class='muted'>Auto-close: " +
      esc(t.site_query.auto_close_condition) + "</p></details>" +
      "</div>").join("");
  } catch (err) { fail(el, err); }
}
