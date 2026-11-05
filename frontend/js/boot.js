/* Boot: tabs, snapshot, form wiring, auto-run all thirteen panels. */
import { $, esc, fail, getJSON, postJSON } from "./api.js";
import { loadDemo, uploadedBundles } from "./data.js";
import {
  runAgingUpload,
  runAudit,
  runBudget,
  runCohort,
  runContraScreen,
  runCrfTrace,
  runDsur,
  runEscalation,
  runMilestones,
  runNiMargin,
  runNpi,
  runOutcomes,
  runPdf,
  runPower,
  runPrescreen,
  runPubmed,
  runRetention,
  runRiskRegister,
  runSaeNarrative,
  runSafety,
  runSignals,
  runSites,
  runSiv,
  runSweep,
} from "./panels-core.js";
import {
  loadDiversityDefaults,
  renderWatchlist,
  runCodeWhys,
  runCompetition,
  runDeviation,
  runDiversity,
  runDsmb,
  runExternal,
  runFinder,
  runForensics,
  runHistory,
  runInspection,
  runLetters,
  runLettersCheck,
  runMonitoring,
  runMonitoringPlan,
  runPortfolio,
  runPromoCheck,
  runTrialMatch,
  runVisitReport,
  watchCurrentSearch,
  runStartup,
} from "./panels-product.js";
import { runMcode, runTwins, runValidity } from "./panels-tier.js";

const TABS = ["audit", "sites", "cohort", "safety", "diversity", "history", "startup",
  "monitoring", "finder", "external", "twins", "mcode", "validity", "letters",
  "matcher"];
let activeTab = "audit";
const TAB_RUNNERS = {
  audit: () => { runAudit(); },
  sites: () => { runSites(); },
  cohort: () => { runCohort(); },
  safety: () => { runSafety(); },
  diversity: () => { runDiversity(); },
  history: () => { runHistory(); runForensics(); },
  startup: () => { runStartup(); },
  monitoring: () => { runMonitoring(); },
  finder: () => { runFinder(); },
  external: () => { runExternal(); },
  twins: () => { runTwins(); },
  mcode: () => { runMcode(); },
  validity: () => { runValidity(); },
  letters: () => { runLetters(); },
  matcher: () => { runTrialMatch(); },
};

/* Tabs (sidebar buttons + deep links) */
const tabBtns = TABS.map((n) => $("tabbtn-" + n));
function showTab(name, push) {
  if (!TABS.includes(name)) return;
  activeTab = name;
  const id = "tabbtn-" + name;
  tabBtns.forEach((b) => b.setAttribute("aria-selected", b.id === id ? "true" : "false"));
  TABS.forEach((n) => { $("tab-" + n).hidden = n !== name; });
  try {
    if (push !== false && typeof location !== "undefined" && location.hash !== "#/" + name) {
      location.hash = "#/" + name;
    }
    if (typeof sessionStorage !== "undefined") sessionStorage.setItem("tnx_tab", name);
  } catch (e) { /* private mode or stub DOM: selection still applies */ }
}
function initialTab() {
  try {
    if (typeof location !== "undefined" && location.hash) {
      const h = location.hash.replace(/^#\/?/, "");
      if (TABS.includes(h)) return h;
    }
    if (typeof sessionStorage !== "undefined") {
      const s = sessionStorage.getItem("tnx_tab");
      if (TABS.includes(s)) return s;
    }
  } catch (e) { /* fall through to default */ }
  return "audit";
}
tabBtns.forEach((btn) => btn.addEventListener("click", () => showTab(btn.id.replace("tabbtn-", ""))));

/* Cross-panel links: any [data-goto] switches to that tab. */
if (typeof document !== "undefined" && document.addEventListener) {
  document.addEventListener("click", (e) => {
    const t = e.target && e.target.closest ? e.target.closest("[data-goto]") : null;
    if (t) showTab(t.getAttribute("data-goto"));
  });
}

/* Global protocol field: one value shared by every panel. */
const PID_FIELDS = ["auditPid", "cohortPid", "safetyPid", "historyPid"];
const PID_SELECTS = ["globalPid", ...PID_FIELDS];
function fillPidSelects(protocols) {
  const ids = (protocols || []).map((p) => p.protocol_id);
  const want = readStoredPid() || "PROT-TNX-001";
  const pick = ids.includes(want) ? want : (ids[0] || "PROT-TNX-001");
  const opts = ids.map((id) =>
    '<option value="' + esc(id) + '">' + esc(id) + "</option>");
  for (const id of PID_SELECTS) {
    const el = $(id);
    if (!el || el.tagName !== "SELECT") continue;
    const extra = id === "safetyPid"
      ? '<option value="UNASSIGNED">UNASSIGNED</option>' : "";
    el.innerHTML = opts.join("") + extra;
  }
  applyPid(pick, false);
}
function readStoredPid() {
  try {
    if (typeof localStorage !== "undefined") return localStorage.getItem("tnx_pid") || "";
  } catch (e) { /* storage unavailable */ }
  return "";
}
function applyPid(pid, save) {
  for (const id of PID_FIELDS) {
    const el = $(id);
    if (el) el.value = pid;
  }
  const g = $("globalPid");
  if (g && g.value !== pid) g.value = pid;
  try {
    if (save && typeof localStorage !== "undefined") localStorage.setItem("tnx_pid", pid);
  } catch (e) { /* storage unavailable */ }
}

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
    const sub = $("snapSub");
    if (sub) sub.textContent = "Seeded demo: " + s.protocols + " protocols, " + s.sites +
      " sites, " + s.fhir_bundles + " FHIR patients, " + s.ae_records + " safety records.";
    try {
      await fillPidSelects(await getJSON("/api/protocols"));
    } catch (e) { /* keep seeded options when offline */ }
  } catch (err) {
    const pill = $("apiStatus");
    pill.textContent = "API offline";
    pill.classList.add("down");
    $("snapshot").innerHTML = '<div class="error">' + esc("API unreachable: " + err.message) + "</div>";
    throw err;
  }
}

/* Forms */
$("auditForm").addEventListener("submit", (e) => { e.preventDefault(); runAudit(); });
$("sitesForm").addEventListener("submit", (e) => { e.preventDefault(); runSites(); });
$("npiForm").addEventListener("submit", (e) => { e.preventDefault(); runNpi(); });
$("cohortForm").addEventListener("submit", (e) => { e.preventDefault(); runCohort(); });
$("safetyForm").addEventListener("submit", (e) => { e.preventDefault(); runSafety(); });
$("diversityForm").addEventListener("submit", (e) => { e.preventDefault(); runDiversity(); });
$("historyForm").addEventListener("submit", (e) => { e.preventDefault(); runHistory(); });
$("startupForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await postJSON("/api/startup/" + encodeURIComponent($("startupSite").value) + "/advance",
      { stage: $("startupStage").value, note: $("startupNote").value });
    runStartup();
  } catch (err) { fail($("startupResult"), err); }
});
$("monitoringForm").addEventListener("submit", (e) => { e.preventDefault(); runMonitoring(); });
$("finderForm").addEventListener("submit", (e) => { e.preventDefault(); runFinder(); });
$("externalForm").addEventListener("submit", (e) => { e.preventDefault(); runExternal(); });
$("twinsForm").addEventListener("submit", (e) => { e.preventDefault(); runTwins(); });
$("mcodeForm").addEventListener("submit", (e) => { e.preventDefault(); runMcode(); });
$("validityForm").addEventListener("submit", (e) => { e.preventDefault(); runValidity(); });
$("lettersForm").addEventListener("submit", (e) => { e.preventDefault(); runLettersCheck(); });
$("matcherForm").addEventListener("submit", (e) => { e.preventDefault(); runTrialMatch(); });
$("watchBtn").addEventListener("click", () => { watchCurrentSearch(); });
$("dsurBtn").addEventListener("click", () => { runDsur(); });
$("riskBtn").addEventListener("click", () => { runRiskRegister(); });
$("planBtn").addEventListener("click", () => { runMonitoringPlan(); });
$("milesBtn").addEventListener("click", () => { runMilestones(); });
$("sivBtn").addEventListener("click", () => { runSiv(); });
$("sweepForm").addEventListener("submit", (e) => { e.preventDefault(); runSweep(); });
$("retentionForm").addEventListener("submit", (e) => { e.preventDefault(); runRetention(); });
$("outcomesForm").addEventListener("submit", (e) => { e.preventDefault(); runOutcomes(); });
$("pdfForm").addEventListener("submit", (e) => { e.preventDefault(); runPdf(); });
$("pubmedForm").addEventListener("submit", (e) => { e.preventDefault(); runPubmed(); });
$("signalForm").addEventListener("submit", (e) => { e.preventDefault(); runSignals(); });
$("crfForm").addEventListener("submit", (e) => { e.preventDefault(); runCrfTrace(); });
$("powerForm").addEventListener("submit", (e) => { e.preventDefault(); runPower(); });
$("niForm").addEventListener("submit", (e) => { e.preventDefault(); runNiMargin(); });
$("budgetForm").addEventListener("submit", (e) => { e.preventDefault(); runBudget(); });
$("saeBtn").addEventListener("click", () => { runSaeNarrative(); });
$("escalBtn").addEventListener("click", () => { runEscalation(); });
$("contraForm").addEventListener("submit", (e) => { e.preventDefault(); runContraScreen(); });
$("promoForm").addEventListener("submit", (e) => { e.preventDefault(); runPromoCheck(); });
$("visitBtn").addEventListener("click", () => { runVisitReport(); });
$("whyForm").addEventListener("submit", (e) => { e.preventDefault(); runCodeWhys(); });
$("inspForm").addEventListener("submit", (e) => { e.preventDefault(); runInspection(); });
$("portBtn").addEventListener("click", () => { runPortfolio(); });
$("dsmbBtn").addEventListener("click", () => { runDsmb(); });
$("compForm").addEventListener("submit", (e) => { e.preventDefault(); runCompetition(); });
$("prescreenForm").addEventListener("submit", (e) => { e.preventDefault(); runPrescreen(); });
$("prescreenFiles").addEventListener("change", async (e) => {
  const files = [...(e.target.files || [])];
  uploadedBundles.length = 0;
  for (const f of files) {
    try {
      uploadedBundles.push({ name: f.name, bundle: JSON.parse(await f.text()) });
    } catch (err) { /* skip unreadable files */ }
  }
  $("prescreenUploadNote").textContent = uploadedBundles.length
    ? uploadedBundles.length + " uploaded bundle(s) added to the worklist pool."
    : "No uploads yet — using ticked demo bundles.";
});
$("devForm").addEventListener("submit", (e) => { e.preventDefault(); runDeviation(); });
$("devFile").addEventListener("change", async (e) => {
  const f = e.target.files && e.target.files[0];
  if (f) $("devJson").value = await f.text();
});
$("sitesFile").addEventListener("change", async (e) => {
  const f = e.target.files && e.target.files[0];
  if (f) $("sitesJson").value = await f.text();
});
$("aeFile").addEventListener("change", async (e) => {
  const f = e.target.files && e.target.files[0];
  if (f) $("aeJson").value = await f.text();
});
$("agingForm").addEventListener("submit", (e) => { e.preventDefault(); runAgingUpload(); });
$("agingFile").addEventListener("change", async (e) => {
  const f = e.target.files && e.target.files[0];
  if (f) $("agingJson").value = await f.text();
});
$("crfFile").addEventListener("change", async (e) => {
  const f = e.target.files && e.target.files[0];
  if (f) $("crfFields").value = await f.text();
});
async function loadInbox(slot, targetId, noteId) {
  const note = $(noteId);
  try {
    const r = await getJSON("/api/inbox/" + slot);
    $(targetId).value = r.text;
    if (note) note.textContent = "Loaded from your inbox.";
  } catch (err) {
    if (note) note.textContent = "Inbox empty — see data/inbox/README.md.";
  }
}
$("loadSites").addEventListener("click", () => loadInbox("sites", "sitesJson", "sitesNote"));
$("loadAe").addEventListener("click", () => loadInbox("ae", "aeJson", "aeNote"));
$("loadAging").addEventListener("click", () => loadInbox("queries", "agingJson", "agingNote"));
$("loadDev").addEventListener("click", () => loadInbox("visits", "devJson", "devNote"));
$("loadCrf").addEventListener("click", () => loadInbox("ecrf", "crfFields", "crfNote"));

/* Run-all workup: same deterministic chain as boot, with progress status. */
async function runAllWorkup() {
  const btn = $("runAllBtn");
  const status = $("runAllStatus");
  if (btn) btn.disabled = true;
  const say = (msg) => { if (status) status.textContent = msg; };
  try {
    say("Scoring sites…");
    await runSites();
    say("Matching cohort…");
    await runCohort();
    say("Triaging safety…");
    await runSafety();
    say("Auditing protocol…");
    await runAudit();
    say("Planning diversity…");
    await runDiversity();
    say("Refreshing operations…");
    await runStartup();
    await runMonitoring();
    say("Matching external evidence…");
    await runFinder();
    await runExternal();
    await runTwins();
    await runMcode();
    await runValidity();
    await runSweep();
    await runRetention();
    say("Summarizing history…");
    await runHistory();
    await runForensics();
    say("Workup complete.");
  } catch (err) {
    say("Workup stopped: one panel threw. See that panel for details.");
  } finally {
    if (btn) btn.disabled = false;
  }
}
const runAllBtn = $("runAllBtn");
if (runAllBtn) runAllBtn.addEventListener("click", () => { runAllWorkup(); });

/* Boot: snapshot, prefill, then auto-run all thirteen panels. */
showTab(initialTab(), false);
const g0 = $("globalPid");
if (g0) {
  const startPid = readStoredPid() || g0.value;
  if (startPid) applyPid(startPid, false);
  g0.addEventListener("change", (e) => {
    const v = e.target.value.trim();
    if (!v) return;
    applyPid(v, true);
    try {
      const rerun = TAB_RUNNERS[activeTab];
      if (rerun) rerun();
    } catch (err) { /* panel shows its own error state */ }
  });
}
loadSnapshot().then(loadDemo).then(loadDiversityDefaults).then(() => {
  runAudit(); runSites(); runDiversity(); runStartup(); runMonitoring(); runFinder(); runExternal();
  runTwins(); runMcode(); runValidity(); runLetters(); runTrialMatch(); renderWatchlist(); runSweep(); runRetention(); runOutcomes();
  Promise.all([runCohort(), runSafety()]).then(() => { runHistory(); runForensics(); });
}).catch(() => {
  for (const id of ["auditResult", "sitesResult", "cohortResult", "safetyResult", "diversityResult", "historyResult", "startupResult", "monitoringResult", "finderResult", "externalResult", "twinsResult", "mcodeResult", "validityResult", "lettersResult", "matcherResult", "sweepResult", "retentionResult", "forensicResult", "outcomesResult", "pubmedResult"]) {
    $(id).innerHTML = '<div class="error">API unreachable. Start it with: uvicorn backend.app:app --port 8000</div>';
  }
});
