// Cliente da API JSON da plataforma. As telas só usam o que a API já oferece.
export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(API_URL + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join("; ")
      : `erro ${response.status}`;
    throw new Error(message);
  }
  return data;
}

export function query(params) {
  const entries = Object.entries(params).filter(([, v]) => v !== "" && v !== null && v !== undefined);
  return entries.length ? "?" + new URLSearchParams(entries).toString() : "";
}
