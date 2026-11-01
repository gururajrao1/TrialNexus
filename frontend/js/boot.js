/* Boot: tabs, snapshot, form wiring, auto-run all thirteen panels. */
import { $, esc, fail, getJSON, postJSON } from "./api.js";
import { loadDemo } from "./data.js";
import {
  runAudit,
  runCohort,
  runOutcomes,
  runRetention,
  runSafety,
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

/* Tabs */
const tabBtns = TABS.map((n) => $("tabbtn-" + n));
tabBtns.forEach((btn) => btn.addEventListener("click", () => {
  tabBtns.forEach((b) => b.setAttribute("aria-selected", b === btn ? "true" : "false"));
  TABS.forEach((n) => { $("tab-" + n).hidden = ("tabbtn-" + n) !== btn.id; });
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

/* Boot: snapshot, prefill, then auto-run all thirteen panels. */
loadSnapshot().then(loadDemo).then(loadDiversityDefaults).then(() => {
  runAudit(); runSites(); runDiversity(); runStartup(); runMonitoring(); runFinder(); runExternal();
  runTwins(); runMcode(); runValidity(); runSweep(); runRetention();
  Promise.all([runCohort(), runSafety()]).then(() => { runHistory(); runForensics(); });
}).catch(() => {
  for (const id of ["auditResult", "sitesResult", "cohortResult", "safetyResult", "diversityResult", "historyResult", "startupResult", "monitoringResult", "finderResult", "externalResult", "twinsResult", "mcodeResult", "validityResult", "sweepResult", "retentionResult", "forensicResult", "outcomesResult"]) {
    $(id).innerHTML = '<div class="error">API unreachable. Start it with: uvicorn backend.app:app --port 8000</div>';
  }
});
