import { short, time } from "../format.js";

// Linha do tempo de auditoria: um evento por efeito, com o trace_id de cada mensagem
function detail(event) {
  const p = event.payload ?? {};
  switch (event.type) {
    case "message.classified": return `${p.category} · ${p.priority} · ${p.classifier}`;
    case "conversation.routed": return `${p.queue_name}${p.rule ? ` (regra: ${p.rule.name})` : " (fila padrão)"}`;
    case "conversation.escalated": return p.reason;
    case "conversation.assigned": return p.analyst_name;
    case "agent.reply_discarded": return p.reason;
    case "message.held_for_human": return p.cause === "handoff" ? "cancelada no handoff" : "fila humana";
    case "message.delivery_failed": return p.error;
    case "conversation.priority_raised": return `${p.from} → ${p.to}`;
    default: return "";
  }
}

export default function Timeline({ events }) {
  if (!events?.length) return <p className="muted">Sem eventos.</p>;
  return (
    <ol className="timeline">
      {events.map((e) => (
        <li key={e.id} className={`event event-${e.type.split(".")[0]}`}>
          <span className="event-time">{time(e.occurred_at)}</span>
          <span className="event-type">{e.type}</span>
          <span className="event-actor">{e.actor}</span>
          <span className="event-detail">{detail(e)}</span>
          <span className="event-trace" title={e.trace_id}>trace {short(e.trace_id)}</span>
        </li>
      ))}
    </ol>
  );
}
