function normalizeApiBase(raw) {
  const value = (raw || "").trim().replace(/\/$/, "");
  if (!value) return "";
  // Host without scheme becomes a relative path on the frontend — fix it.
  if (!/^https?:\/\//i.test(value)) {
    return `https://${value}`;
  }
  return value;
}

export { normalizeApiBase };

const API_BASE = normalizeApiBase(import.meta.env.VITE_API_URL);

export async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "include",
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    const detail = data?.detail;
    let msg;
    let code = null;
    let email = null;
    if (typeof detail === "string") {
      msg = detail;
    } else if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      msg = detail.message || detail.detail || JSON.stringify(detail);
      code = detail.code || null;
      email = detail.email || null;
    } else if (Array.isArray(detail)) {
      msg = detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    } else {
      msg = JSON.stringify(detail || data);
    }
    const err = new Error(msg || res.statusText);
    err.code = code;
    err.email = email;
    err.status = res.status;
    throw err;
  }
  return data;
}
