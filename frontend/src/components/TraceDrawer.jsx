import { preciseTime } from "../format.js";
import Sheet from "./Sheet.jsx";

// A auditoria crua: cada evento com o trace_id que liga os registros de todos os serviços
export default function TraceDrawer({ open, onOpenChange, events }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="Rastro técnico" width="640px"
           description="Eventos de auditoria desta conversa, na ordem em que aconteceram. Mensagens com o mesmo trace_id passaram pelos mesmos serviços.">
      {!events?.length ? <p className="empty">Sem eventos.</p> : (
        <ol className="trace">
          {events.map((e) => (
            <li key={e.id}>
              <time>{preciseTime(e.occurred_at)}</time>
              <span className="trace-type">{e.type}</span>
              <span className="trace-actor">{e.actor}</span>
              <code className="trace-id" title={e.trace_id}>{e.trace_id}</code>
            </li>
          ))}
        </ol>
      )}
    </Sheet>
  );
}
