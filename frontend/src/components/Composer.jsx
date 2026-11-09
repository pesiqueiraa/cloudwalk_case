import { useState } from "react";
import { SendHorizontal } from "lucide-react";

// Enter envia, Shift+Enter quebra a linha. onSend devolve true quando deu certo.
export default function Composer({ label, placeholder, onSend, action = "Enviar", tone = "neutral" }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e?.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    const ok = await onSend(text.trim());
    setBusy(false);
    if (ok) setText("");
  }

  return (
    <form className={`composer composer-${tone}`} onSubmit={submit}>
      <label className="sr-only" htmlFor={`composer-${tone}`}>{label}</label>
      <textarea id={`composer-${tone}`} rows={1} value={text} maxLength={4000} placeholder={placeholder}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) submit(e); }} />
      <button type="submit" className="btn btn-primary" disabled={!text.trim() || busy}>
        <SendHorizontal size={15} aria-hidden="true" />
        {action}
      </button>
    </form>
  );
}
