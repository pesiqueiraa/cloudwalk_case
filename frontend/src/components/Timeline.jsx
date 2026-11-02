import { preciseTime } from "../format.js";

// Detalhes técnicos: a auditoria crua, com o trace_id que liga os eventos entre os serviços
export default function Timeline({ events }) {
  if (!events?.length) return <p className="empty">Sem eventos.</p>;
  return (
    <table className="audit">
      <thead><tr><th>Hora</th><th>Evento</th><th>Quem</th><th>trace_id</th></tr></thead>
      <tbody>
        {events.map((e) => (
          <tr key={e.id}>
            <td className="num">{preciseTime(e.occurred_at)}</td>
            <td>{e.type}</td>
            <td>{e.actor}</td>
            <td className="trace" title={e.trace_id}>{e.trace_id}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
