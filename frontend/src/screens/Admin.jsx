import { useState } from "react";
import { api } from "../api.js";
import { usePolling } from "../usePolling.js";
import { BRANDS, CATEGORIES, CHANNELS } from "../format.js";
import Badge from "../components/Badge.jsx";

// Filas e regras vivem no banco: cada mudança vale no atendimento seguinte, sem reiniciar nada
export default function Admin() {
  const queues = usePolling("/api/admin/queues", 5000);
  const rules = usePolling("/api/admin/routing-rules", 5000);
  const teams = usePolling("/api/admin/teams", 60000);
  const [error, setError] = useState(null);

  async function change(path, method, body) {
    setError(null);
    try {
      await api(path, { method, body });
      queues.reload();
      rules.reload();
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    }
  }

  const queueList = queues.data ?? [];
  const queueName = Object.fromEntries(queueList.map((q) => [q.id, q.name]));
  const props = { queues: queueList, teams: teams.data ?? [], change };

  return (
    <div className="stack">
      {error && <p className="error">{error}</p>}
      <section className="panel">
        <h2>Filas</h2>
        <table>
          <thead>
            <tr><th>Fila</th><th>Marca</th><th>Equipe</th><th>Atende primeiro</th><th>Fila de escalas</th>
              <th>Padrão</th><th>Ativa</th></tr>
          </thead>
          <tbody>{queueList.map((q) => <QueueRow key={q.id} queue={q} {...props} />)}</tbody>
        </table>
        <NewQueue {...props} />
      </section>
      <section className="panel">
        <h2>Regras de roteamento <span className="muted small">avaliadas por posição; vale a primeira que casa; vazio = qualquer</span></h2>
        <table>
          <thead>
            <tr><th>Posição</th><th>Regra</th><th>Marca</th><th>Canal</th><th>Categoria</th><th>Prioridade</th>
              <th>Fila de destino</th><th>Ativa</th></tr>
          </thead>
          <tbody>
            {(rules.data ?? []).map((r) => (
              <tr key={r.id} className={r.active ? "" : "inactive"}>
                <td>
                  <input type="number" className="narrow" defaultValue={r.position}
                         onBlur={(e) => Number(e.target.value) !== r.position &&
                           change(`/api/admin/routing-rules/${r.id}`, "PATCH", { position: Number(e.target.value) })} />
                </td>
                <td>{r.name}</td>
                <td>{BRANDS[r.brand_id] ?? "qualquer"}</td>
                <td>{r.channel ?? "qualquer"}</td>
                <td>{r.category ?? "qualquer"}</td>
                <td>{r.priority ?? "qualquer"}</td>
                <td>{queueName[r.queue_id]}</td>
                <td>
                  <input type="checkbox" checked={r.active}
                         onChange={(e) => change(`/api/admin/routing-rules/${r.id}`, "PATCH", { active: e.target.checked })} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <NewRule {...props} />
      </section>
    </div>
  );
}

function QueueRow({ queue: q, queues, teams, change }) {
  const patch = (body) => change(`/api/admin/queues/${q.id}`, "PATCH", body);
  const sameBrand = queues.filter((o) => o.brand_id === q.brand_id && o.id !== q.id && o.active);
  return (
    <tr className={q.active ? "" : "inactive"}>
      <td>{q.name}</td>
      <td>{BRANDS[q.brand_id]}</td>
      <td>
        <select value={q.team_id} onChange={(e) => patch({ team_id: e.target.value })}>
          {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </td>
      <td>
        <select value={q.first_responder} onChange={(e) => patch({ first_responder: e.target.value })}>
          <option value="agent">agente (IA)</option>
          <option value="human">humano</option>
        </select>
      </td>
      <td>
        <select value={q.escalation_queue_id ?? ""} onChange={(e) => patch({ escalation_queue_id: e.target.value || null })}>
          <option value="">a própria fila</option>
          {sameBrand.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      </td>
      <td>
        {q.is_default ? <Badge value="open" label="padrão" />
          : <button className="link" disabled={!q.active} onClick={() => patch({ is_default: true })}>tornar padrão</button>}
      </td>
      <td><input type="checkbox" checked={q.active} onChange={(e) => patch({ active: e.target.checked })} /></td>
    </tr>
  );
}

function NewQueue({ teams, change }) {
  const empty = { name: "", brand_id: "infinitepay", team_id: "geral", first_responder: "agent" };
  const [form, setForm] = useState(empty);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  return (
    <form className="inline-form" onSubmit={async (e) => {
      e.preventDefault();
      if (await change("/api/admin/queues", "POST", form)) setForm(empty);
    }}>
      <strong>Nova fila</strong>
      <input value={form.name} onChange={set("name")} placeholder="Nome (ex.: JIM · Chargebacks)" required />
      <select value={form.brand_id} onChange={set("brand_id")}>
        {Object.entries(BRANDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <select value={form.team_id} onChange={set("team_id")}>
        {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
      </select>
      <select value={form.first_responder} onChange={set("first_responder")}>
        <option value="agent">agente (IA)</option>
        <option value="human">humano</option>
      </select>
      <button type="submit">Criar fila</button>
    </form>
  );
}

function NewRule({ queues, change }) {
  const empty = { name: "", position: 1, brand_id: "", channel: "", category: "", priority: "", queue_id: "" };
  const [form, setForm] = useState(empty);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const targets = queues.filter((q) => q.active && (!form.brand_id || q.brand_id === form.brand_id));
  return (
    <form className="inline-form" onSubmit={async (e) => {
      e.preventDefault();
      const body = { ...form, position: Number(form.position) };
      for (const k of ["brand_id", "channel", "category", "priority"]) if (!body[k]) body[k] = null;
      if (await change("/api/admin/routing-rules", "POST", body)) setForm(empty);
    }}>
      <strong>Nova regra</strong>
      <input type="number" className="narrow" value={form.position} onChange={set("position")} title="posição" />
      <input value={form.name} onChange={set("name")} placeholder="Nome" required />
      <select value={form.brand_id} onChange={set("brand_id")}>
        <option value="">qualquer marca</option>
        {Object.entries(BRANDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <select value={form.channel} onChange={set("channel")}>
        <option value="">qualquer canal</option>
        {CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
      <select value={form.category} onChange={set("category")}>
        <option value="">qualquer categoria</option>
        {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
      <select value={form.priority} onChange={set("priority")}>
        <option value="">qualquer prioridade</option>
        <option value="high">alta</option>
        <option value="normal">normal</option>
      </select>
      <select value={form.queue_id} onChange={set("queue_id")} required>
        <option value="">fila de destino</option>
        {targets.map((q) => <option key={q.id} value={q.id}>{q.name}</option>)}
      </select>
      <button type="submit">Criar regra</button>
    </form>
  );
}
