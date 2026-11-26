import { useEffect, useRef } from "react";
import { CATEGORIES, FRUSTRATION, WANTS_HUMAN_MIN, frustrationLevel, time } from "../format.js";

// A conversa conta a própria história: mensagens e, entre elas, o que a plataforma fez.
// O trilho à esquerda mostra quem estava atendendo em cada momento: IA, equipe ou encerrada.
function eventLine(e) {
  const p = e.payload ?? {};
  switch (e.type) {
    case "conversation.routed":
      return { tone: "route", phase: p.first_responder === "human" ? "human" : null,
        text: `Entrou na fila ${p.queue_name}`
          + (p.rule ? `, pela regra “${p.rule.name}”` : ", a fila padrão da marca")
          + (p.first_responder === "human" ? ". Quem atende é a equipe." : ".") };
    case "conversation.escalated":
      return { tone: "handoff", phase: "human",
        text: e.actor === "triage" ? "A triagem transferiu para a equipe" : "Transferida para a equipe",
        detail: [p.reason, p.to_queue_name ? `Fila ${p.to_queue_name}.` : null].filter(Boolean).join(". ") };
    case "conversation.assigned":
      return { tone: "human", text: `${p.analyst_name} assumiu o caso` };
    case "conversation.closed":
      return { tone: "closed", phase: "closed", text: "Caso encerrado" };
    case "conversation.priority_raised":
      return { tone: "alert", text: "A prioridade subiu para alta" };
    case "message.held_for_human":
      return p.cause === "handoff" ? { tone: "human", text: "Mensagem segurada para a equipe durante a transferência" } : null;
    case "agent.reply_discarded":
      return { tone: "alert", text: "Resposta atrasada da IA descartada",
        detail: "O caso já estava com a equipe, então o cliente não a recebeu." };
    case "message.delivery_failed":
      return { tone: "alert", text: `A IA não recebeu a mensagem depois de ${p.attempts} tentativas` };
    case "message.redelivery_requested":
      return { tone: "route", text: "Reenvio para a IA pedido pela operação" };
    default:
      return null; // recebida, classificada, enviada, respondida: a própria mensagem já mostra
  }
}

export default function Thread({ messages, audit, customerName, analystName }) {
  const end = useRef(null);
  const sorted = [
    ...(messages ?? []).map((m) => ({ at: m.created_at, key: m.id, m })),
    ...(audit ?? []).map((e) => ({ at: e.occurred_at, key: e.id, e, line: eventLine(e) })).filter((i) => i.line),
  ].sort((a, b) => new Date(a.at) - new Date(b.at));

  let phase = "ai";
  const items = sorted.map((item) => {
    if (item.line?.phase) phase = item.line.phase;
    return { ...item, phase };
  });

  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [items.length]);

  const who = { customer: customerName ?? "Cliente", agent: "IA", analyst: analystName ?? "Equipe", system: "Plataforma" };
  if (!items.length) return <p className="empty thread-empty">Nenhuma mensagem ainda.</p>;
  return (
    <ol className="thread">
      {items.map((item) => item.m ? (
        <li key={item.key} className={`row row-${item.m.author}`} data-phase={item.phase}>
          <div className={`bubble bubble-${item.m.author}`}>
            <p>{item.m.text}</p>
            <span className="bubble-meta">
              {who[item.m.author]}, <time>{time(item.m.created_at)}</time>
              {item.m.category && <span className="bubble-cat">{CATEGORIES[item.m.category]}</span>}
            </span>
            <Signals m={item.m} />
          </div>
        </li>
      ) : (
        <li key={item.key} className={`row event event-${item.line.tone}`} data-phase={item.phase}>
          <span className="event-text">{item.line.text}</span>
          {item.line.detail && <span className="event-detail">{item.line.detail}</span>}
          <time>{time(item.e.occurred_at)}</time>
        </li>
      ))}
      <li ref={end} aria-hidden="true" className="thread-end" />
    </ol>
  );
}

// O que o Jev percebeu na mensagem do cliente: só aparece quando chama atenção
function Signals({ m }) {
  if (m.author !== "customer") return null;
  const level = frustrationLevel(m.frustration);
  const asks = m.wants_human != null && m.wants_human > WANTS_HUMAN_MIN;
  if (!(level >= 2) && !asks) return null;
  return (
    <span className="signals">
      {level >= 2 && <span className={`chip chip-mood-${level}`} title={`Frustração ${m.frustration.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} de 3 (Jev)`}>
        {FRUSTRATION[level]}</span>}
      {asks && <span className="chip chip-human" title={`Pedido de pessoa: ${Math.round(m.wants_human * 100)}% (Jev)`}>
        Pediu uma pessoa</span>}
    </span>
  );
}
