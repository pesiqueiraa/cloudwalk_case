import { CHANNELS, BRANDS, ago } from "../format.js";
import Status from "./Status.jsx";

export default function ConversationList({ items, selected, onSelect, empty, preview = (c) => c.last_message_text }) {
  if (!items) return <p className="empty">Carregando…</p>;
  if (!items.length) return <p className="empty">{empty}</p>;
  return (
    <ul className="list">
      {items.map((c) => (
        <li key={c.id}>
          <button type="button" className={c.id === selected ? "item selected" : "item"} onClick={() => onSelect(c.id)}
                  aria-current={c.id === selected ? "true" : undefined}>
            <span className="item-top">
              <strong>{c.customer_name}</strong>
              <time>{ago(c.last_message_at ?? c.escalated_at ?? c.created_at)}</time>
            </span>
            <span className="item-text">{preview(c)}</span>
            <span className="item-bottom">
              <Status conversation={c} />
              {c.priority === "high" && <span className="priority">Alta</span>}
              <span className="item-where">{BRANDS[c.brand_id]} · {CHANNELS[c.channel]}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
