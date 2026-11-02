import { useState } from "react";
import { api, query } from "../api.js";
import { usePolling } from "../usePolling.js";
import { BRANDS, CATEGORIES, CHANNELS, PRIORITIES } from "../format.js";
import { useToast } from "../components/Toast.jsx";

// Filas e regras vivem no banco: cada mudança vale para a próxima conversa, sem reiniciar nada
export default function Admin() {
  const [brand, setBrand] = useState("infinitepay");
  const queues = usePolling("/api/admin/queues", 5000);
  const rules = usePolling("/api/admin/routing-rules" + query({ brand }), 5000);
  const teams = usePolling("/api/admin/teams", 60000);
  const toast = useToast();

  async function change(path, method, body, done) {
    try {
      await api(path, { method, body });
      toast(done);
      queues.reload();
      rules.reload();
      return true;
    } catch (err) {
      toast(err.message, "error");
      return false;
    }
  }

  const brandQueues = (queues.data ?? []).filter((q) => q.brand_id === brand);
  const queueName = Object.fromEntries((queues.data ?? []).map((q) => [q.id, q.name]));
  const ctx = { brand, brandQueues, queueName, teams: teams.data ?? [], change };

  return (
    <div className="admin">
      <div className="admin-head">
        <h2>Filas e regras</h2>
        <p>As mudanças valem para a próxima conversa que chegar. Nada precisa ser reiniciado.</p>
        <div className="segmented" role="group" aria-label="Marca">
          {Object.entries(BRANDS).map(([k, v]) => (
            <button key={k} type="button" aria-pressed={brand === k} onClick={() => setBrand(k)}>{v}</button>
          ))}
        </div>
      </div>
      <Rules rules={rules.data} {...ctx} />
      <Queues {...ctx} />
    </div>
  );
}

function sentence(rule) {
  const parts = [];
  if (rule.channel) parts.push(<>o canal é <b>{CHANNELS[rule.channel]}</b></>);
  if (rule.category) parts.push(<>o assunto é <b>{CATEGORIES[rule.category]}</b></>);
  if (rule.priority) parts.push(<>a prioridade é <b>{PRIORITIES[rule.priority].toLowerCase()}</b></>);
  if (!parts.length) return <>Qualquer conversa{rule.brand_id ? "" : " de qualquer marca"}</>;
  return <>Se {parts.map((p, i) => <span key={i}>{i > 0 && " e "}{p}</span>)}</>;
}

function Rules({ rules, brand, brandQueues, queueName, change }) {
  const [adding, setAdding] = useState(false);
  const list = rules ?? [];

  async function move(index, delta) {
    const a = list[index];
    const b = list[index + delta];
    // Troca as posições das duas; se forem iguais, passa a frente (ou para trás) da vizinha
    const aPos = a.position === b.position ? b.position + (delta < 0 ? -1 : 1) : b.position;
    await change(`/api/admin/routing-rules/${a.id}`, "PATCH", { position: aPos }, "Ordem atualizada");
    if (a.position !== b.position) {
      await change(`/api/admin/routing-rules/${b.id}`, "PATCH", { position: a.position }, "Ordem atualizada");
    }
  }

  return (
    <section className="admin-section">
      <div className="section-head">
        <div>
          <h3>Para onde vai cada conversa</h3>
          <p>A primeira conversa do cliente é comparada com as regras de cima para baixo e vai para a fila da primeira que combinar. Se nenhuma combinar, vai para a fila padrão de {BRANDS[brand]}.</p>
        </div>
        {!adding && <button type="button" className="primary" onClick={() => setAdding(true)}>Nova regra</button>}
      </div>
      {adding && <NewRule brand={brand} brandQueues={brandQueues} change={change} onDone={() => setAdding(false)}
                          top={list.length ? Math.min(...list.map((r) => r.position)) - 1 : 10} />}
      <ol className="rules">
        {list.map((r, i) => (
          <li key={r.id} className={r.active ? "rule" : "rule off"}>
            <span className="rule-order">{i + 1}</span>
            <div className="rule-body">
              <p className="rule-sentence">
                {sentence(r)}, vai para <b className="rule-target">{queueName[r.queue_id]}</b>
              </p>
              <span className="rule-name">{r.name}{r.brand_id ? "" : " · vale para as duas marcas"}{r.active ? "" : " · desativada"}</span>
            </div>
            <div className="rule-controls">
              <button type="button" className="icon" disabled={i === 0} onClick={() => move(i, -1)}
                      aria-label={`Subir a regra ${r.name}`}>↑</button>
              <button type="button" className="icon" disabled={i === list.length - 1} onClick={() => move(i, 1)}
                      aria-label={`Descer a regra ${r.name}`}>↓</button>
              <Switch checked={r.active} label={`Regra ${r.name} ativa`}
                      onChange={(v) => change(`/api/admin/routing-rules/${r.id}`, "PATCH", { active: v },
                        v ? "Regra ativada" : "Regra desativada")} />
            </div>
          </li>
        ))}
        {rules && !list.length && <li className="empty">Nenhuma regra para {BRANDS[brand]}: tudo vai para a fila padrão.</li>}
      </ol>
    </section>
  );
}

function NewRule({ brand, brandQueues, change, onDone, top }) {
  const [form, setForm] = useState({ channel: "", category: "", priority: "", queue_id: "", name: "" });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  return (
    <form className="rule-builder" onSubmit={async (e) => {
      e.preventDefault();
      const body = {
        name: form.name || `${BRANDS[brand]}: ${CATEGORIES[form.category] ?? "regra"}`,
        position: top, brand_id: brand, queue_id: form.queue_id,
        channel: form.channel || null, category: form.category || null, priority: form.priority || null,
      };
      if (await change("/api/admin/routing-rules", "POST", body, "Regra criada")) onDone();
    }}>
      <p className="builder-sentence">
        Se o canal for
        <select value={form.channel} onChange={set("channel")}>
          <option value="">qualquer um</option>
          {Object.entries(CHANNELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        e o assunto for
        <select value={form.category} onChange={set("category")}>
          <option value="">qualquer um</option>
          {Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        e a prioridade for
        <select value={form.priority} onChange={set("priority")}>
          <option value="">qualquer uma</option>
          {Object.entries(PRIORITIES).map(([k, v]) => <option key={k} value={k}>{v.toLowerCase()}</option>)}
        </select>
        , mandar para
        <select value={form.queue_id} onChange={set("queue_id")} required>
          <option value="">escolha a fila</option>
          {brandQueues.filter((q) => q.active).map((q) => <option key={q.id} value={q.id}>{q.name}</option>)}
        </select>
      </p>
      <label className="builder-name">Nome da regra (opcional)
        <input value={form.name} onChange={set("name")} maxLength={120} placeholder="Ex.: Chargebacks para o time de pagamentos" />
      </label>
      <p className="hint">A regra nova entra no topo da lista. Use as setas para mudar a ordem depois.</p>
      <div className="form-actions">
        <button type="submit" className="primary">Criar regra</button>
        <button type="button" className="quiet" onClick={onDone}>Cancelar</button>
      </div>
    </form>
  );
}

function Queues({ brand, brandQueues, teams, change }) {
  const [adding, setAdding] = useState(false);
  return (
    <section className="admin-section">
      <div className="section-head">
        <div>
          <h3>Filas de {BRANDS[brand]}</h3>
          <p>Cada fila pertence a uma equipe e diz quem atende primeiro: a IA ou uma pessoa.</p>
        </div>
        {!adding && <button type="button" className="primary" onClick={() => setAdding(true)}>Nova fila</button>}
      </div>
      {adding && <NewQueue brand={brand} teams={teams} change={change} onDone={() => setAdding(false)} />}
      <ul className="queues">
        {brandQueues.map((q) => (
          <QueueCard key={q.id} queue={q} others={brandQueues.filter((o) => o.id !== q.id && o.active)}
                     teams={teams} change={change} />
        ))}
      </ul>
    </section>
  );
}

function QueueCard({ queue: q, others, teams, change }) {
  const patch = (body, done) => change(`/api/admin/queues/${q.id}`, "PATCH", body, done);
  return (
    <li className={q.active ? "queue" : "queue off"}>
      <div className="queue-title">
        <h4>{q.name}</h4>
        {q.is_default && <span className="default-mark">Fila padrão</span>}
        <Switch checked={q.active} label={`Fila ${q.name} ativa`}
                onChange={(v) => patch({ active: v }, v ? "Fila ativada" : "Fila desativada")} />
      </div>
      <div className="queue-fields">
        <label>Equipe
          <select value={q.team_id} onChange={(e) => patch({ team_id: e.target.value }, "Equipe alterada")}>
            {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>
        <div className="field">
          <span>Quem atende primeiro</span>
          <div className="segmented small" role="group" aria-label="Quem atende primeiro">
            <button type="button" aria-pressed={q.first_responder === "agent"}
                    onClick={() => patch({ first_responder: "agent" }, "Agora a IA atende primeiro")}>IA</button>
            <button type="button" aria-pressed={q.first_responder === "human"}
                    onClick={() => patch({ first_responder: "human" }, "Agora a equipe atende primeiro")}>Equipe</button>
          </div>
        </div>
        <label>Quando a IA transferir, enviar para
          <select value={q.escalation_queue_id ?? ""}
                  onChange={(e) => patch({ escalation_queue_id: e.target.value || null }, "Destino das transferências alterado")}>
            <option value="">esta mesma fila</option>
            {others.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        </label>
      </div>
      {!q.is_default && q.active && (
        <button type="button" className="link" onClick={() => patch({ is_default: true }, `${q.name} agora é a fila padrão`)}>
          Usar como fila padrão
        </button>
      )}
    </li>
  );
}

function NewQueue({ brand, teams, change, onDone }) {
  const [form, setForm] = useState({ name: "", team_id: "geral", first_responder: "agent" });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  return (
    <form className="rule-builder" onSubmit={async (e) => {
      e.preventDefault();
      if (await change("/api/admin/queues", "POST", { ...form, brand_id: brand }, "Fila criada")) onDone();
    }}>
      <div className="field-row">
        <label>Nome
          <input value={form.name} onChange={set("name")} required maxLength={120}
                 placeholder={`Ex.: ${BRANDS[brand]} · Chargebacks`} />
        </label>
        <label>Equipe
          <select value={form.team_id} onChange={set("team_id")}>
            {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>
        <label>Quem atende primeiro
          <select value={form.first_responder} onChange={set("first_responder")}>
            <option value="agent">IA</option>
            <option value="human">Equipe</option>
          </select>
        </label>
      </div>
      <p className="hint">A fila só recebe conversas depois que uma regra apontar para ela.</p>
      <div className="form-actions">
        <button type="submit" className="primary">Criar fila</button>
        <button type="button" className="quiet" onClick={onDone}>Cancelar</button>
      </div>
    </form>
  );
}

function Switch({ checked, onChange, label }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label}
            className="switch" onClick={() => onChange(!checked)}>
      <span className="switch-track"><span className="switch-thumb" /></span>
      <span className="switch-text">{checked ? "Ativa" : "Desativada"}</span>
    </button>
  );
}
