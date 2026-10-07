const BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export function getTechnician() {
  return localStorage.getItem("technician") || "";
}
export function setTechnician(name) {
  localStorage.setItem("technician", name.trim());
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function detailToText(detail) {
  if (!detail) return "Request failed";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => `${(d.loc || []).filter((x) => x !== "body").join(".")}: ${d.msg}`)
      .join("; ");
  }
  return JSON.stringify(detail);
}

async function request(method, path, body) {
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-Technician": getTechnician() || "technician",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      "Cannot reach the server. It may be starting up (free hosting can take ~60s) — please retry.",
      0
    );
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* no body */
  }
  if (!res.ok) throw new ApiError(detailToText(data && data.detail), res.status);
  return data;
}

export const api = {
  equipmentTypes: () => request("GET", "/equipment-types"),
  listReports: () => request("GET", "/reports"),
  getReport: (id) => request("GET", `/reports/${id}`),
  createReport: (body) => request("POST", "/reports", body),
  analyze: (id, answers) => request("POST", `/reports/${id}/analyze`, { answers: answers || {} }),
  addFinding: (id, body) => request("POST", `/reports/${id}/findings`, body),
  history: (identifier) => request("GET", `/equipment/${encodeURIComponent(identifier)}/history`),
  editWO: (id, body) => request("PATCH", `/work-orders/${id}`, body),
  approveWO: (id, overrideReason) =>
    request("POST", `/work-orders/${id}/approve`, { override_reason: overrideReason || null }),
  rejectWO: (id, reason) => request("POST", `/work-orders/${id}/reject`, { reason }),
};