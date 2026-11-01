/* Boot: tabs, snapshot, form wiring, auto-run all thirteen panels. */
import { $, esc, fail, getJSON, postJSON } from "./api.js";
import { loadDemo } from "./data.js";
import {
  runAudit,
  runCohort,
  runOutcomes,
  runPdf,
  runPubmed,
  runRetention,
  runSafety,
  runSignals,
  runSites,
  runSweep,
} from "./panels-core.js";
import {
  loadDiversityDefaults,
  runDiversity,
  runExternal,
  runFinder,
  runForensics,
  runHistory,
  runMonitoring,
  runStartup,
} from "./panels-product.js";
import { runMcode, runTwins, runValidity } from "./panels-tier.js";

const TABS = ["audit", "sites", "cohort", "safety", "diversity", "history", "startup",
  "monitoring", "finder", "external", "twins", "mcode", "validity"];

/* Tabs (sidebar buttons + deep links) */
const tabBtns = TABS.map((n) => $("tabbtn-" + n));
function showTab(name, push) {
  if (!TABS.includes(name)) return;
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
$("sweepForm").addEventListener("submit", (e) => { e.preventDefault(); runSweep(); });
$("retentionForm").addEventListener("submit", (e) => { e.preventDefault(); runRetention(); });
$("outcomesForm").addEventListener("submit", (e) => { e.preventDefault(); runOutcomes(); });
$("pdfForm").addEventListener("submit", (e) => { e.preventDefault(); runPdf(); });
$("pubmedForm").addEventListener("submit", (e) => { e.preventDefault(); runPubmed(); });
$("signalForm").addEventListener("submit", (e) => { e.preventDefault(); runSignals(); });

/* Boot: snapshot, prefill, then auto-run all thirteen panels. */
showTab(initialTab(), false);
const g0 = $("globalPid");
if (g0) {
  const startPid = readStoredPid() || g0.value;
  if (startPid) applyPid(startPid, false);
  g0.addEventListener("input", (e) => {
    const v = e.target.value.trim();
    if (v) applyPid(v, true);
  });
}
loadSnapshot().then(loadDemo).then(loadDiversityDefaults).then(() => {
  runAudit(); runSites(); runDiversity(); runStartup(); runMonitoring(); runFinder(); runExternal();
  runTwins(); runMcode(); runValidity(); runSweep(); runRetention();
  Promise.all([runCohort(), runSafety()]).then(() => { runHistory(); runForensics(); });
}).catch(() => {
  for (const id of ["auditResult", "sitesResult", "cohortResult", "safetyResult", "diversityResult", "historyResult", "startupResult", "monitoringResult", "finderResult", "externalResult", "twinsResult", "mcodeResult", "validityResult", "sweepResult", "retentionResult", "forensicResult", "outcomesResult", "pubmedResult"]) {
    $(id).innerHTML = '<div class="error">API unreachable. Start it with: uvicorn backend.app:app --port 8000</div>';
  }
});
