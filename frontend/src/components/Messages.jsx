import { time } from "../format.js";

const AUTHOR = { customer: "Cliente", agent: "Agente (IA)", analyst: "Analista" };

export default function Messages({ messages }) {
  if (!messages?.length) return <p className="muted">Sem mensagens.</p>;
  return (
    <ol className="messages">
      {messages.map((m) => (
        <li key={m.id} className={`message message-${m.author}`}>
          <div className="message-meta">
            <strong>{AUTHOR[m.author] ?? m.author}</strong>
            <span>{time(m.created_at)}</span>
            {m.category && <span className="muted">{m.category} · {m.priority}</span>}
          </div>
          <div className="message-text">{m.text}</div>
        </li>
      ))}
    </ol>
  );
}
