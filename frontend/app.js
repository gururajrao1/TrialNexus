/* TrialNexus static UI. Same-origin API, no dependencies. */
const $ = (id) => document.getElementById(id);
let lastStructure = null;

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
const tabBtns = ["audit", "sites", "cohort", "safety", "diversity", "history", "startup", "monitoring", "finder", "external", "twins", "mcode", "validity"].map((n) => $("tabbtn-" + n));
tabBtns.forEach((btn) => btn.addEventListener("click", () => {
  tabBtns.forEach((b) => b.setAttribute("aria-selected", b === btn ? "true" : "false"));
  ["audit", "sites", "cohort", "safety", "diversity", "history", "startup", "monitoring", "finder", "external", "twins", "mcode", "validity"].forEach((n) => { $("tab-" + n).hidden = ("tabbtn-" + n) !== btn.id; });
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
    const cols = [["id", "ID"], ["category", "Category"], ["variable", "Variable"],
                  ["operator", "Op"], ["value", "Value"], ["flexibility_rating", "Flexibility"]];
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
    const fc = await postJSON("/api/forecast", { sites: r.evaluated_sites.map((s) =>
      ({ accrual: s.projected_monthly_accrual_rate, months_observed: 6 })), target_enrollment: target });
    el.innerHTML += "<h3>Enrollment forecast (Poisson-Gamma)</h3>" +
      "<p>Months to target — P10 <strong>" + esc(fc.p10) + "</strong>, P50 <strong>" +
      esc(fc.p50) + "</strong>, P90 <strong>" + esc(fc.p90) + "</strong> (mean " +
      esc(fc.mean) + "; " + esc(fc.simulations) + " simulations, seed " + esc(fc.seed) + ")</p>";
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
$("diversityForm").addEventListener("submit", (e) => { e.preventDefault(); runDiversity(); });
$("historyForm").addEventListener("submit", (e) => { e.preventDefault(); runHistory(); });
$("startupForm").addEventListener("submit", async (e) => { e.preventDefault();
  try {
    await postJSON("/api/startup/" + encodeURIComponent($("startupSite").value) + "/advance",
      { stage: $("startupStage").value, note: $("startupNote").value });
    runStartup();
  } catch (err) { fail($("startupResult"), err); } });

async function loadDiversityDefaults() {
  const d = await getJSON("/api/diversity-defaults");
  $("diversityTargets").value = JSON.stringify(d.targets, null, 1);
}
function diversityBundles() {
  const sel = selectedBundles();
  return sel.length ? sel : demoBundles.map((b) => b.bundle);
}
async function runDiversity() {
  const el = $("diversityResult");
  try {
    let targets = null;
    const txt = $("diversityTargets").value.trim();
    if (txt) targets = JSON.parse(txt);
    const r = await postJSON("/api/diversity-plan", { bundles: diversityBundles(), targets });
    const badge = r.overall_status === "ready" ? "b-elig"
      : (r.overall_status === "watch" ? "b-review" : "b-inelig");
    el.innerHTML = "<h3>Cohort n=" + esc(r.n) + ' <span class="badge ' + badge + '">' +
      esc(r.overall_status) + "</span></h3>" +
      Object.entries(r.dimensions).map(([dim, rows]) =>
        "<h3>" + esc(dim) + "</h3>" + table(rows.map((x) => ({
          group: x.group, n: x.n, actual: x.actual_pct + "%", goal: x.goal_pct + "%",
          gap: (x.gap_pp > 0 ? "+" : "") + x.gap_pp + "pp", status: x.status, need: x.need_to_enroll,
        })), [["group", "Group"], ["n", "n"], ["actual", "Actual"], ["goal", "Goal"],
              ["gap", "Gap"], ["status", "Status"], ["need", "Need"]])).join("") +
      "<h3>Focus areas</h3><ul class='tight'>" +
      r.focus_areas.map((f) => "<li>" + esc(f) + "</li>").join("") + "</ul>" +
      "<p class='muted'>" + esc(r.note) + "</p>";
  } catch (err) { fail(el, err); }
}
async function runHistory() {
  const el = $("historyResult");
  try {
    const pid = $("historyPid").value.trim();
    const q = pid ? "?protocol_id=" + encodeURIComponent(pid) : "";
    const c = await getJSON("/api/history/cohort" + q);
    const s = await getJSON("/api/history/safety" + q);
    $("exportLinks").innerHTML = '<a href="/api/export/cohort.csv' + q + '">cohort.csv</a> · ' +
      '<a href="/api/export/safety.csv' + q + '">safety.csv</a>';
    el.innerHTML = "<h3>Cohort evaluations (" + c.evaluations.length + ")</h3>" +
      (c.evaluations.length ? table(c.evaluations,
        [["patient_fhir_id", "Patient"], ["eligibility_status", "Status"],
         ["inclusion_match_score", "Match %"], ["exclusion_conflict_count", "Excl hits"],
         ["evaluated_at", "Evaluated"]])
        : "<p class='muted'>No evaluations yet — run Cohort matching first.</p>") +
      "<h3>Safety queries (" + s.queries.length + ")</h3>" +
      (s.queries.length ? table(s.queries,
        [["reported_term", "Term"], ["suspected_meddra_soc", "SOC"], ["severity", "Severity"],
         ["is_sae", "SAE"], ["reporting_timeline_hours", "Clock (h)"], ["resolution_status", "Status"]])
        : "<p class='muted'>No queries yet — run Safety triage first.</p>");
  } catch (err) { fail(el, err); }
}

async function runStartup() {
  const el = $("startupResult");
  try {
    const r = await getJSON("/api/startup");
    const sel = $("startupSite");
    if (!sel.options.length) {
      sel.innerHTML = r.sites.map((s) => '<option value="' + esc(s.site_id) + '">' +
        esc(s.site_name) + "</option>").join("");
    }
    el.innerHTML = "<h3>Pipeline as of " + esc(r.as_of) + "</h3>" +
      table(r.sites.map((s) => ({ site: s.site_name + " (" + s.country + ")", stage: s.stage,
        days: s.days_in_stage, total: s.days_since_identified,
        flags: s.flags.length ? s.flags.join("; ") : "—" })),
        [["site", "Site"], ["stage", "Stage"], ["days", "Days in stage"],
         ["total", "Days since ID"], ["flags", "Flags"]]) +
      "<p class='muted'>Benchmarks: contract ≤" + esc(r.benchmarks.contract_days) + "d, IRB ≤" +
      esc(r.benchmarks.irb_days) + "d, activation ≤" + esc(r.benchmarks.activation_days) +
      "d (~8 months). Flagged: " + esc(r.flagged_site_ids.join(", ") || "none") + "</p>";
  } catch (err) { fail(el, err); }
}

async function runMonitoring() {
  const el = $("monitoringResult");
  try {
    const r = await getJSON("/api/monitoring");
    el.innerHTML = r.sites.map((s) => {
      const badge = s.worst === "alert" ? "b-inelig" : (s.worst === "watch" ? "b-review" : "b-elig");
      return '<div class="record"><h3>' + esc(s.site_id) + ' <span class="badge ' + badge + '">' +
        esc(s.worst) + "</span></h3>" +
        table(s.kris.map((k) => ({ kri: k.kri, value: k.value, detail: k.detail, status: k.status })),
          [["kri", "KRI"], ["value", "Value"], ["detail", "Detail"], ["status", "Status"]]) +
        "<p>" + esc(s.action) + "</p></div>";
    }).join("") +
      "<p class='muted'>Alert sites: " + esc(r.alert_site_ids.join(", ") || "none") + ". " + esc(r.note) + "</p>";
  } catch (err) { fail(el, err); }
}
async function runFinder() {
  const el = $("finderResult");
  try {
    const sel = $("finderBundle");
    if (!sel.options.length) {
      sel.innerHTML = demoBundles.map((b, i) => '<option value="' + i + '">' + esc(b.name) + "</option>").join("");
    }
    const bundle = demoBundles[parseInt(sel.value || "0", 10)].bundle;
    const r = await postJSON("/api/find-trials", { bundle });
    el.innerHTML = "<h3>Ranked trials for " + esc(r.patient_id) + "</h3>" +
      r.ranked.map((t, i) =>
        '<div class="record"><h3>#' + (i + 1) + " " + esc(t.title) +
        ' <span class="badge ' + (COHORT_BADGE[t.status] || "") + '">' + esc(t.status) + "</span> " +
        '<span class="score">' + esc(t.match_percentage) + "%</span></h3>" +
        "<p class='muted'>" + esc(t.protocol_id) + " — " + esc(t.phase) + "</p>" +
        "<ul class='tight'>" + t.top_reasons.map((x) => "<li>" + esc(x) + "</li>").join("") + "</ul></div>").join("");
  } catch (err) { fail(el, err); }
}
async function runExternal() {
  const el = $("externalResult");
  try {
    const relax = $("relaxIds").value.split(",").map((s) => s.trim()).filter(Boolean);
    const r = await postJSON("/api/external-control",
      { protocol_id: "PROT-TNX-001", relax_ids: relax });
    el.innerHTML = "<h3>Comparator pool n=" + esc(r.pool.length) +
      " (near-miss n=" + esc(r.near_miss.length) + ")</h3>" +
      (r.pool.length ? table(r.pool,
        [["patient_id", "Patient"], ["strict_status", "Strict"], ["relaxed_status", "Relaxed"],
         ["match_percentage", "Match %"]]) : "<p class='muted'>Empty pool.</p>") +
      "<h3>Comparability: pool mix</h3>" +
      Object.entries(r.comparability.pool_mix || {}).map(([dim, rows]) =>
        "<h3>" + esc(dim) + "</h3>" + table(rows.map((x) => ({ group: x.group, n: x.n,
          actual: x.actual_pct + "%" })), [["group", "Group"], ["n", "n"], ["actual", "Share"]])).join("") +
      "<h3>Methods note</h3><p>" + esc(r.methods_note) + "</p>";
  } catch (err) { fail(el, err); }
}
$("monitoringForm").addEventListener("submit", (e) => { e.preventDefault(); runMonitoring(); });
$("finderForm").addEventListener("submit", (e) => { e.preventDefault(); runFinder(); });
$("externalForm").addEventListener("submit", (e) => { e.preventDefault(); runExternal(); });

async function runTwins() {
  const el = $("twinsResult");
  try {
    const sel = $("twinsBundle");
    if (!sel.options.length) {
      sel.innerHTML = demoBundles.map((b, i) => '<option value="' + i + '">' + esc(b.name) + "</option>").join("");
    }
    const bundle = demoBundles[parseInt(sel.value || "0", 10)].bundle;
    const r = await postJSON("/api/twins",
      { protocol_id: "PROT-TNX-001", bundle, n: parseInt($("twinsN").value, 10) || 500 });
    const mix = r.counts;
    el.innerHTML = "<h3>" + esc(r.n) + " twins (seed " + esc(r.seed) + ")</h3>" +
      "<p>Eligible <strong>" + esc(r.eligible_pct) + "%</strong> — eligible " +
      esc(mix.ELIGIBLE) + ", ineligible " + esc(mix.INELIGIBLE) + ", review " +
      esc(mix.REVIEW_REQUIRED) + "</p>" +
      "<p class='muted'>" + esc(r.note) + "</p>";
  } catch (err) { fail(el, err); }
}
async function runMcode() {
  const el = $("mcodeResult");
  try {
    const sel = $("mcodeBundle");
    if (!sel.options.length) {
      sel.innerHTML = demoBundles.map((b, i) => '<option value="' + i + '">' + esc(b.name) + "</option>").join("");
    }
    const bundle = demoBundles[parseInt(sel.value || "0", 10)].bundle;
    const r = await postJSON("/api/mcode", { bundle });
    const p = r.profile;
    el.innerHTML = "<h3>Oncology profile — " + esc(p.cancer_type) + "</h3>" +
      table([
        { k: "Stage", v: p.stage },
        { k: "Histology", v: p.histology },
        { k: "Biomarkers", v: p.biomarkers.join(", ") || "none" },
        { k: "ECOG", v: p.ecog },
        { k: "Metastasis sites", v: p.metastasis_sites.join(", ") || "none" },
      ], [["k", "Domain"], ["v", "Value"]]) +
      "<p>Completeness: <strong>" + esc(r.completeness_pct) + "%</strong>" +
      (r.gaps.length ? " — gaps: " + esc(r.gaps.join(", ")) : "") + "</p>" +
      "<p class='muted'>" + esc(r.note) + "</p>";
  } catch (err) { fail(el, err); }
}
async function runValidity() {
  const el = $("validityResult");
  try {
    const r = await getJSON("/api/n2c2-status");
    el.innerHTML = "<h3>n2c2 2018 cohort-selection benchmark</h3>" +
      "<p>Fixture micro-F1: <strong>" + esc(r.fixture_f1) + "</strong> (" +
      esc(r.criteria.length) + " criteria)</p>" +
      "<p>Real labeled notes: <strong>" + (r.real_data_present ? "present" : "not present") + "</strong></p>" +
      "<p class='muted'>" + esc(r.instructions) + "</p>";
  } catch (err) { fail(el, err); }
}
$("twinsForm").addEventListener("submit", (e) => { e.preventDefault(); runTwins(); });
$("mcodeForm").addEventListener("submit", (e) => { e.preventDefault(); runMcode(); });
$("validityForm").addEventListener("submit", (e) => { e.preventDefault(); runValidity(); });

/* Boot: snapshot, prefill, then auto-run all thirteen panels. */
loadSnapshot().then(loadDemo).then(loadDiversityDefaults).then(() => {
  runAudit(); runSites(); runDiversity(); runStartup(); runMonitoring(); runFinder(); runExternal();
  runTwins(); runMcode(); runValidity();
  Promise.all([runCohort(), runSafety()]).then(runHistory);
}).catch(() => {
  for (const id of ["auditResult", "sitesResult", "cohortResult", "safetyResult", "diversityResult", "historyResult", "startupResult", "monitoringResult", "finderResult", "externalResult", "twinsResult", "mcodeResult", "validityResult"]) {
    $(id).innerHTML = '<div class="error">API unreachable. Start it with: uvicorn backend.app:app --port 8000</div>';
  }
});
