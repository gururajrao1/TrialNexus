/* Product panel runners: diversity, history, startup, monitoring, finder, external. */
import { $, esc, fail, getJSON, postJSON } from "./api.js";
import { COHORT_BADGE, busy, table } from "./ui.js";
import { demoBundles, diversityBundles, selectedExtBundles } from "./data.js";

export async function loadDiversityDefaults() {
  const d = await getJSON("/api/diversity-defaults");
  $("diversityTargets").value = JSON.stringify(d.targets, null, 1);
}

export async function runDiversity() {
  const el = $("diversityResult");
  busy(el);
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
  busy(el);
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
  busy(el);
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
  busy(el);
  try {
    const r = await getJSON("/api/monitoring");
    el.innerHTML = r.sites.map((s) => {
      const badge = s.worst === "alert" ? "b-inelig" : (s.worst === "watch" ? "b-review" : "b-elig");
      const z = s.zero_enroll || { score: 0, band: "low", factors: [], trend: null };
      const tr = z.trend
        ? "Trend: <strong>" + esc(z.trend.direction) + "</strong> (Cox-Stuart p=" +
          esc(z.trend.p_value) + ", " + esc(z.trend.n_pairs) + " pairs)"
        : "";
      const zb = z.band === "high" ? "b-inelig" : (z.band === "elevated" ? "b-review" : "b-elig");
      return '<div class="record"><h3>' + esc(s.site_id) + ' <span class="badge ' + badge + '">' +
        esc(s.worst) + "</span> " +
        '<span class="badge ' + zb + '">zero-enroll ' + esc(z.band) + " " + esc(z.score) + "</span></h3>" +
        table(s.kris.map((k) => ({ kri: k.kri, value: k.value, detail: k.detail, status: k.status })),
          [["kri", "KRI"], ["value", "Value"], ["detail", "Detail"], ["status", "Status"]]) +
        "<p class='muted'>Zero-enroll risk: " + esc((z.factors || []).join("; ")) +
          (tr ? " — " + tr : "") + "</p>" +
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
  busy(el);
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

export async function runTrialMatch() {
  const el = $("matcherResult");
  busy(el);
  try {
    const description = $("matcherText").value.trim();
    if (!description) {
      el.innerHTML = "<p class='muted'>Describe the patient's condition first.</p>";
      return;
    }
    const useModel = $("matcherModel").checked;
    const r = await postJSON("/api/trial-match", {
      description,
      condition: $("matcherCondition").value.trim(),
      location: $("matcherLocation").value.trim(),
      model_explain: useModel,
      model_rerank: useModel,
    });
    if (!r.trials.length) {
      el.innerHTML = "<p class='muted'>No recruiting trials found (" +
        esc(r.source) + " search over " + esc(r.total_recruiting) +
        "). Try fewer details or another condition.</p>";
      return;
    }
    el.innerHTML = "<h3>" + esc(r.trials.length) + " top matches " +
      "<span class='muted'>(" + esc(r.total_recruiting) + " recruiting, " +
      esc(r.source) + " · " + esc(r.explain_source || "template") + " notes" +
      (r.reranked ? " · model re-ranked" : "") + ")</span></h3>" +
      (r.searched_terms ? "<p class='muted'>Searched: " + esc(r.searched_terms) +
        (r.widened ? " — no hits near " + esc($("matcherLocation").value.trim()) +
          ", widened beyond your location" : "") + "</p>" : "") +
      ((r.model_warnings || []).length ? "<p class='muted'>Model checks: " +
        esc(r.model_warnings.join(", ")) + " — templates stood in.</p>" : "") +
      r.trials.map((t, i) =>
        '<div class="record"><h3>#' + (i + 1) + " " + esc(t.title) +
        ' <span class="badge ' + (t.verdict === "worth discussing" ? "b-elig" : "b-review") +
        '">' + esc(t.verdict) + "</span> " +
        '<span class="score">' + esc(t.score) + "%</span></h3>" +
        "<p class='muted'>" +
        (t.url ? "<a href='" + esc(t.url) + "' target='_blank' rel='noopener'>" +
          esc(t.nct_id) + "</a>" : esc(t.nct_id)) +
        " — " + esc(t.phase) + " — " + esc(t.status) +
        (t.locations.length ? " — " + esc(t.locations.slice(0, 3).join("; ")) : "") + "</p>" +
        "<p>" + esc(t.summary) + "</p>" +
        (t.rerank_reason ? "<p><strong>Why this rank:</strong> " +
          esc(t.rerank_reason) + "</p>" : "") +
        "<ul class='tight'>" + t.notes.map((n) =>
          "<li><strong>" + esc(n.verdict) + ":</strong> " + esc(n.plain) +
          (n.draft ? " <span class='chip'>AI draft</span>" : "") +
          " <span class='muted'>“" + esc(n.quote) + "”</span></li>").join("") +
        "</ul></div>").join("") +
      "<p class='muted'>" + esc(r.disclaimer) + "</p>";
  } catch (err) { fail(el, err); }
}

export async function runExternal() {
  const el = $("externalResult");
  busy(el);
  try {
    const relax = $("relaxIds").value.split(",").map((s) => s.trim()).filter(Boolean);
    const r = await postJSON("/api/external-control",
      { protocol_id: "PROT-TNX-001", relax_ids: relax,
        bundles: selectedExtBundles() });
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
  busy(el);
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
  busy(el);
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
      ((r.site_signals || []).length ? "<h3>Rate signals vs portfolio</h3>" +
        '<table class="grid"><thead><tr><th>Site</th><th>Affected</th>' +
        "<th>Portfolio</th><th>p-value</th></tr></thead><tbody>" +
        (r.site_signals || []).map((s) =>
          "<tr><td>" + esc(s.site_id) +
          (s.flag ? " <span class='badge b-review'>rate signal</span>" : "") + "</td>" +
          "<td>" + esc((s.rate * 100).toFixed(1)) + "% (" +
          esc(s.n_affected) + "/" + esc(s.n_visits) + ")</td>" +
          "<td>" + esc((s.background_rate * 100).toFixed(1)) + "%</td>" +
          "<td>" + esc(s.p_value) + "</td></tr>").join("") +
        "</tbody></table>" : "") +
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

const TIER_BADGE = { critical: "b-inelig", major: "b-review", minor: "b-elig" };

export async function runLetters() {
  const el = $("lettersResult");
  busy(el);
  try {
    const r = await getJSON("/api/warning-letters");
    if (!r.count) {
      el.innerHTML = "<p class='muted'>" + esc(r.note) + "</p>";
      return;
    }
    el.innerHTML = "<h3>" + esc(r.count) + " letter(s) indexed</h3>" +
      '<table class="grid"><thead><tr><th>Firm</th><th>Date</th><th>Office</th>' +
      "<th>Violation themes</th><th>Charges</th></tr></thead><tbody>" +
      r.letters.map((l) =>
        "<tr><td>" + esc(l.firm) +
        (l.cms ? "<br><span class='muted'>CMS #" + esc(l.cms) + "</span>" : "") + "</td>" +
        "<td>" + esc(l.date || "—") + "</td>" +
        "<td>" + esc(l.office || "—") + "</td>" +
        "<td>" + (l.themes || []).map((t) =>
          "<span class='chip'>" + esc(t.replace(/_/g, " ")) + "</span>").join(" ") + "</td>" +
        "<td>" + esc(l.n_violations) + "</td></tr>").join("") +
      "</tbody></table>" +
      "<p class='muted'>" + esc(r.note) + "</p>";
  } catch (err) { fail(el, err); }
}

export async function runLettersCheck() {
  const el = $("lettersCheckResult");
  busy(el);
  try {
    const txt = $("lettersText").value.trim();
    if (!txt) {
      el.innerHTML = "<p class='muted'>Describe a finding first.</p>";
      return;
    }
    const r = await postJSON("/api/warning-letters/check", { text: txt });
    if (!r.matches.length) {
      el.innerHTML = "<p class='muted'>No indexed violation resembles this finding — " +
        "nothing in " + esc(r.n_letters) + " letter(s) shares its themes or terms.</p>";
      return;
    }
    el.innerHTML = r.matches.map((m, i) =>
      "<h3>#" + (i + 1) + " " + esc(m.firm) +
      ' <span class="badge ' + (TIER_BADGE[m.suggested_tier] || "b-review") + '">' +
      esc(m.suggested_tier) + "</span></h3>" +
      "<p class='muted'>" + (m.cms ? "CMS #" + esc(m.cms) + " · " : "") +
      esc(m.date || "undated") + " · " +
      (m.matched_themes || []).map((t) => '<span class="chip">' + esc(t.label) + "</span>").join(" ") + "</p>" +
      "<blockquote>" + esc((m.excerpt || "").slice(0, 500)) + "</blockquote>" +
      ((m.trial_actions || []).length ? "<p><strong>Trial analogue:</strong> " +
        esc(m.trial_actions.join("; ")) + "</p>" : "") +
      ((m.panels || []).length ? "<p><button type='button' data-goto='" + esc(m.panels[0]) +
        "'>Open the owning panel</button></p>" : "")
    ).join("");
  } catch (err) { fail(el, err); }
}
