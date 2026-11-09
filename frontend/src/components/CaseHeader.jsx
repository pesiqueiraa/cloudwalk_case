import * as Tooltip from "@radix-ui/react-tooltip";
import { ArrowLeft, PanelRight, Waypoints } from "lucide-react";
import { BRANDS, CHANNELS } from "../format.js";
import Status from "./Status.jsx";

export function Tip({ label, children }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="tip" sideOffset={6}>{label}</Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export default function CaseHeader({ conversation: c, onBack, onToggleContext, contextOpen, onTrace, children }) {
  return (
    <header className="case-head">
      <div className="case-id">
        {onBack && (
          <button type="button" className="btn btn-icon back" onClick={onBack} aria-label="Voltar à lista">
            <ArrowLeft size={16} />
          </button>
        )}
        <div className="case-name">
          <h1>{c.customer_name}</h1>
          <p>{BRANDS[c.brand_id]}, {CHANNELS[c.channel] ?? c.channel}{c.queue_name ? `, fila ${c.queue_name}` : ""}</p>
        </div>
        <Status conversation={c} />
        {c.priority === "high" && <span className="flag-high">Prioridade alta</span>}
      </div>
      <div className="case-tools">
        {children}
        <Tip label="Rastro técnico">
          <button type="button" className="btn btn-icon" onClick={onTrace} aria-label="Abrir rastro técnico">
            <Waypoints size={16} />
          </button>
        </Tip>
        <Tip label={contextOpen ? "Esconder contexto" : "Mostrar contexto"}>
          <button type="button" className="btn btn-icon" onClick={onToggleContext} aria-pressed={contextOpen}
                  aria-label="Contexto do atendimento">
            <PanelRight size={16} />
          </button>
        </Tip>
      </div>
    </header>
  );
}
