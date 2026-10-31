/* TrialNexus static UI (MVP: 4 panels). Same-origin API, no dependencies. */
const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + " → HTTP " + r.status);
  return r.json();
}
async function postJSON(path, payload) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(path + " → HTTP " + r.status);
  return r.json();
}
function table(rows, cols) {
  let h = '<table class="grid"><thead><tr>';
  for (const c of cols) h += "<th>" + esc(c[1]) + "</th>";
  h += "</tr></thead><tbody>";
  for (const r of rows) {
    h += "<tr>";
    for (const c of cols) {
      const v = r[c[0]];
      const shown = v === null || v === undefined ? "—"
        : (typeof v === "boolean" ? (v ? "Yes" : "No")
        : (typeof v === "object" ? JSON.stringify(v) : v));
      h += "<td>" + esc(shown) + "</td>";
    }
    h += "</tr>";
  }
  return h + "</tbody></table>";
}
function preJSON(obj) {
  return '<pre class="json">' + esc(JSON.stringify(obj, null, 1)) + "</pre>";
}
function fail(el, err) {
  el.innerHTML = '<div class="error">' + esc("Failed: " + err.message) + "</div>";
}
const SITE_BADGE = { GO: "b-go", CONDITIONAL: "b-cond", "NO-GO": "b-nogo" };
const COHORT_BADGE = { ELIGIBLE: "b-elig", INELIGIBLE: "b-inelig", REVIEW_REQUIRED: "b-review" };

/* Tabs */
const tabBtns = ["audit", "sites", "cohort", "safety"].map((n) => $("tabbtn-" + n));
tabBtns.forEach((btn) => btn.addEventListener("click", () => {
  tabBtns.forEach((b) => b.setAttribute("aria-selected", b === btn ? "true" : "false"));
  ["audit", "sites", "cohort", "safety"].forEach((n) => { $("tab-" + n).hidden = ("tabbtn-" + n) !== btn.id; });
}));

/* Snapshot + health */
async function loadSnapshot() {
  try {
    const h = await getJSON("/health");
    const pill = $("apiStatus");
    pill.textContent = h.mode === "zero-cost-local" ? "API online" : "API online";
    const s = await getJSON("/api/snapshot");
    const cards = [["Protocols", s.protocols], ["Sites", s.sites],
                   ["FHIR patients", s.fhir_bundles], ["Safety records", s.ae_records]];
    $("snapshot").innerHTML = cards.map(([l, n]) =>
      '<div class="metric"><span class="num">' + esc(n) + '</span><span class="lbl">' + esc(l) + "</span></div>").join("");
  } catch (err) {
    const pill = $("apiStatus");
    pill.textContent = "API offline";
    pill.classList.add("down");
    $("snapshot").innerHTML = '<div class="error">' + esc("API unreachable: " + err.message) + "</div>";
    throw err;
  }
}

/* Demo data prefill */
let demoBundles = [];
async function loadDemo() {
  const d = await getJSON("/api/demo-data");
  $("sitesJson").value = JSON.stringify(d.sites, null, 1);
  $("aeJson").value = JSON.stringify(d.ae_records, null, 1);
  demoBundles = d.bundles;
  $("bundleList").innerHTML = d.bundles.map((b) =>
    '<label><input type="checkbox" checked data-name="' + esc(b.name) + '"> ' + esc(b.name) + "</label>").join("");
}

function critTable(rows) {
  let h = '<table class="grid"><thead><tr><th>ID</th><th>Category</th><th>Rule</th><th>Flexibility</th></tr></thead><tbody>';
  for (const c of rows) {
    const rule = c.variable + " " + c.operator + " " +
      (typeof c.value === "object" ? JSON.stringify(c.value) : c.value) + (c.unit ? " " + c.unit : "");
    const flex = c.flexibility_rating === "Ambiguous" ? "flex-amb"
      : (c.flexibility_rating === "Rigid" ? "flex-rigid" : "");
    h += "<tr><td class='mono'>" + esc(c.id) + "</td><td><span class='chip'>" + esc(c.category) +
      "</span></td><td>" + esc(rule) + "<br><span class='muted'>" + esc(c.raw_text.slice(0, 140)) +
      "</span></td><td><span class='chip " + flex + "'>" + esc(c.flexibility_rating) + "</span></td></tr>";
  }
  return h + "</tbody></table>";
}
function evalTable(rows, isExclusion) {
  let h = '<table class="grid"><thead><tr><th>ID</th><th>Outcome</th><th>Evidence</th></tr></thead><tbody>';
  for (const e of rows) {
    const bad = isExclusion ? e.triggered : !e.passed;
    const outcome = e.missing_data ? "<span class='miss'>NEEDS DATA</span>"
      : (bad ? "<span class='fail'>" + (isExclusion ? "TRIGGERED" : "FAIL") + "</span>"
             : "<span class='pass'>" + (isExclusion ? "CLEAR" : "PASS") + "</span>");
    h += "<tr><td class='mono'>" + esc(e.criterion_id) + "</td><td>" + outcome + "</td><td>" +
      esc(e.clinical_evidence_found) + "</td></tr>";
  }
  return h + "</tbody></table>";
}

/* Panel runners */
async function runAudit() {
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
  } catch (err) { fail(el, err); }
}
async function runSites() {
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
  } catch (err) { fail(el, err); }
}
function selectedBundles() {
  const checked = new Set([...$("bundleList").querySelectorAll("input:checked")].map((i) => i.dataset.name));
  return demoBundles.filter((b) => checked.has(b.name)).map((b) => b.bundle);
}
async function runCohort() {
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
async function runSafety() {
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

$("auditForm").addEventListener("submit", (e) => { e.preventDefault(); runAudit(); });
$("sitesForm").addEventListener("submit", (e) => { e.preventDefault(); runSites(); });
$("cohortForm").addEventListener("submit", (e) => { e.preventDefault(); runCohort(); });
$("safetyForm").addEventListener("submit", (e) => { e.preventDefault(); runSafety(); });

/* Boot: snapshot, prefill, then auto-run all four panels. */
loadSnapshot().then(loadDemo).then(() => {
  runAudit(); runSites(); runCohort(); runSafety();
}).catch(() => {
  for (const id of ["auditResult", "sitesResult", "cohortResult", "safetyResult"]) {
    $(id).innerHTML = '<div class="error">API unreachable. Start it with: uvicorn backend.app:app --port 8000</div>';
  }
});
