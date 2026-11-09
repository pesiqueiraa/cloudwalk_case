import { useState } from "react";
import { Headset, PenLine } from "lucide-react";
import { query } from "../api.js";
import { usePolling } from "../usePolling.js";
import { BRANDS } from "../format.js";
import { go, useApp } from "../hooks.js";
import ConversationList from "../components/ConversationList.jsx";
import ConversationView from "../components/ConversationView.jsx";

const VIEWS = [["all", "Todas"], ["ai", "Com a IA"], ["human", "Com a equipe"], ["closed", "Encerradas"]];
const VIEW_QUERY = { all: {}, ai: { handled_by: "agent" }, human: { handled_by: "human" }, closed: { status: "closed" } };

// Todas as conversas, para acompanhar o que a plataforma está fazendo. Só leitura.
export default function Inbox({ routeId }) {
  const [view, setView] = useState("all");
  const [brand, setBrand] = useState("");
  const list = usePolling("/api/conversations" + query({ ...VIEW_QUERY[view], brand, limit: 60 }));
  const detail = usePolling(routeId ? `/api/cases/${routeId}` : null);
  // "Com a equipe" inclui as que já nasceram na fila humana; as encerradas ficam em "Encerradas"
  const shown = view === "human" ? list.data?.filter((c) => c.status !== "closed") : list.data;

  return (
    <div className={routeId ? "workspace has-selection" : "workspace"}>
      <section className="pane pane-list" aria-label="Conversas">
        <div className="pane-head">
          <h1>Conversas</h1>
          <select className="select-quiet" value={brand} onChange={(e) => setBrand(e.target.value)} aria-label="Marca">
            <option value="">Todas as marcas</option>
            {Object.entries(BRANDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div className="filters" role="group" aria-label="Filtrar por quem atende">
          {VIEWS.map(([key, label]) => (
            <button key={key} type="button" className="filter" aria-pressed={view === key} onClick={() => setView(key)}>
              {label}
            </button>
          ))}
        </div>
        <div className="pane-scroll">
          {list.error && <p className="error">Não consegui carregar as conversas: {list.error}</p>}
          <ConversationList items={shown} selected={routeId} onSelect={(id) => go("conversas", id)}
                            empty="Nenhuma conversa aqui. Use Simular cliente para começar uma." />
        </div>
      </section>

      {!routeId && (
        <div className="pane pane-empty">
          <h2>Escolha uma conversa</h2>
          <p>Você vê cada mensagem e o que a plataforma fez entre elas: fila escolhida, transferência, quem assumiu.</p>
        </div>
      )}
      {routeId && detail.error && <div className="pane pane-empty"><p className="error">{detail.error}</p></div>}
      {routeId && detail.data && <Watch data={detail.data} />}
    </div>
  );
}

function Watch({ data }) {
  const { openSimulator, analyst } = useApp();
  const c = data.conversation;
  const open = c.status !== "closed";
  const actions = (
    <>
      {open && c.handled_by === "human" && analyst?.team_id === c.team_id && (
        <button type="button" className="btn btn-ghost" onClick={() => go("atendimento", c.id)}>
          <Headset size={15} aria-hidden="true" /> Abrir no atendimento
        </button>
      )}
      {c.channel === "chat" && (
        <button type="button" className="btn btn-ghost" onClick={() => openSimulator(c.id)}>
          <PenLine size={15} aria-hidden="true" /> Escrever como cliente
        </button>
      )}
    </>
  );
  return <ConversationView data={data} onBack={() => go("conversas")} actions={actions} />;
}
