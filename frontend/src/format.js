export function time(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString("pt-BR", { hour12: false }) + "." + String(d.getMilliseconds()).padStart(3, "0");
}

export function dateTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("pt-BR", { hour12: false });
}

export function short(id) {
  return id ? String(id).slice(0, 8) : "—";
}

export const BRANDS = { infinitepay: "InfinitePay", jim: "JIM" };
export const CATEGORIES = ["payments", "hardware", "card", "account", "fraud", "other"];
export const CHANNELS = ["chat", "whatsapp", "email"];
