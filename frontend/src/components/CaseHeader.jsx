import { BRANDS, CHANNELS, PRIORITIES, situation } from "../format.js";
import Status from "./Status.jsx";

// A faixa do topo muda de cor com quem atende: anil com a IA, cobre com a equipe
export default function CaseHeader({ conversation: c, onBack, children }) {
  const tone = situation(c)?.tone ?? "ai";
  return (
    <header className={`case-header case-${tone}`}>
      {onBack && <button type="button" className="back" onClick={onBack}>Voltar à lista</button>}
      <div className="case-title">
        <h1>{c.customer_name}</h1>
        <Status conversation={c} />
        {c.priority === "high" && <span className="priority">Prioridade {PRIORITIES.high.toLowerCase()}</span>}
      </div>
      <p className="case-meta">
        {BRANDS[c.brand_id]}, por {CHANNELS[c.channel] ?? c.channel}. Fila {c.queue_name ?? "ainda não definida"}.
      </p>
      {children}
    </header>
  );
}
