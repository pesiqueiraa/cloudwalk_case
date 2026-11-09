import { useState } from "react";
import { ArrowDown, ArrowUp, Plus } from "lucide-react";
import { BRANDS, CATEGORIES, CHANNELS, PRIORITIES } from "../../format.js";
import Sheet from "../../components/Sheet.jsx";
import Toggle from "../../components/Toggle.jsx";

function sentence(rule) {
  const parts = [];
  if (rule.channel) parts.push(<>o canal é <b>{CHANNELS[rule.channel]}</b></>);
  if (rule.category) parts.push(<>o assunto é <b>{CATEGORIES[rule.category]}</b></>);
  if (rule.priority) parts.push(<>a prioridade é <b>{PRIORITIES[rule.priority].toLowerCase()}</b></>);
  if (!parts.length) return <>Qualquer conversa</>;
  return <>Se {parts.map((p, i) => <span key={i}>{i > 0 && " e "}{p}</span>)}</>;
}

export default function Rules({ rules, brand, brandQueues, queueName, change }) {
  const [adding, setAdding] = useState(false);
  const list = rules ?? [];
  const fallback = brandQueues.find((q) => q.is_default && q.active);

  async function move(index, delta) {
    const a = list[index];
    const b = list[index + delta];
    // Troca as posições das duas; se forem iguais, passa à frente (ou para trás) da vizinha
    const aPos = a.position === b.position ? b.position + (delta < 0 ? -1 : 1) : b.position;
    await change(`/api/admin/routing-rules/${a.id}`, "PATCH", { position: aPos }, null);
    if (a.position !== b.position) await change(`/api/admin/routing-rules/${b.id}`, "PATCH", { position: a.position }, null);
  }

  return (
    <section className="section">
      <div className="section-head">
        <p>A primeira mensagem do cliente é comparada com as regras de cima para baixo. Vale a primeira que combinar.</p>
        <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
          <Plus size={15} aria-hidden="true" /> Nova regra
        </button>
      </div>

      {!rules && <div className="skeleton skeleton-tall" aria-busy="true" />}
      <ol className="rules">
        {list.map((r, i) => (
          <li key={r.id} className={r.active ? "rule" : "rule rule-off"}>
            <span className="rule-pos" aria-label={`Posição ${i + 1}`}>{i + 1}</span>
            <div className="rule-body">
              <p>{sentence(r)}, vai para <b>{queueName[r.queue_id]}</b></p>
              <small>{r.name}{r.brand_id ? "" : ", vale para as duas marcas"}</small>
            </div>
            <div className="rule-tools">
              <button type="button" className="btn btn-icon" disabled={i === 0} onClick={() => move(i, -1)}
                      aria-label={`Subir a regra ${r.name}`}><ArrowUp size={15} /></button>
              <button type="button" className="btn btn-icon" disabled={i === list.length - 1} onClick={() => move(i, 1)}
                      aria-label={`Descer a regra ${r.name}`}><ArrowDown size={15} /></button>
              <Toggle checked={r.active} label={`Regra ${r.name} ativa`}
                      onChange={(v) => change(`/api/admin/routing-rules/${r.id}`, "PATCH", { active: v },
                        v ? "Regra ativada" : "Regra desativada")} />
            </div>
          </li>
        ))}
        {rules && (
          <li className="rule rule-fallback">
            <span className="rule-pos" aria-hidden="true" />
            <div className="rule-body">
              <p>Se nenhuma combinar, vai para <b>{fallback?.name ?? "a fila padrão"}</b></p>
              <small>Fila padrão de {BRANDS[brand]}. Dá para trocar na aba Filas.</small>
            </div>
          </li>
        )}
      </ol>

      <Sheet open={adding} onOpenChange={setAdding} side="center" width="560px" title="Nova regra"
             description="A regra nova entra no topo da lista. Depois, use as setas para mudar a ordem.">
        <NewRule brand={brand} brandQueues={brandQueues} change={change} onDone={() => setAdding(false)}
                 top={list.length ? Math.min(...list.map((r) => r.position)) - 1 : 10} />
      </Sheet>
    </section>
  );
}

function NewRule({ brand, brandQueues, change, onDone, top }) {
  const [form, setForm] = useState({ channel: "", category: "", priority: "", queue_id: "", name: "" });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  return (
    <form className="form" onSubmit={async (e) => {
      e.preventDefault();
      const body = {
        name: form.name || `${BRANDS[brand]}: ${CATEGORIES[form.category] ?? "regra"}`,
        position: top, brand_id: brand, queue_id: form.queue_id,
        channel: form.channel || null, category: form.category || null, priority: form.priority || null,
      };
      if (await change("/api/admin/routing-rules", "POST", body, "Regra criada")) onDone();
    }}>
      <p className="form-hint">Deixe em “qualquer” o que não importa.</p>
      <div className="form-grid">
        <label className="field"><span className="field-label">Canal</span>
          <select value={form.channel} onChange={set("channel")}>
            <option value="">Qualquer</option>
            {Object.entries(CHANNELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="field"><span className="field-label">Assunto</span>
          <select value={form.category} onChange={set("category")}>
            <option value="">Qualquer</option>
            {Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="field"><span className="field-label">Prioridade</span>
          <select value={form.priority} onChange={set("priority")}>
            <option value="">Qualquer</option>
            {Object.entries(PRIORITIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="field"><span className="field-label">Mandar para a fila</span>
          <select value={form.queue_id} onChange={set("queue_id")} required>
            <option value="">Escolha a fila</option>
            {brandQueues.filter((q) => q.active).map((q) => <option key={q.id} value={q.id}>{q.name}</option>)}
          </select>
        </label>
      </div>
      <label className="field"><span className="field-label">Nome da regra (opcional)</span>
        <input value={form.name} onChange={set("name")} maxLength={120} placeholder="Ex.: Chargebacks para pagamentos" />
      </label>
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onDone}>Cancelar</button>
        <button type="submit" className="btn btn-primary">Criar regra</button>
      </div>
    </form>
  );
}
