/* Shared fetch + DOM helpers. */
export const $ = (id) => document.getElementById(id);

export function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

export async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + " → HTTP " + r.status);
  return r.json();
}

export async function postJSON(path, payload) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(path + " → HTTP " + r.status);
  return r.json();
}

export function fail(el, err) {
  el.innerHTML = '<div class="error">' + esc("Failed: " + err.message) + "</div>";
}
