import { CATEGORIES, PRIORITIES, time } from "../format.js";

// A conversa conta a própria história: mensagens e, entre elas, o que a plataforma fez
function eventLine(e) {
  const p = e.payload ?? {};
  switch (e.type) {
    case "conversation.routed":
      return { tone: "route", text: `Entrou na fila ${p.queue_name}`
        + (p.rule ? ` pela regra "${p.rule.name}"` : ", a fila padrão da marca")
        + (p.first_responder === "human" ? ". Essa fila é atendida pela equipe." : ".") };
    case "conversation.escalated":
      return { tone: "handoff", text: "Transferida para atendimento humano",
        detail: [p.reason, p.to_queue_name ? `Foi para a fila ${p.to_queue_name}.` : null].filter(Boolean).join(". ") };
    case "conversation.assigned":
      return { tone: "human", text: `${p.analyst_name} assumiu o caso` };
    case "conversation.closed":
      return { tone: "closed", text: "Caso encerrado" };
    case "conversation.priority_raised":
      return { tone: "alert", text: "A prioridade subiu para alta" };
    case "message.held_for_human":
      return { tone: "human", text: p.cause === "handoff"
        ? "Mensagem segurada para a equipe: chegou durante a transferência"
        : "Mensagem ficou com a equipe, sem passar pela IA" };
    case "agent.reply_discarded":
      return { tone: "alert", text: "Uma resposta atrasada da IA foi descartada",
        detail: "O caso já estava com a equipe, então o cliente não a recebeu." };
    case "message.delivery_failed":
      return { tone: "alert", text: `A IA não recebeu a mensagem depois de ${p.attempts} tentativas` };
    case "message.redelivery_requested":
      return { tone: "route", text: "Reenvio para a IA solicitado pela operação" };
    default:
      return null; // recebida, classificada, enviada, respondida: a própria mensagem já mostra
  }
}

const AUTHOR = { customer: "Cliente", agent: "IA", analyst: "Analista" };

export default function Thread({ messages, audit, customerName }) {
  const items = [
    ...(messages ?? []).map((m) => ({ at: m.created_at, kind: "message", m })),
    ...(audit ?? []).map((e) => ({ at: e.occurred_at, kind: "event", e, line: eventLine(e) })).filter((i) => i.line),
  ].sort((a, b) => new Date(a.at) - new Date(b.at));

  if (!items.length) return <p className="empty">Nenhuma mensagem ainda.</p>;
  return (
    <ol className="thread">
      {items.map((item) => item.kind === "message"
        ? (
          <li key={item.m.id} className={`bubble bubble-${item.m.author}`}>
            <div className="bubble-who">
              {item.m.author === "customer" ? customerName ?? "Cliente" : AUTHOR[item.m.author]}
              <time>{time(item.m.created_at)}</time>
            </div>
            <p>{item.m.text}</p>
            {item.m.category && (
              <div className="bubble-tags">
                {CATEGORIES[item.m.category]}{item.m.priority === "high" ? ` · prioridade ${PRIORITIES.high.toLowerCase()}` : ""}
              </div>
            )}
          </li>
        )
        : (
          <li key={item.e.id} className={`happening happening-${item.line.tone}`}>
            <span>{item.line.text}</span>
            {item.line.detail && <small>{item.line.detail}</small>}
            <time>{time(item.e.occurred_at)}</time>
          </li>
        ))}
    </ol>
  );
}
