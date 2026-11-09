import { useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { toast } from "sonner";
import { api, query } from "../api.js";
import { usePolling } from "../usePolling.js";
import { BRANDS } from "../format.js";
import { useApp } from "../hooks.js";
import Rules from "./admin/Rules.jsx";
import Queues from "./admin/Queues.jsx";

// Filas e regras vivem no banco: cada mudança vale para a próxima conversa, sem reiniciar nada
export default function Admin() {
  const { teams } = useApp();
  const [brand, setBrand] = useState("infinitepay");
  const queues = usePolling("/api/admin/queues", 5000);
  const rules = usePolling("/api/admin/routing-rules" + query({ brand }), 5000);

  async function change(path, method, body, done) {
    try {
      await api(path, { method, body });
      if (done) toast.success(done);
      queues.reload();
      rules.reload();
      return true;
    } catch (err) {
      toast.error(err.message);
      return false;
    }
  }

  const brandQueues = (queues.data ?? []).filter((q) => q.brand_id === brand);
  const queueName = Object.fromEntries((queues.data ?? []).map((q) => [q.id, q.name]));
  const ctx = { brand, brandQueues, queueName, teams, change };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Configuração</h1>
          <p>As mudanças valem para a próxima conversa que chegar, sem reiniciar nada.</p>
        </div>
        <div className="segmented" role="group" aria-label="Marca">
          {Object.entries(BRANDS).map(([k, v]) => (
            <button key={k} type="button" aria-pressed={brand === k} onClick={() => setBrand(k)}>{v}</button>
          ))}
        </div>
      </header>
      <Tabs.Root defaultValue="rules" className="tabs">
        <Tabs.List className="tab-list" aria-label="O que configurar">
          <Tabs.Trigger value="rules" className="tab">Regras de roteamento</Tabs.Trigger>
          <Tabs.Trigger value="queues" className="tab">Filas</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="rules" className="tab-panel">
          <Rules rules={rules.data} {...ctx} />
        </Tabs.Content>
        <Tabs.Content value="queues" className="tab-panel">
          <Queues loaded={!!queues.data} {...ctx} />
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}
