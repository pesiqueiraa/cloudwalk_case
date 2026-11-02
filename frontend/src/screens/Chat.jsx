import { useState } from "react";
import { api, query } from "../api.js";
import { usePolling } from "../usePolling.js";
import { BRANDS, dateTime } from "../format.js";
import Badge from "../components/Badge.jsx";
import Messages from "../components/Messages.jsx";
import Timeline from "../components/Timeline.jsx";

// Clientes sintéticos, os mesmos do simulador (simulator/data.py)
const CUSTOMERS = {
  infinitepay: [
    { external_id: "sim-ip-001", name: "Ana Ficticia", email: "ana.ficticia@example.com" },
    { external_id: "sim-ip-002", name: "Bruno Inventado", email: "bruno.inventado@example.com" },
  ],
  jim: [
    { external_id: "sim-jim-001", name: "John Placeholder", email: "john.placeholder@example.com" },
    { external_id: "sim-jim-002", name: "Mary Sample", email: "mary.sample@example.com" },
  ],
};

function uid() {
  return crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random();
}

export default function Chat() {
  const [filters, setFilters] = useState({ brand: "", handled_by: "" });
  const [selected, setSelected] = useState(null);
  const list = usePolling("/api/conversations" + query({ ...filters, limit: 50 }));
  const detail = usePolling(selected ? `/api/conversations/${selected}` : null);

  return (
    <div className="split">
      <section className="panel list-panel">
        <h2>Conversas</h2>
        <div className="filters">
          <select value={filters.brand} onChange={(e) => setFilters({ ...filters, brand: e.target.value })}>
            <option value="">Todas as marcas</option>
            {Object.entries(BRANDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select value={filters.handled_by} onChange={(e) => setFilters({ ...filters, handled_by: e.target.value })}>
            <option value="">Agente e humano</option>
            <option value="agent">Com o agente</option>
            <option value="human">Com humano</option>
          </select>
        </div>
        <NewMessage selected={detail.data?.conversation} onSent={(id) => { setSelected(id); list.reload(); }} />
        {list.error && <p className="error">{list.error}</p>}
        <ul className="rows">
          {(list.data ?? []).map((c) => (
            <li key={c.id} className={c.id === selected ? "row selected" : "row"} onClick={() => setSelected(c.id)}>
              <div className="row-head">
                <strong>{c.customer_name}</strong>
                <span className="muted small">{BRANDS[c.brand_id]} · {c.channel}</span>
              </div>
              <div className="row-text">{c.last_message_text}</div>
              <div className="row-badges">
                <Badge value={c.status} />
                <Badge value={c.handled_by} label={c.handled_by === "human" ? "humano" : "agente"} />
                {c.priority === "high" && <Badge value="high" label="alta" />}
                <span className="muted small">{c.queue_name}</span>
              </div>
            </li>
          ))}
        </ul>
      </section>
      <section className="panel detail-panel">
        {!selected && <p className="muted">Escolha uma conversa ou mande uma mensagem como cliente.</p>}
        {detail.error && <p className="error">{detail.error}</p>}
        {detail.data && <ConversationDetail data={detail.data} />}
      </section>
    </div>
  );
}

function ConversationDetail({ data }) {
  const c = data.conversation;
  return (
    <>
      <div className="detail-head">
        <h2>{BRANDS[c.brand_id]} · {c.channel}</h2>
        <div className="row-badges">
          <Badge value={c.status} />
          <Badge value={c.handled_by} label={c.handled_by === "human" ? "humano" : "agente"} />
          {c.priority && <Badge value={c.priority} label={c.priority === "high" ? "alta" : "normal"} />}
        </div>
        <p className="muted small">aberta em {dateTime(c.created_at)} · sessão {c.external_session_id}</p>
      </div>
      {c.escalation_summary && (
        <div className="summary"><strong>Resumo da escalação:</strong> {c.escalation_summary}</div>
      )}
      <div className="columns">
        <div><h3>Mensagens</h3><Messages messages={data.messages} /></div>
        <div><h3>Auditoria</h3><Timeline events={data.audit} /></div>
      </div>
    </>
  );
}

// Simula o cliente no canal de chat: nova conversa ou continuação da selecionada
function NewMessage({ selected, onSent }) {
  const [brand, setBrand] = useState("infinitepay");
  const [customer, setCustomer] = useState(0);
  const [text, setText] = useState("");
  const [error, setError] = useState(null);
  const canContinue = selected && selected.channel === "chat" && selected.status !== "closed";
  const [mode, setMode] = useState("new");
  const continuing = mode === "continue" && canContinue;

  async function send(e) {
    e.preventDefault();
    setError(null);
    const who = continuing
      ? { external_id: selected.customer_external_id, name: selected.customer_name,
          email: `${selected.customer_external_id}@example.com` }
      : CUSTOMERS[brand][customer];
    try {
      const result = await api("/channels/chat/messages", {
        method: "POST",
        body: {
          session_id: continuing ? selected.external_session_id : `tela-${uid()}`,
          message_id: `tela-${uid()}`,
          brand: continuing ? selected.brand_id : brand,
          customer: who,
          text,
          sent_at: new Date().toISOString(),
        },
      });
      setText("");
      onSent(result.conversation_id);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="compose" onSubmit={send}>
      <div className="filters">
        <select value={continuing ? "continue" : "new"} onChange={(e) => setMode(e.target.value)}>
          <option value="new">Nova conversa</option>
          <option value="continue" disabled={!canContinue}>Continuar a selecionada</option>
        </select>
        {!continuing && (
          <>
            <select value={brand} onChange={(e) => { setBrand(e.target.value); setCustomer(0); }}>
              {Object.entries(BRANDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select value={customer} onChange={(e) => setCustomer(Number(e.target.value))}>
              {CUSTOMERS[brand].map((c, i) => <option key={c.external_id} value={i}>{c.name}</option>)}
            </select>
          </>
        )}
      </div>
      <div className="compose-row">
        <input value={text} onChange={(e) => setText(e.target.value)} required maxLength={4000}
               placeholder="Mensagem do cliente (ex.: Minha maquininha não liga)" />
        <button type="submit">Enviar</button>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
