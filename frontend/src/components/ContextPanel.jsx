import { BRANDS, CHANNELS, PRIORITIES, dateTime } from "../format.js";

// O que o analista precisa saber antes de responder, sem disputar espaço com a conversa
export default function ContextPanel({ data, teamName = {} }) {
  const c = data.conversation;
  const history = data.previous_conversations ?? [];
  return (
    <div className="context">
      {c.handled_by === "human" && (
        <section className="ctx-section ctx-summary">
          <h2>{c.escalation_summary ? "Resumo da IA" : "Por que está com a equipe"}</h2>
          <p>{c.escalation_summary ?? `A conversa caiu na fila ${c.queue_name}, que é atendida por pessoas.`}</p>
          {c.escalation_reason && <p className="muted">Motivo: {c.escalation_reason}.</p>}
        </section>
      )}

      <section className="ctx-section">
        <h2>Atendimento</h2>
        <dl className="facts">
          <dt>Marca</dt><dd>{BRANDS[c.brand_id]}</dd>
          <dt>Canal</dt><dd>{CHANNELS[c.channel] ?? c.channel}</dd>
          <dt>Fila</dt><dd>{c.queue_name ?? "Ainda não definida"}</dd>
          {c.team_id && <><dt>Equipe</dt><dd>{teamName[c.team_id] ?? c.team_id}</dd></>}
          <dt>Prioridade</dt><dd>{PRIORITIES[c.priority] ?? "Normal"}</dd>
          <dt>Aberta em</dt><dd>{dateTime(c.created_at)}</dd>
          {c.assigned_analyst_name && <><dt>Analista</dt><dd>{c.assigned_analyst_name}</dd></>}
        </dl>
      </section>

      <section className="ctx-section">
        <h2>Atendimentos anteriores</h2>
        {history.length === 0
          ? <p className="muted">Primeiro atendimento de {c.customer_name} por este canal.</p>
          : (
            <ul className="history">
              {history.map((p) => (
                <li key={p.id}>
                  <span className="history-when">{dateTime(p.created_at)}, {CHANNELS[p.channel]}</span>
                  <p>{p.escalation_summary ?? `“${p.first_message_text}”`}</p>
                  <span className="muted">
                    {p.assigned_analyst_name ? `Atendido por ${p.assigned_analyst_name}` : "Resolvido pela IA"}
                    {p.status !== "closed" ? ", ainda aberto" : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
      </section>
    </div>
  );
}
