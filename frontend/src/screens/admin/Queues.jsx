import { useState } from "react";
import { Plus } from "lucide-react";
import { BRANDS, FRUSTRATION } from "../../format.js";
import Sheet from "../../components/Sheet.jsx";
import Toggle from "../../components/Toggle.jsx";

const RESPONDER = { agent: "IA", human: "Equipe" };

export default function Queues({ loaded, brand, brandQueues, queueName, teams, change }) {
  const [editing, setEditing] = useState(null); // null fechado, "new" criando, ou a fila em edição
  const teamName = Object.fromEntries(teams.map((t) => [t.id, t.name]));

  return (
    <section className="section">
      <div className="section-head">
        <p>Cada fila pertence a uma equipe e diz quem atende primeiro: a IA ou uma pessoa.</p>
        <button type="button" className="btn btn-primary" onClick={() => setEditing("new")}>
          <Plus size={15} aria-hidden="true" /> Nova fila
        </button>
      </div>

      {!loaded && <div className="skeleton skeleton-tall" aria-busy="true" />}
      <ul className="queues">
        {brandQueues.map((q) => (
          <li key={q.id} className={q.active ? "queue" : "queue queue-off"}>
            <div className="queue-body">
              <p className="queue-name">
                {q.name}
                {q.is_default && <span className="tag">Padrão</span>}
              </p>
              <small>
                {teamName[q.team_id] ?? q.team_id}. Atende primeiro: {RESPONDER[q.first_responder]}.
                {" "}Transferências: {q.escalation_queue_id ? queueName[q.escalation_queue_id] : "a própria fila"}.
                {q.escalate_on_frustration != null && q.first_responder === "agent" &&
                  <> Passa para a equipe a partir de “{FRUSTRATION[q.escalate_on_frustration].toLowerCase()}”.</>}
              </small>
            </div>
            <div className="queue-tools">
              <button type="button" className="btn btn-ghost" onClick={() => setEditing(q)}>Editar</button>
              <Toggle checked={q.active} label={`Fila ${q.name} ativa`}
                      onChange={(v) => change(`/api/admin/queues/${q.id}`, "PATCH", { active: v },
                        v ? "Fila ativada" : "Fila desativada")} />
            </div>
          </li>
        ))}
      </ul>

      <Sheet open={!!editing} onOpenChange={(o) => !o && setEditing(null)} side="center" width="520px"
             title={editing === "new" ? `Nova fila em ${BRANDS[brand]}` : `Editar ${editing?.name ?? ""}`}
             description={editing === "new" ? "A fila só recebe conversas depois que uma regra apontar para ela." : undefined}>
        {editing && (
          <QueueForm key={editing === "new" ? "new" : editing.id} queue={editing === "new" ? null : editing}
                     brand={brand} teams={teams} change={change} onDone={() => setEditing(null)}
                     others={brandQueues.filter((o) => o.active && o.id !== editing?.id)} />
        )}
      </Sheet>
    </section>
  );
}

function QueueForm({ queue, brand, teams, others, change, onDone }) {
  const initial = queue
    ? { name: queue.name, team_id: queue.team_id, first_responder: queue.first_responder,
        escalation_queue_id: queue.escalation_queue_id ?? "", is_default: queue.is_default,
        escalate_on_frustration: queue.escalate_on_frustration ?? "" }
    : { name: "", team_id: teams[0]?.id ?? "", first_responder: "agent", escalation_queue_id: "", is_default: false,
        escalate_on_frustration: "" };
  const [form, setForm] = useState(initial);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function save(e) {
    e.preventDefault();
    const body = { ...form, escalation_queue_id: form.escalation_queue_id || null,
                   escalate_on_frustration: form.escalate_on_frustration === "" ? null : Number(form.escalate_on_frustration) };
    if (!queue) {
      if (await change("/api/admin/queues", "POST", { ...body, brand_id: brand }, "Fila criada")) onDone();
      return;
    }
    // Manda só o que mudou
    const changed = Object.fromEntries(Object.entries(body).filter(([k, v]) => v !== (initial[k] === "" ? null : initial[k])));
    if (!Object.keys(changed).length) return onDone();
    if (await change(`/api/admin/queues/${queue.id}`, "PATCH", changed, "Alterações salvas")) onDone();
  }

  return (
    <form className="form" onSubmit={save}>
      <label className="field"><span className="field-label">Nome</span>
        <input value={form.name} onChange={set("name")} required maxLength={120} placeholder={`Ex.: ${BRANDS[brand]} Chargebacks`} />
      </label>
      <div className="form-grid">
        <label className="field"><span className="field-label">Equipe</span>
          <select value={form.team_id} onChange={set("team_id")}>
            {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>
        <div className="field">
          <span className="field-label" id="responder">Quem atende primeiro</span>
          <div className="segmented" role="group" aria-labelledby="responder">
            {Object.entries(RESPONDER).map(([k, v]) => (
              <button key={k} type="button" aria-pressed={form.first_responder === k}
                      onClick={() => setForm({ ...form, first_responder: k })}>{v}</button>
            ))}
          </div>
        </div>
      </div>
      <label className="field"><span className="field-label">Quando a conversa for para a equipe, enviar para</span>
        <select value={form.escalation_queue_id} onChange={set("escalation_queue_id")}>
          <option value="">Esta mesma fila</option>
          {others.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      </label>
      {form.first_responder === "agent" && (
        <label className="field"><span className="field-label">Passar para a equipe quando o cliente estiver</span>
          <select value={form.escalate_on_frustration} onChange={set("escalate_on_frustration")}>
            <option value="">Nunca (a IA decide quando transferir)</option>
            {FRUSTRATION.slice(1).map((label, i) => <option key={i + 1} value={i + 1}>{label} ou mais</option>)}
          </select>
          <small className="field-hint">Frustração medida pelo Jev em cada mensagem. Um pedido explícito de pessoa sempre transfere.</small>
        </label>
      )}
      {(!queue || (!queue.is_default && queue.active)) && (
        <label className="check">
          <input type="checkbox" checked={form.is_default} onChange={(e) => setForm({ ...form, is_default: e.target.checked })} />
          Usar como fila padrão de {BRANDS[brand]}
        </label>
      )}
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onDone}>Cancelar</button>
        <button type="submit" className="btn btn-primary">{queue ? "Salvar alterações" : "Criar fila"}</button>
      </div>
    </form>
  );
}
