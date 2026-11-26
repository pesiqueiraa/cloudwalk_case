import { BRANDS, CHANNELS, FRUSTRATION, PRIORITIES, dateTime, frustrationLevel } from "../format.js";

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

      <TriageSignals messages={data.messages ?? []} audit={data.audit ?? []} />

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

// Como o cliente está e quem respondeu: frustração por mensagem (Jev) e o modelo do agente (auditoria)
function TriageSignals({ messages, audit }) {
  const points = messages.filter((m) => m.author === "customer" && m.frustration != null);
  const classified = [...audit].reverse().find((e) => e.type === "message.classified")?.payload;
  const agent = [...audit].reverse().find((e) => e.type === "agent.replied" && e.payload?.agent)?.payload.agent;
  if (!classified && !agent) return null;
  const last = points.at(-1);
  return (
    <section className="ctx-section">
      <h2>Sinais da IA</h2>
      {points.length > 0 ? (
        <>
          <p className="mood">
            <span className={`chip chip-mood-${frustrationLevel(last.frustration)}`}>{FRUSTRATION[frustrationLevel(last.frustration)]}</span>
            <span className="muted">na última mensagem ({last.frustration.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} de 3)</span>
          </p>
          {points.length > 1 && <MoodLine values={points.map((m) => m.frustration)} />}
        </>
      ) : (
        <p className="muted">Sem medida de frustração: a triagem desta conversa rodou pelas regras.</p>
      )}
      <dl className="facts">
        {classified && <><dt>Triagem</dt><dd>{classified.classifier === "jev" ? `Jev (${classified.version})` : "Regras por palavra-chave"}
          {classified.fallback_reason && <span className="muted"> (reserva: {classified.fallback_reason})</span>}</dd></>}
        {agent && <><dt>Agente</dt><dd>{agent.impl === "llm" ? `${agent.model}, esforço ${agent.effort}, prompt v${agent.prompt_version}` : "Mock determinístico"}</dd></>}
      </dl>
    </section>
  );
}

// Curva da frustração ao longo da conversa, de 0 (calmo) a 3 (muito irritado)
function MoodLine({ values }) {
  const w = 220, h = 44, pad = 4;
  const x = (i) => pad + (i * (w - 2 * pad)) / (values.length - 1);
  const y = (v) => h - pad - (v / 3) * (h - 2 * pad);
  // Coordenadas do SVG com ponto decimal: nunca formatar em pt-BR aqui
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <svg className="moodline" viewBox={`0 0 ${w} ${h}`} role="img"
         aria-label={`Frustração por mensagem: ${values.map((v) => v.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })).join(", ")} (de 0 a 3)`}>
      <line x1={pad} x2={w - pad} y1={y(2)} y2={y(2)} className="moodline-mark" />
      <path d={d} className="moodline-path" />
      {values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r="3" className="moodline-dot" />)}
    </svg>
  );
}
