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

export let lastMatcherTrials = [];

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
    lastMatcherTrials = r.trials || [];
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
        ((t.snapshot || []).length ? "<ul class='tight'>" +
          t.snapshot.map((s) => "<li>" + esc(s) + "</li>").join("") + "</ul>" : "") +
        (t.rerank_reason ? "<p><strong>Why this rank:</strong> " +
          esc(t.rerank_reason) + "</p>" : "") +
        "<p class='muted'>" + esc(((t.travel || {}).note) || "") + "</p>" +
        "<ul class='tight'>" + t.notes.map((n) =>
          "<li><strong>" + esc(n.verdict) + ":</strong> " + esc(n.plain) +
          (n.draft ? " <span class='chip'>AI draft</span>" : "") +
          " <span class='muted'>“" + esc(n.quote) + "”</span></li>").join("") +
        "</ul>" +
        "<p><button type='button' data-mact='referral' data-idx='" + i + "'>Referral letter</button> " +
        "<button type='button' data-mact='questions' data-idx='" + i + "'>Screening questions</button></p>" +
        "<div class='extra' id='mx-" + i + "'></div>" +
        "</div>").join("") +
      "<p class='muted'>" + esc(r.disclaimer) + "</p>";
    wireMatcherActions(el, description);
  } catch (err) { fail(el, err); }
}

const WATCH_KEY = "tnx-watch";

function getWatch() {
  try {
    const list = JSON.parse(localStorage.getItem(WATCH_KEY));
    return Array.isArray(list) ? list : [];
  } catch (e) { return []; }
}

function setWatch(list) {
  try { localStorage.setItem(WATCH_KEY, JSON.stringify(list)); } catch (e) {}
}

export function renderWatchlist() {
  const el = $("watchResult");
  if (!el) return;
  const list = getWatch();
  if (!list.length) {
    el.innerHTML = "<p class='muted'>None yet — describe a patient and watch the search.</p>";
    return;
  }
  el.innerHTML = "<ul class='tight'>" + list.map((w, i) =>
    "<li>" + esc(w.description) +
    (w.last_total != null ? " <span class='muted'>— last check: " +
      esc(w.last_total) + " matches" +
      (w.last_check ? " on " + esc(w.last_check) : "") + "</span>" : "") +
    " <button type='button' data-wact='run' data-widx='" + i + "'>Run</button>" +
    " <button type='button' data-wact='drop' data-widx='" + i + "'>Remove</button></li>"
  ).join("") + "</ul>";
  el.querySelectorAll("[data-wact]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const idx = Number(btn.getAttribute("data-widx"));
      const items = getWatch();
      const entry = items[idx];
      if (!entry) return;
      if (btn.getAttribute("data-wact") === "drop") {
        items.splice(idx, 1);
        setWatch(items);
        renderWatchlist();
        return;
      }
      $("matcherText").value = entry.description || "";
      $("matcherCondition").value = entry.condition || "";
      $("matcherLocation").value = entry.location || "";
      await runTrialMatch();
      const fresh = getWatch();
      if (fresh[idx]) {
        fresh[idx].last_total = lastMatcherTrials.length;
        fresh[idx].last_check = new Date().toISOString().slice(0, 10);
        setWatch(fresh);
        renderWatchlist();
      }
    });
  });
}

export function watchCurrentSearch() {
  const description = $("matcherText").value.trim();
  if (!description) return;
  const list = getWatch();
  if (!list.some((w) => w.description === description)) {
    list.push({
      description,
      condition: $("matcherCondition").value.trim(),
      location: $("matcherLocation").value.trim(),
      last_total: null,
      last_check: null,
    });
    setWatch(list);
  }
  renderWatchlist();
}

function wireMatcherActions(el, description) {
  el.querySelectorAll("[data-mact]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const idx = Number(btn.getAttribute("data-idx"));
      const trial = lastMatcherTrials[idx];
      const out = $("mx-" + idx);
      if (!trial || !out) return;
      out.innerHTML = "<p class='muted'>Working…</p>";
      try {
        if (btn.getAttribute("data-mact") === "referral") {
          const r = await postJSON("/api/trial-referral",
            { trial, description, patient_label: "the patient" });
          out.innerHTML = "<h3>Referral letter</h3><pre class='mono'>" +
            esc(r.letter) + "</pre>";
        } else {
          const r = await postJSON("/api/trial-questions", { trial });
          out.innerHTML = "<h3>Screening checklist</h3><ul class='tight'>" +
            r.questions.map((q) =>
              "<li><strong>" + esc(q.kind) + ":</strong> " + esc(q.question) +
              "</li>").join("") + "</ul>";
        }
      } catch (err) { fail(out, err); }
    });
  });
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


export let lastMonitoringTiers = [];

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
    lastDevFindings = r.findings || [];
    lastDevTiers = r.by_site || [];
    lastMonitoringTiers = (r.by_site || []).map((s) => ({
      site_id: s.site_id, tier: s.tier,
      reason: (s.n_findings || 0) + " finding(s) this screen",
    }));
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

export async function runMonitoringPlan() {
  const el = $("planResult");
  busy(el);
  try {
    if (!lastMonitoringTiers.length) {
      el.innerHTML = "<p class='muted'>Screen deviations above first — the plan is built from scored tiers.</p>";
      return;
    }
    const pid = ($("globalPid") && $("globalPid").textContent.trim()) || "UNASSIGNED";
    const r = await postJSON("/api/monitoring-plan", {
      protocol: { id: pid },
      site_tiers: lastMonitoringTiers,
    });
    el.innerHTML = "<pre class='mono'>" + esc(r.markdown) + "</pre>";
  } catch (err) { fail(el, err); }
}

const TIER_BADGE = { critical: "b-inelig", major: "b-review", minor: "b-elig" };

export let lastDevFindings = [];
export let lastDevTiers = [];

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

export async function runPromoCheck() {
  const el = $("promoResult");
  busy(el);
  try {
    const draft = $("promoDraft").value.trim();
    if (!draft) {
      el.innerHTML = "<p class='muted'>Paste the draft copy first.</p>";
      return;
    }
    const r = await postJSON("/api/promo-check",
      { draft, indication: $("promoIndication").value });
    const badge = r.verdict === "no lexical flags" ? "b-elig" : "b-review";
    el.innerHTML = "<h3>Verdict: " + esc(r.verdict) + ' <span class="badge ' + badge + '">' +
      esc(r.flags.length) + " flag(s)</span></h3>" +
      (r.flags.length ? "<ul class='tight'>" + r.flags.map((f) =>
        "<li><strong>" + esc(f.kind) + ":</strong> " + esc(f.text) +
        "<br><span class='muted'>" + esc(f.note) + "</span></li>").join("") + "</ul>"
        : "<p class='muted'>Nothing in the draft falls outside the indication.</p>") +
      "<p class='muted'>" + esc(r.basis) + "</p>";
  } catch (err) { fail(el, err); }
}

export async function runVisitReport() {
  const el = $("visitResult");
  busy(el);
  try {
    if (!lastDevFindings.length) {
      el.innerHTML = "<p class='muted'>Screen deviations above first — the report is built from screened findings.</p>";
      return;
    }
    const tier = (lastDevTiers[0] && { site_id: lastDevTiers[0].site_id, tier: lastDevTiers[0].tier }) || null;
    const r = await postJSON("/api/visit-report",
      { findings: lastDevFindings, site_tier: tier });
    el.innerHTML = "<h3>" + esc(r.n_findings) + " finding(s)" +
      (tier ? " — " + esc(tier.site_id) + " tier " + esc(tier.tier) : "") + "</h3>" +
      "<pre class='mono'>" + esc(r.markdown) + "</pre>";
  } catch (err) { fail(el, err); }
}

export async function runCodeWhys() {
  const el = $("whyResult");
  busy(el);
  try {
    const t = $("whyType").value.trim();
    const detail = $("whyDetail").value.trim();
    if (!t) {
      el.innerHTML = "<p class='muted'>Enter a deviation type first.</p>";
      return;
    }
    const [code, whys] = await Promise.all([
      postJSON("/api/code-deviation", { deviation_type: t, detail }),
      postJSON("/api/five-whys", { deviation_type: t, detail }),
    ]);
    el.innerHTML = "<h3>" + esc(code.type) + " → <span class='mono'>" +
      esc(code.cdisc_code) + "</span> " + esc(code.cdisc_label) + "</h3>" +
      "<p class='muted'>" + esc(code.basis) + "</p><ol class='tight'>" +
      whys.questions.map((q) => "<li>" + esc(q) + "</li>").join("") + "</ol>" +
      "<p><strong>Effectiveness check:</strong> " + esc(whys.effectiveness_check) + "</p>" +
      "<p class='muted'>" + esc(whys.basis) + "</p>";
  } catch (err) { fail(el, err); }
}

export async function runInspection() {
  const el = $("inspResult");
  busy(el);
  try {
    const r = await postJSON("/api/inspection-pack", {
      protocol_id: $("inspPid").value.trim(),
      n_deviations: parseInt($("inspDev").value, 10) || 0,
      open_items: $("inspOpen").value.split("\n").map((s) => s.trim()).filter(Boolean),
    });
    const ready = r.ready ? "b-elig" : "b-review";
    el.innerHTML = "<h3>Inspection pack — " + esc(r.protocol_id) +
      ' <span class="badge ' + ready + '">' + (r.ready ? "compiled exhibits ready" : "TMF items open") +
      "</span></h3>" +
      table(r.exhibits.map((e) => ({ exhibit: e.exhibit, status: e.status, detail: e.detail || "—" })),
        [["exhibit", "Exhibit"], ["status", "Status"], ["detail", "Detail"]]) +
      (r.open_items.length ? "<h3>Open items</h3><ul class='tight'>" +
        r.open_items.map((o) => "<li>" + esc(o) + "</li>").join("") + "</ul>" : "") +
      "<p class='muted'>" + esc(r.basis) + "</p>";
  } catch (err) { fail(el, err); }
}

export async function runPortfolio() {
  const el = $("portResult");
  busy(el);
  try {
    const r = await getJSON("/api/portfolio");
    el.innerHTML = "<h3>" + esc(r.n_protocols) + " protocol(s)</h3>" +
      (r.protocols.length ? table(r.protocols.map((p) => ({
        pid: p.protocol_id, title: (p.title || "").slice(0, 60), phase: p.phase,
        queries: p.queries + " (" + p.open_queries + " open)", evals: p.evaluations,
      })), [["pid", "Protocol"], ["title", "Title"], ["phase", "Phase"],
        ["queries", "Queries"], ["evals", "Evaluations"]])
        : "<p class='muted'>No protocols in the database yet.</p>");
  } catch (err) { fail(el, err); }
}

export async function runDsmb() {
  const el = $("portResult");
  busy(el);
  try {
    const pid = ($("historyPid") && $("historyPid").value.trim()) || "PROT-TNX-001";
    const r = await postJSON("/api/dsmb-pack", { protocol_id: pid });
    el.innerHTML = "<h3>DSMB pack — " + esc(r.protocol_id) +
      " <span class='muted'>(" + esc(r.n_sites) + " sites, " +
      esc(r.n_activated) + " activated)</span></h3>" +
      "<pre class='mono'>" + esc(r.markdown) + "</pre>";
  } catch (err) { fail(el, err); }
}

export async function runCompetition() {
  const el = $("compResult");
  busy(el);
  try {
    el.innerHTML = "<p class='muted'>Checking live registry…</p>";
    const r = await postJSON("/api/competition-alerts", {
      threshold: parseInt($("compThreshold").value, 10) || 20,
      country: $("compCountry").value.trim() || "United States",
    });
    el.innerHTML = r.alerts.length
      ? "<h3>" + esc(r.alerts.length) + " alert(s) at ≥" + esc(r.threshold) +
        " recruiting <span class='chip'>" + esc(r.country) + "</span></h3>" +
        table(r.alerts.map((a) => ({
          pid: a.protocol_id, ind: (a.indication || "").slice(0, 60),
          n: a.recruiting_competitors, src: a.source,
        })), [["pid", "Protocol"], ["ind", "Indication"],
          ["n", "Recruiting"], ["src", "Source"]])
      : "<p class='muted'>No indication at or above the threshold — clear field.</p>";
  } catch (err) { fail(el, err); }
}
