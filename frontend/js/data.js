/* Demo prefill payload + bundle selection state. */
import { $, esc, getJSON } from "./api.js";

export let demoBundles = [];

export async function loadDemo() {
  const d = await getJSON("/api/demo-data");
  $("sitesJson").value = JSON.stringify(d.sites, null, 1);
  $("aeJson").value = JSON.stringify(d.ae_records, null, 1);
  demoBundles = d.bundles;
  $("bundleList").innerHTML = d.bundles.map((b) =>
    '<label><input type="checkbox" checked data-name="' + esc(b.name) + '"> ' + esc(b.name) + "</label>").join("");
}

export function selectedBundles() {
  const checked = new Set([...$("bundleList").querySelectorAll("input:checked")].map((i) => i.dataset.name));
  return demoBundles.filter((b) => checked.has(b.name)).map((b) => b.bundle);
}

/* Coordinator-uploaded FHIR bundles (in-memory only, never stored). */
export let uploadedBundles = [];

export function selectedEntries() {
  const checked = new Set([...$("bundleList").querySelectorAll("input:checked")].map((i) => i.dataset.name));
  return demoBundles.filter((b) => checked.has(b.name)).map((b) => ({ name: b.name, bundle: b.bundle }));
}

export function prescreenEntries() {
  return [...selectedEntries(), ...uploadedBundles];
}

export function diversityBundles() {
  const sel = selectedBundles();
  return sel.length ? sel : demoBundles.map((b) => b.bundle);
}
