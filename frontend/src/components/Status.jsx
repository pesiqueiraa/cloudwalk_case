import { situation } from "../format.js";

export default function Status({ conversation }) {
  const s = situation(conversation);
  if (!s) return null;
  return <span className={`status status-${s.tone}`}>{s.label}</span>;
}
