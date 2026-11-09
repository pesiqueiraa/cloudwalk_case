import { situation } from "../format.js";

// Verde = com a IA, cobre = com a equipe. A mesma cor em toda a interface.
export default function Status({ conversation, quiet = false }) {
  const s = situation(conversation);
  if (!s) return null;
  return <span className={`status status-${s.tone}${quiet ? " status-quiet" : ""}`}>{s.label}</span>;
}
