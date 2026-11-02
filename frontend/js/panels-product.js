/* Product panel runners: diversity, history, startup, monitoring, finder, external. */
import { $, esc, fail, getJSON, postJSON } from "./api.js";
import { COHORT_BADGE, table } from "./ui.js";
import { demoBundles, diversityBundles } from "./data.js";

export async function loadDiversityDefaults() {
  const d = await getJSON("/api/diversity-defaults");
  $("diversityTargets").value = JSON.stringify(d.targets, null, 1);
}

export async function runDiversity() {
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

export async function runHistory() {
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

export async function runStartup() {
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

export async function runMonitoring() {
  const el = $("monitoringResult");
  try {
    const r = await getJSON("/api/monitoring");
    el.innerHTML = r.sites.map((s) => {
      const badge = s.worst === "alert" ? "b-inelig" : (s.worst === "watch" ? "b-review" : "b-elig");
      const z = s.zero_enroll || { score: 0, band: "low", factors: [] };
      const zb = z.band === "high" ? "b-inelig" : (z.band === "elevated" ? "b-review" : "b-elig");
      return '<div class="record"><h3>' + esc(s.site_id) + ' <span class="badge ' + badge + '">' +
        esc(s.worst) + "</span> " +
        '<span class="badge ' + zb + '">zero-enroll ' + esc(z.band) + " " + esc(z.score) + "</span></h3>" +
        table(s.kris.map((k) => ({ kri: k.kri, value: k.value, detail: k.detail, status: k.status })),
          [["kri", "KRI"], ["value", "Value"], ["detail", "Detail"], ["status", "Status"]]) +
        "<p class='muted'>Zero-enroll risk: " + esc(z.factors.join("; ")) + "</p>" +
        "<p>" + esc(s.action) + "</p></div>";
    }).join("") +
      "<p class='muted'>Alert sites: " + esc(r.alert_site_ids.join(", ") || "none") + ". " + esc(r.note) + "</p>";
    const csm = await getJSON("/api/csm");
    el.innerHTML += "<h3>Centralized statistical monitoring</h3>" +
      csm.sites.map((s) =>
        "<p><strong>" + esc(s.site_id) + "</strong> — " + esc(s.n_flagged) + " flags</p>" +
        (s.n_flagged ? table(s.signals.filter((x) => x.flag).map((x) =>
          ({ kri: x.kri, rate: x.rate + " (pool " + x.pooled + ")", z: x.z,
             p: "hi " + x.p_high + " / lo " + x.p_low, funnel: x.funnel,
             dir: x.direction })),
          [["kri", "KRI"], ["rate", "Rate"], ["z", "z"], ["p", "Poisson p"],
           ["funnel", "Funnel"], ["dir", "Direction"]]) : "")
      ).join("") +
      "<p class='muted'>" + esc(csm.basis) + "</p>";
  } catch (err) { fail(el, err); }
}

export async function runFinder() {
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

export async function runExternal() {
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

export async function runForensics() {
  const el = $("forensicResult");
  try {
    const pid = $("historyPid").value.trim();
    const q = pid ? "?protocol_id=" + encodeURIComponent(pid) : "";
    const r = await getJSON("/api/forensics" + q);
    if (!r.n_evaluations) {
      el.innerHTML = "<p class='muted'>No stored evaluations yet — run Cohort matching first.</p>";
      return;
    }
    el.innerHTML = "<h3>Top screen-failure drivers (" + esc(r.n_evaluations) + " runs)</h3>" +
      table(r.top_drivers, [["criterion_id", "Criterion"], ["kind", "Kind"], ["rate", "Rate %"], ["n", "n"]]) +
      "<h3>Inclusion fail / missing rates</h3>" +
      table(r.inclusions, [["criterion_id", "ID"], ["fail_rate", "Fail %"], ["missing_rate", "Missing %"], ["n", "n"]]) +
      "<h3>Exclusion trigger rates</h3>" +
      table(r.exclusions, [["criterion_id", "ID"], ["trigger_rate", "Trigger %"], ["n", "n"]]) +
      "<p class='muted'>" + esc(r.note) + "</p>";
  } catch (err) { fail(el, err); }
}


export async function runDeviation() {
  const el = $("devResult");
  try {
    const txt = $("devJson").value.trim();
    if (!txt) {
      el.innerHTML = "<p class='muted'>Upload a visit file or paste records first.</p>";
      return;
    }
    const w = parseInt($("devWindow").value, 10) || 0;
    const r = await postJSON("/api/deviation-watch",
      { records: JSON.parse(txt), window_days: w });
    el.innerHTML = "<h3>" + esc(r.summary.n_findings) + " findings over " +
      esc(r.summary.n_records) + " visits " +
      '<span class="chip">' + esc(r.summary.n_sites_flagged) + " sites flagged</span></h3>" +
      (r.by_site.length ? table(r.by_site.map((s) => ({
        site: s.site_id, tier: s.tier, n: s.n_findings,
      })), [["site", "Site"], ["tier", "SDV tier"], ["n", "Findings"]]) : "") +
      (r.findings.length ? table(r.findings.map((f) => ({
        site: f.site_id, subj: f.subject, visit: f.visit, type: f.type,
        sev: f.severity, late: f.days_late, detail: f.detail,
      })), [["site", "Site"], ["subj", "Subject"], ["visit", "Visit"],
        ["type", "Type"], ["sev", "Severity"], ["late", "Days late"],
        ["detail", "Detail"]])
        : "<p class='muted'>No deviations in this upload.</p>") +
      "<p class='muted'>" + esc(r.basis) + "</p>";
  } catch (err) { fail(el, err); }
}
