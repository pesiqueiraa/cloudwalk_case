export const BRANDS = { infinitepay: "InfinitePay", jim: "JIM" };
export const CHANNELS = { chat: "Chat", whatsapp: "WhatsApp", email: "E-mail" };
export const CATEGORIES = {
  payments: "Pagamentos", hardware: "Maquininha", card: "Cartão",
  account: "Conta", fraud: "Fraude", other: "Outros assuntos",
};
export const PRIORITIES = { high: "Alta", normal: "Normal" };

// Frustração medida pelo Jev (Score 0 a 3); a mesma escala do limiar de escalação da fila
export const FRUSTRATION = ["Calmo", "Incomodado", "Frustrado", "Muito irritado"];
export function frustrationLevel(x) {
  return x == null ? null : Math.min(3, Math.max(0, Math.floor(x + 0.5)));
}
export const WANTS_HUMAN_MIN = 0.7; // mesmo corte de decision.py

export function time(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function preciseTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return time(iso) + "," + String(d.getMilliseconds()).padStart(3, "0");
}

export function dateTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function ago(iso) {
  if (!iso) return "";
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "agora";
  if (seconds < 3600) return `há ${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `há ${Math.floor(seconds / 3600)} h`;
  return dateTime(iso);
}

export function short(id) {
  return id ? String(id).slice(0, 8) : "";
}

// Situação da conversa em linguagem de quem atende
export function situation(c) {
  if (!c) return null;
  if (c.status === "closed") return { tone: "closed", label: "Encerrada" };
  if (c.handled_by === "human") {
    return c.assigned_analyst_name
      ? { tone: "human", label: `Com ${c.assigned_analyst_name.split(" ")[0]}` }
      : { tone: "waiting", label: "Aguardando analista" };
  }
  return { tone: "ai", label: "Com a IA" };
}
