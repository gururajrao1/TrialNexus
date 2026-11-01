/* Tables, badges, criterion renderers. */
import { esc } from "./api.js";

export function table(rows, cols) {
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

export function preJSON(obj) {
  return '<pre class="json">' + esc(JSON.stringify(obj, null, 1)) + "</pre>";
}

export const SITE_BADGE = { GO: "b-go", CONDITIONAL: "b-cond", "NO-GO": "b-nogo" };
export const COHORT_BADGE = { ELIGIBLE: "b-elig", INELIGIBLE: "b-inelig", REVIEW_REQUIRED: "b-review" };

export function critTable(rows) {
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

export function evalTable(rows, isExclusion) {
  let h = '<table class="grid"><thead><tr><th>ID</th><th>Outcome</th><th>Evidence</th><th>Signal</th></tr></thead><tbody>';
  for (const e of rows) {
    const bad = isExclusion ? e.triggered : !e.passed;
    const outcome = e.missing_data ? "<span class='miss'>NEEDS DATA</span>"
      : (bad ? "<span class='fail'>" + (isExclusion ? "TRIGGERED" : "FAIL") + "</span>"
             : "<span class='pass'>" + (isExclusion ? "CLEAR" : "PASS") + "</span>");
    h += "<tr><td class='mono'>" + esc(e.criterion_id) + "</td><td>" + outcome + "</td><td>" +
      esc(e.clinical_evidence_found) + "</td><td><span class='chip'>" +
      esc(((e.provenance || {}).match_type || "—") + "/" + ((e.provenance || {}).confidence || "—")) +
      "</span></td></tr>";
  }
  return h + "</tbody></table>";
}
