import { toast } from "sonner";
import { CheckCircle2, Hand, MessageSquarePlus } from "lucide-react";
import { api, query } from "../api.js";
import { usePolling } from "../usePolling.js";
import { dateTime } from "../format.js";
import { go, useApp } from "../hooks.js";
import { initials } from "../components/AnalystMenu.jsx";
import Composer from "../components/Composer.jsx";
import ConversationList from "../components/ConversationList.jsx";
import ConversationView from "../components/ConversationView.jsx";

const preview = (c) => c.escalation_summary ?? "Chegou direto na fila da equipe, sem passar pela IA.";

export default function Analyst({ routeId }) {
  const { analyst, teamName } = useApp();
  const queue = usePolling(analyst ? "/api/escalations" + query({ team_id: analyst.team_id }) : null);
  const caseView = usePolling(analyst && routeId ? `/api/cases/${routeId}` : null);

  if (!analyst) return <WhoAreYou />;

  const all = queue.data;
  const waiting = all?.filter((c) => !c.assigned_analyst_id);
  const mine = all?.filter((c) => c.assigned_analyst_id === analyst.id);
  const others = all?.filter((c) => c.assigned_analyst_id && c.assigned_analyst_id !== analyst.id) ?? [];
  const select = (id) => go("atendimento", id);

  return (
    <div className={routeId ? "workspace has-selection" : "workspace"}>
      <section className="pane pane-list" aria-label="Fila da equipe">
        <div className="pane-head">
          <h1>Fila de {teamName[analyst.team_id] ?? analyst.team_id}</h1>
        </div>
        <div className="pane-scroll">
          {queue.error && <p className="error">Não consegui carregar a fila: {queue.error}</p>}
          <Group title="Esperando" count={waiting?.length}>
            <ConversationList items={waiting} selected={routeId} onSelect={select} preview={preview}
                              empty="Ninguém esperando agora." />
          </Group>
          <Group title="Com você" count={mine?.length}>
            <ConversationList items={mine} selected={routeId} onSelect={select} preview={preview}
                              empty="Você não tem casos abertos." />
          </Group>
          {others.length > 0 && (
            <details className="group group-fold">
              <summary><h2>Com colegas</h2><span className="count">{others.length}</span></summary>
              <ConversationList items={others} selected={routeId} onSelect={select} preview={preview} />
            </details>
          )}
        </div>
      </section>

      {!routeId && <EmptyCase hasQueue={!!all?.length} />}
      {routeId && caseView.error && <div className="pane pane-empty"><p className="error">{caseView.error}</p></div>}
      {routeId && caseView.data && (
        <Case data={caseView.data} analyst={analyst} onBack={() => go("atendimento")}
              onChange={() => { caseView.reload(); queue.reload(); }} />
      )}
    </div>
  );
}

function Group({ title, count, children }) {
  return (
    <div className="group">
      <h2>{title}{count ? <span className="count">{count}</span> : null}</h2>
      {children}
    </div>
  );
}

function Case({ data, analyst, onBack, onChange }) {
  const c = data.conversation;
  const mine = c.assigned_analyst_id === analyst.id;
  const open = c.status !== "closed";
  const isTeam = c.team_id === analyst.team_id;

  async function act(path, done, body = {}) {
    try {
      await api(`/api/conversations/${c.id}/${path}`, { method: "POST", body: { analyst_id: analyst.id, ...body } });
      if (done) toast.success(done);
      onChange();
      return true;
    } catch (err) {
      toast.error(err.message);
      return false;
    }
  }

  let actions = null;
  let footer = null;
  if (!open) {
    footer = <p className="note">Encerrado em {dateTime(c.closed_at)}. Uma nova mensagem do cliente abre outro atendimento.</p>;
  } else if (c.handled_by !== "human") {
    footer = <p className="note">A IA está atendendo esta conversa. Ela chega aqui se for transferida para a equipe.</p>;
  } else if (!c.assigned_analyst_id) {
    footer = isTeam ? (
      <div className="claim">
        <p>Ninguém assumiu este caso ainda.</p>
        <button type="button" className="btn btn-primary" onClick={() => act("assign", "Caso assumido")}>
          <Hand size={15} aria-hidden="true" /> Assumir caso
        </button>
      </div>
    ) : <p className="note">Este caso é de outra equipe.</p>;
  } else if (mine) {
    actions = (
      <button type="button" className="btn btn-ghost" onClick={() => act("close", "Caso encerrado")}>
        <CheckCircle2 size={15} aria-hidden="true" /> Encerrar caso
      </button>
    );
    footer = <Composer label={`Responder a ${c.customer_name}`} placeholder={`Responder a ${c.customer_name}`}
                       action="Responder" tone="analyst" onSend={(text) => act("messages", null, { text })} />;
  } else {
    footer = <p className="note">{c.assigned_analyst_name} está cuidando deste caso.</p>;
  }

  return <ConversationView data={data} onBack={onBack} actions={actions} footer={footer} />;
}

function EmptyCase({ hasQueue }) {
  const { openSimulator } = useApp();
  return (
    <div className="pane pane-empty">
      {hasQueue ? (
        <>
          <h2>Escolha um caso na fila</h2>
          <p>Os que ninguém assumiu e os de prioridade alta ficam no topo.</p>
        </>
      ) : (
        <>
          <h2>Sua fila está vazia</h2>
          <p>Para ver um caso chegar, simule um cliente que pede para falar com um atendente.</p>
          <button type="button" className="btn btn-ghost" onClick={() => openSimulator()}>
            <MessageSquarePlus size={15} aria-hidden="true" /> Simular cliente
          </button>
        </>
      )}
    </div>
  );
}

function WhoAreYou() {
  const { teamsWithAnalysts, chooseAnalyst } = useApp();
  return (
    <div className="welcome">
      <h1>Quem está atendendo?</h1>
      <p>Escolha seu nome para ver a fila da sua equipe. Dá para trocar depois, no canto superior direito.</p>
      {!teamsWithAnalysts.length && <div className="skeleton skeleton-tall" aria-busy="true" />}
      <div className="teams">
        {teamsWithAnalysts.map((t) => (
          <section key={t.id} className="team">
            <h2>{t.name}</h2>
            <ul>
              {t.analysts.map((a) => (
                <li key={a.id}>
                  <button type="button" className="person" onClick={() => chooseAnalyst(a.id)}>
                    <span className="avatar" aria-hidden="true">{initials(a.name)}</span>
                    {a.name}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
