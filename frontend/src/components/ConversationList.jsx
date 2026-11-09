import { BRANDS, ago, situation } from "../format.js";

export default function ConversationList({ items, selected, onSelect, empty, preview = (c) => c.last_message_text }) {
  if (!items) return <SkeletonList />;
  if (!items.length) return empty ? <p className="empty">{empty}</p> : null;
  return (
    <ul className="list">
      {items.map((c) => {
        const s = situation(c);
        return (
          <li key={c.id}>
            <button type="button" className="item" onClick={() => onSelect(c.id)}
                    aria-current={c.id === selected ? "true" : undefined}>
              <span className={`item-dot dot-${s?.tone ?? "ai"}`} aria-hidden="true" />
              <span className="item-main">
                <span className="item-top">
                  <strong>{c.customer_name}</strong>
                  <time>{ago(c.last_message_at ?? c.escalated_at ?? c.created_at)}</time>
                </span>
                <span className="item-text">{preview(c) ?? "Sem mensagens"}</span>
                <span className="item-meta">
                  {s?.label}
                  <span className="item-brand">{BRANDS[c.brand_id]}</span>
                  {c.priority === "high" && <span className="flag-high">Alta</span>}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function SkeletonList() {
  return (
    <ul className="list" aria-busy="true" aria-label="Carregando">
      {[0, 1, 2].map((i) => <li key={i} className="skeleton" />)}
    </ul>
  );
}
