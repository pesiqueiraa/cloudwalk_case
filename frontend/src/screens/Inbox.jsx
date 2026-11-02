import { useState } from "react";
import { api, query } from "../api.js";
import { usePolling } from "../usePolling.js";
import { BRANDS } from "../format.js";
import { useToast } from "../components/Toast.jsx";
import CaseHeader from "../components/CaseHeader.jsx";
import ConversationList from "../components/ConversationList.jsx";
import Tabs from "../components/Tabs.jsx";
import Thread from "../components/Thread.jsx";
import Timeline from "../components/Timeline.jsx";

// Clientes sintéticos, os mesmos do simulador (simulator/data.py)
const CUSTOMERS = {
  infinitepay: [
    { external_id: "sim-ip-001", name: "Ana Ficticia", email: "ana.ficticia@example.com" },
    { external_id: "sim-ip-002", name: "Bruno Inventado", email: "bruno.inventado@example.com" },
    { external_id: "sim-ip-003", name: "Carla Sintetica", email: "carla.sintetica@example.com" },
  ],
  jim: [
    { external_id: "sim-jim-001", name: "John Placeholder", email: "john.placeholder@example.com" },
    { external_id: "sim-jim-002", name: "Mary Sample", email: "mary.sample@example.com" },
  ],
};

const SUGGESTIONS = {
  infinitepay: ["Minha maquininha não liga", "Não recebi o pagamento de ontem", "Quero falar com um atendente",
    "Fui vítima de golpe, clonaram meu cartão"],
  jim: ["My card reader is off", "I didn't get yesterday's payout", "I want to talk to a human",
    "My card was cloned"],
};

const VIEWS = [
  ["all", "Todas"], ["ai", "Com a IA"], ["human", "Com a equipe"], ["closed", "Encerradas"],
];
const VIEW_QUERY = {
  all: {}, ai: { handled_by: "agent" }, human: { handled_by: "human" }, closed: { status: "closed" },
};

function uid() {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

async function sendAsCustomer({ session, brand, customer, text }) {
  return api("/channels/chat/messages", {
    method: "POST",
    body: { session_id: session, message_id: `tela-${uid()}`, brand, customer, text, sent_at: new Date().toISOString() },
  });
}

export default function Inbox() {
  const [view, setView] = useState("all");
  const [brand, setBrand] = useState("");
  const [selected, setSelected] = useState(null);
  const [starting, setStarting] = useState(false);
  const list = usePolling("/api/conversations" + query({ ...VIEW_QUERY[view], brand, limit: 60 }));
  const detail = usePolling(selected ? `/api/cases/${selected}` : null);
  // "Com a equipe" inclui as que já nasceram na fila humana (status open); as encerradas ficam em "Encerradas"
  const shown = view === "human" ? list.data?.filter((c) => c.status !== "closed") : list.data;

  return (
    <div className={selected ? "workspace has-selection" : "workspace"}>
      <section className="column list-column" aria-label="Conversas">
        <div className="column-head">
          <h2>Atendimentos</h2>
          <button type="button" className="primary" onClick={() => { setStarting(true); setSelected(null); }}>
            Simular cliente
          </button>
        </div>
        <div className="segmented" role="group" aria-label="Filtrar por quem atende">
          {VIEWS.map(([key, label]) => (
            <button key={key} type="button" aria-pressed={view === key} onClick={() => setView(key)}>{label}</button>
          ))}
        </div>
        <select className="brand-filter" value={brand} onChange={(e) => setBrand(e.target.value)} aria-label="Marca">
          <option value="">InfinitePay e JIM</option>
          {Object.entries(BRANDS).map(([k, v]) => <option key={k} value={k}>Só {v}</option>)}
        </select>
        {list.error && <p className="error">Não consegui carregar as conversas: {list.error}</p>}
        <ConversationList items={shown} selected={selected} onSelect={(id) => { setSelected(id); setStarting(false); }}
                          empty="Nenhuma conversa aqui. Use “Simular cliente” para começar uma." />
      </section>

      <section className="column case-column" aria-label="Conversa">
        {starting && <NewConversation onStarted={(id) => { setStarting(false); setSelected(id); }}
                                      onCancel={() => setStarting(false)} />}
        {!starting && !selected && (
          <div className="placeholder">
            <h2>Escolha uma conversa</h2>
            <p>Aqui aparece a conversa completa, com cada passo que a plataforma deu: fila escolhida, transferência para a equipe, quem assumiu.</p>
          </div>
        )}
        {!starting && detail.data && <Conversation data={detail.data} onBack={() => setSelected(null)} />}
      </section>
    </div>
  );
}

function Conversation({ data, onBack }) {
  const [tab, setTab] = useState("thread");
  const c = data.conversation;
  return (
    <>
      <CaseHeader conversation={c} onBack={onBack} />
      {c.escalation_summary && (
        <div className="reason"><strong>Resumo da IA para a equipe</strong><p>{c.escalation_summary}</p></div>
      )}
      <Tabs value={tab} onChange={setTab} tabs={[["thread", "Conversa"], ["tech", "Detalhes técnicos"]]} />
      {tab === "thread" ? (
        <>
          <Thread messages={data.messages} audit={data.audit} customerName={c.customer_name} />
          <CustomerReply conversation={c} />
        </>
      ) : (
        <div className="tech">
          <p>Cada mensagem tem um <code>trace_id</code>, que liga os registros de todos os serviços por onde ela passou.</p>
          <Timeline events={data.audit} />
        </div>
      )}
    </>
  );
}

function CustomerReply({ conversation: c }) {
  const [text, setText] = useState("");
  const toast = useToast();
  if (c.channel !== "chat") return <p className="composer-note">Só dá para simular o cliente em conversas de chat.</p>;
  if (c.status === "closed") return <p className="composer-note">Conversa encerrada. Uma nova mensagem deste cliente abre outra conversa.</p>;
  return (
    <form className="composer composer-customer" onSubmit={async (e) => {
      e.preventDefault();
      try {
        await sendAsCustomer({
          session: c.external_session_id, brand: c.brand_id, text,
          customer: { external_id: c.customer_external_id, name: c.customer_name, email: `${c.customer_external_id}@example.com` },
        });
        setText("");
      } catch (err) {
        toast(`Mensagem não enviada: ${err.message}`, "error");
      }
    }}>
      <label htmlFor="as-customer">Escrever como {c.customer_name}</label>
      <div className="composer-row">
        <input id="as-customer" value={text} onChange={(e) => setText(e.target.value)} required maxLength={4000}
               placeholder="O que o cliente diz a seguir" />
        <button type="submit">Enviar como cliente</button>
      </div>
    </form>
  );
}

function NewConversation({ onStarted, onCancel }) {
  const [brand, setBrand] = useState("infinitepay");
  const [customer, setCustomer] = useState(0);
  const [text, setText] = useState("");
  const toast = useToast();

  async function start(e) {
    e.preventDefault();
    try {
      const result = await sendAsCustomer({ session: `tela-${uid()}`, brand, customer: CUSTOMERS[brand][customer], text });
      toast("Conversa iniciada");
      onStarted(result.conversation_id);
    } catch (err) {
      toast(`Conversa não iniciada: ${err.message}`, "error");
    }
  }

  return (
    <form className="start" onSubmit={start}>
      <h2>Simular um cliente</h2>
      <p>A mensagem entra pelo chat como se viesse de um cliente de verdade e segue o caminho normal: triagem, fila e IA ou equipe.</p>
      <div className="field-row">
        <label>Marca
          <select value={brand} onChange={(e) => { setBrand(e.target.value); setCustomer(0); }}>
            {Object.entries(BRANDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label>Cliente
          <select value={customer} onChange={(e) => setCustomer(Number(e.target.value))}>
            {CUSTOMERS[brand].map((c, i) => <option key={c.external_id} value={i}>{c.name}</option>)}
          </select>
        </label>
      </div>
      <label>Mensagem
        <textarea value={text} onChange={(e) => setText(e.target.value)} required maxLength={4000} rows={3} />
      </label>
      <div className="suggestions">
        <span>Exemplos:</span>
        {SUGGESTIONS[brand].map((s) => <button key={s} type="button" className="chip" onClick={() => setText(s)}>{s}</button>)}
      </div>
      <div className="form-actions">
        <button type="submit" className="primary">Enviar mensagem</button>
        <button type="button" className="quiet" onClick={onCancel}>Cancelar</button>
      </div>
    </form>
  );
}
