/* Tier 1+2 panel runners: synthetic twins, mCODE summary, model validity. */
import { $, esc, fail, getJSON, postJSON } from "./api.js";
import { table } from "./ui.js";
import { demoBundles } from "./data.js";

export async function runTwins() {
  const el = $("twinsResult");
  try {
    const sel = $("twinsBundle");
    if (!sel.options.length) {
      sel.innerHTML = demoBundles.map((b, i) => '<option value="' + i + '">' + esc(b.name) + "</option>").join("");
    }
    const bundle = demoBundles[parseInt(sel.value || "0", 10)].bundle;
    const r = await postJSON("/api/twins",
      { protocol_id: "PROT-TNX-001", bundle, n: parseInt($("twinsN").value, 10) || 100,
        seed: parseInt($("twinsSeed").value, 10) || 0, jitter: parseFloat($("twinsJitter").value) || 0.15 });
    const mix = r.counts;
    const ci = r.eligible_ci95 || [];
    const flips = (r.flips || []).slice(0, 5);
    el.innerHTML = "<h3>" + esc(r.n) + " twins (seed " + esc(r.seed) + ", jitter ±" +
      esc(Math.round((r.jitter || 0.15) * 100)) + "%)</h3>" +
      "<p>Eligible <strong>" + esc(r.eligible_pct) + "%</strong>" +
      (ci.length === 2 ? " <span class='muted'>95% CI " + esc(ci[0]) + "–" + esc(ci[1]) +
        "%, MC-SE ±" + esc(r.mc_se) + "pp</span>" : "") +
      " — eligible " + esc(mix.ELIGIBLE) + ", ineligible " + esc(mix.INELIGIBLE) +
      ", review " + esc(mix.REVIEW_REQUIRED) + "</p>" +
      "<p>Index patient: <strong>" + esc(r.base_status || "?") + "</strong></p>" +
      (flips.length ? "<h4>Top flip drivers</h4>" + table(flips.map((f) => ({
        k: f.criterion_id + " (" + f.kind + ")",
        v: esc(f.flips) + " twins (" + esc((f.flip_rate * 100).toFixed(1)) + "%)",
      })), [["k", "Criterion"], ["v", "Verdict flips vs index"]]) : "") +
      "<p class='muted'>" + esc(r.note) + "</p>";
  } catch (err) { fail(el, err); }
}

export async function runMcode() {
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

export async function runValidity() {
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
