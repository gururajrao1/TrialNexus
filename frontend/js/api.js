/* Shared fetch + DOM helpers. */
export const $ = (id) => document.getElementById(id);

export function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function authHeaders(extra) {
  const h = Object.assign({}, extra);
  try {
    const t = sessionStorage.getItem("tnx_token");
    if (t) h["Authorization"] = "Bearer " + t;
  } catch (e) { /* storage unavailable: send unauthenticated */ }
  return h;
}

function rememberToken() {
  try {
    if (sessionStorage.getItem("tnx_token")) return false;
    const t = window.prompt("This server requires an API token:");
    if (t) sessionStorage.setItem("tnx_token", t.trim());
    return !!t;
  } catch (e) { return false; }
}

async function guarded(path, init, retry) {
  const r = await fetch(path, init);
  if (r.status === 401 && !retry && rememberToken()) {
    init.headers = authHeaders(init.headers);
    return guarded(path, init, true);
  }
  if (!r.ok) throw new Error(path + " → HTTP " + r.status);
  return r.json();
}

export async function getJSON(path) {
  return guarded(path, { headers: authHeaders() }, false);
}

export async function postJSON(path, payload) {
  return guarded(path, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  }, false);
}

export function fail(el, err) {
  el.innerHTML = '<div class="error">' + esc("Failed: " + err.message) + "</div>";
}
