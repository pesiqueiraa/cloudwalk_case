import { useState } from "react";
import { api, query } from "../api.js";
import { usePolling } from "../usePolling.js";
import { BRANDS, dateTime } from "../format.js";
import Badge from "../components/Badge.jsx";
import Messages from "../components/Messages.jsx";
import Timeline from "../components/Timeline.jsx";

export default function Analyst() {
  const analysts = usePolling("/api/admin/analysts", 60000);
  const [analystId, setAnalystId] = useState("");
  const [selected, setSelected] = useState(null);
  const analyst = (analysts.data ?? []).find((a) => a.id === analystId);
  const queue = usePolling(analyst ? "/api/escalations" + query({ team_id: analyst.team_id }) : null);
  const caseView = usePolling(selected ? `/api/cases/${selected}` : null);

  return (
    <div className="split">
      <section className="panel list-panel">
        <h2>Fila de escalas</h2>
        <select value={analystId} onChange={(e) => { setAnalystId(e.target.value); setSelected(null); }}>
          <option value="">Quem é você?</option>
          {(analysts.data ?? []).map((a) => (
            <option key={a.id} value={a.id}>{a.name} — {a.team_id}</option>
          ))}
        </select>
        {queue.error && <p className="error">{queue.error}</p>}
        {analyst && queue.data?.length === 0 && <p className="muted">Nenhum caso na fila da equipe {analyst.team_id}.</p>}
        <ul className="rows">
          {(queue.data ?? []).map((c) => (
            <li key={c.id} className={c.id === selected ? "row selected" : "row"} onClick={() => setSelected(c.id)}>
              <div className="row-head">
                <strong>{c.customer_name}</strong>
                <span className="muted small">{BRANDS[c.brand_id]} · {c.channel}</span>
              </div>
              <div className="row-text">{c.escalation_summary ?? "Roteada direto para a equipe"}</div>
              <div className="row-badges">
                {c.priority === "high" && <Badge value="high" label="alta" />}
                <Badge value={c.status} />
                {c.assigned_analyst_name
                  ? <span className="muted small">com {c.assigned_analyst_name}</span>
                  : <Badge value="open" label="não assumido" />}
                <span className="muted small">{c.queue_name}</span>
              </div>
            </li>
          ))}
        </ul>
      </section>
      <section className="panel detail-panel">
        {!selected && <p className="muted">Escolha quem você é e um caso da fila.</p>}
        {caseView.error && <p className="error">{caseView.error}</p>}
        {caseView.data && (
          <Case data={caseView.data} analystId={analystId} onChange={() => { caseView.reload(); queue.reload(); }} />
        )}
      </section>
    </div>
  );
}

function Case({ data, analystId, onChange }) {
  const c = data.conversation;
  const [text, setText] = useState("");
  const [error, setError] = useState(null);
  const mine = c.assigned_analyst_id === analystId;
  const open = c.status !== "closed";

  async function act(path, body) {
    setError(null);
    try {
      await api(`/api/conversations/${c.id}/${path}`, { method: "POST", body: { analyst_id: analystId, ...body } });
      onChange();
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    }
  }

  return (
    <>
      <div className="detail-head">
        <h2>{c.customer_name} <span className="muted small">{BRANDS[c.brand_id]} · {c.channel}</span></h2>
        <div className="row-badges">
          <Badge value={c.status} />
          {c.priority && <Badge value={c.priority} label={c.priority === "high" ? "alta" : "normal"} />}
          <span className="muted small">{c.queue_name} · equipe {c.team_id}</span>
          {c.assigned_analyst_name && <span className="muted small">· com {c.assigned_analyst_name}</span>}
        </div>
      </div>
      <div className="summary">
        <strong>Resumo:</strong> {c.escalation_summary ?? "Sem resumo: conversa roteada direto para a equipe humana."}
        {c.escalation_reason && <div className="muted small">Motivo: {c.escalation_reason}</div>}
      </div>
      <div className="actions">
        {open && !c.assigned_analyst_id && <button onClick={() => act("assign")}>Assumir caso</button>}
        {open && mine && <button className="secondary" onClick={() => act("close")}>Encerrar</button>}
        {!open && <span className="muted">Encerrada em {dateTime(c.closed_at)}</span>}
      </div>
      {error && <p className="error">{error}</p>}
      {open && mine && (
        <form className="compose-row" onSubmit={async (e) => {
          e.preventDefault();
          if (await act("messages", { text })) setText("");
        }}>
          <input value={text} onChange={(e) => setText(e.target.value)} required maxLength={4000}
                 placeholder="Responder ao cliente" />
          <button type="submit">Responder</button>
        </form>
      )}
      <div className="columns">
        <div>
          <h3>Conversa</h3>
          <Messages messages={data.messages} />
          <h3>Atendimentos anteriores</h3>
          {data.previous_conversations.length === 0 && <p className="muted">Primeiro atendimento deste cliente.</p>}
          <ul className="memory">
            {data.previous_conversations.map((p) => (
              <li key={p.id}>
                <div><strong>{dateTime(p.created_at)}</strong> · {p.channel} · {p.queue_name} <Badge value={p.status} /></div>
                <div>{p.escalation_summary ?? p.first_message_text}</div>
                <div className="muted small">
                  {p.message_count} mensagens{p.assigned_analyst_name ? ` · atendido por ${p.assigned_analyst_name}` : ""}
                </div>
              </li>
            ))}
          </ul>
        </div>
        <div><h3>Auditoria</h3><Timeline events={data.audit} /></div>
      </div>
    </>
  );
}
