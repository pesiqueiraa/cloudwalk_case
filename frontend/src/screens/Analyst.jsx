import { useState } from "react";
import { api, query } from "../api.js";
import { usePolling } from "../usePolling.js";
import { CHANNELS, dateTime } from "../format.js";
import { useToast } from "../components/Toast.jsx";
import CaseHeader from "../components/CaseHeader.jsx";
import ConversationList from "../components/ConversationList.jsx";
import Tabs from "../components/Tabs.jsx";
import Thread from "../components/Thread.jsx";
import Timeline from "../components/Timeline.jsx";

const preview = (c) => c.escalation_summary ?? "Chegou direto na fila da equipe, sem passar pela IA.";

export default function Analyst({ analyst, teamName }) {
  const [selected, setSelected] = useState(null);
  const queue = usePolling(analyst ? "/api/escalations" + query({ team_id: analyst.team_id }) : null);
  const caseView = usePolling(selected ? `/api/cases/${selected}` : null);

  if (!analyst) {
    return (
      <div className="placeholder wide">
        <h2>Quem está atendendo?</h2>
        <p>Escolha seu nome em “Você é”, no menu ao lado. A fila mostra os casos da sua equipe que precisam de uma pessoa.</p>
      </div>
    );
  }

  const all = queue.data;
  const groups = all && [
    ["Esperando alguém assumir", all.filter((c) => !c.assigned_analyst_id),
      "Ninguém esperando. Quando a IA transferir um caso para a sua equipe, ele aparece aqui."],
    ["Com você", all.filter((c) => c.assigned_analyst_id === analyst.id), "Você não tem casos abertos."],
    ["Com colegas", all.filter((c) => c.assigned_analyst_id && c.assigned_analyst_id !== analyst.id), null],
  ];

  return (
    <div className={selected ? "workspace has-selection" : "workspace"}>
      <section className="column list-column" aria-label="Fila da equipe">
        <div className="column-head">
          <h2>Fila de {teamName[analyst.team_id] ?? analyst.team_id}</h2>
        </div>
        {queue.error && <p className="error">Não consegui carregar a fila: {queue.error}</p>}
        {!all && <p className="empty">Carregando…</p>}
        {groups?.map(([title, items, empty]) => (items.length || empty) && (
          <div key={title} className="group">
            <h3>{title} <span className="group-count">{items.length}</span></h3>
            <ConversationList items={items} selected={selected} onSelect={setSelected} empty={empty} preview={preview} />
          </div>
        ))}
      </section>
      <section className="column case-column" aria-label="Caso">
        {!selected && (
          <div className="placeholder">
            <h2>Escolha um caso</h2>
            <p>Os casos mais antigos e os de prioridade alta ficam no topo. Assuma um para responder ao cliente.</p>
          </div>
        )}
        {caseView.data && (
          <Case data={caseView.data} analyst={analyst} onBack={() => setSelected(null)}
                onChange={() => { caseView.reload(); queue.reload(); }} />
        )}
      </section>
    </div>
  );
}

function Case({ data, analyst, onBack, onChange }) {
  const [tab, setTab] = useState("thread");
  const [text, setText] = useState("");
  const toast = useToast();
  const c = data.conversation;
  const mine = c.assigned_analyst_id === analyst.id;
  const open = c.status !== "closed";

  async function act(path, done, body = {}) {
    try {
      await api(`/api/conversations/${c.id}/${path}`, { method: "POST", body: { analyst_id: analyst.id, ...body } });
      toast(done);
      onChange();
      return true;
    } catch (err) {
      toast(err.message, "error");
      return false;
    }
  }

  const history = data.previous_conversations;
  return (
    <>
      <CaseHeader conversation={c} onBack={onBack}>
        <div className="case-actions">
          {open && !c.assigned_analyst_id && (
            <button type="button" className="primary" onClick={() => act("assign", "Caso assumido")}>Assumir caso</button>
          )}
          {open && mine && (
            <button type="button" className="quiet" onClick={() => act("close", "Caso encerrado")}>Encerrar caso</button>
          )}
          {open && c.assigned_analyst_id && !mine && <span>{c.assigned_analyst_name} está cuidando deste caso.</span>}
          {!open && <span>Encerrado em {dateTime(c.closed_at)}.</span>}
        </div>
      </CaseHeader>

      <div className="reason">
        <strong>{c.escalation_summary ? "Por que chegou à equipe" : "Chegou direto para a equipe"}</strong>
        <p>{c.escalation_summary ?? `A conversa caiu na fila ${c.queue_name}, que é atendida por pessoas.`}</p>
        {c.escalation_reason && <p className="reason-why">Motivo informado pela IA: {c.escalation_reason}.</p>}
      </div>

      <Tabs value={tab} onChange={setTab} tabs={[
        ["thread", "Conversa"],
        ["history", history.length ? `Atendimentos anteriores (${history.length})` : "Atendimentos anteriores"],
        ["tech", "Detalhes técnicos"],
      ]} />

      {tab === "thread" && (
        <>
          <Thread messages={data.messages} audit={data.audit} customerName={c.customer_name} />
          {open && mine && (
            <form className="composer composer-analyst" onSubmit={async (e) => {
              e.preventDefault();
              if (await act("messages", "Resposta enviada", { text })) setText("");
            }}>
              <label htmlFor="reply">Responder a {c.customer_name}</label>
              <div className="composer-row">
                <input id="reply" value={text} onChange={(e) => setText(e.target.value)} required maxLength={4000}
                       placeholder="Sua resposta ao cliente" />
                <button type="submit" className="primary">Enviar resposta</button>
              </div>
            </form>
          )}
          {open && !c.assigned_analyst_id && <p className="composer-note">Assuma o caso para responder ao cliente.</p>}
        </>
      )}

      {tab === "history" && (
        history.length === 0
          ? <p className="empty">É o primeiro atendimento de {c.customer_name} por este canal.</p>
          : (
            <ul className="history">
              {history.map((p) => (
                <li key={p.id}>
                  <div className="history-when">{dateTime(p.created_at)} · {CHANNELS[p.channel]}</div>
                  <p>{p.escalation_summary ?? `“${p.first_message_text}”`}</p>
                  <div className="history-meta">
                    Fila {p.queue_name}. {p.message_count} mensagens.
                    {p.assigned_analyst_name ? ` Atendido por ${p.assigned_analyst_name}.` : " Resolvido pela IA."}
                    {p.status !== "closed" ? " Ainda aberto." : ""}
                  </div>
                </li>
              ))}
            </ul>
          )
      )}

      {tab === "tech" && (
        <div className="tech"><Timeline events={data.audit} /></div>
      )}
    </>
  );
}
