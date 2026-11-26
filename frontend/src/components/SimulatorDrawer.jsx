import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ExternalLink, RotateCcw } from "lucide-react";
import { api } from "../api.js";
import { usePolling } from "../usePolling.js";
import { BRANDS, time } from "../format.js";
import { go } from "../hooks.js";
import Composer from "./Composer.jsx";
import Sheet from "./Sheet.jsx";

// Clientes sintéticos, os mesmos do simulador (simulator/data.py)
const CUSTOMERS = {
  infinitepay: [
    { external_id: "sim-ip-001", name: "Ana Ficticia", email: "ana.ficticia@example.com" },
    { external_id: "sim-ip-002", name: "Bruno Inventado", email: "bruno.inventado@example.com" },
    { external_id: "sim-ip-003", name: "Carla Sintetica", email: "carla.sintetica@example.com" },
  ],
  jim: [
    { external_id: "sim-jim-001", name: "John Placeholder", email: "john.placeholder@example.com" },
    { external_id: "sim-jim-002", name: "Mary Sample", email: "mary.sample@example.com" },
  ],
};

const SUGGESTIONS = {
  infinitepay: ["Minha maquininha não liga", "Não recebi o pagamento de ontem", "Quero falar com um atendente",
    "Fui vítima de golpe, clonaram meu cartão"],
  jim: ["My card reader is off", "I didn't get yesterday's payout", "I want to talk to a human", "My card was cloned"],
};

function uid() {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

async function sendAsCustomer({ session, brand, customer, text }) {
  return api("/channels/chat/messages", {
    method: "POST",
    body: { session_id: session, message_id: `tela-${uid()}`, brand, customer, text, sent_at: new Date().toISOString() },
  });
}

// O chat do lado do cliente. Fica separado da plataforma: é a ferramenta da demo, não o produto.
export default function SimulatorDrawer({ open, conversationId, onOpenChange, onConversation }) {
  const live = usePolling(open && conversationId ? `/api/cases/${conversationId}` : null);
  const c = live.data?.conversation;
  return (
    <Sheet open={open} onOpenChange={onOpenChange} width="420px"
           title={c ? `Simulador: ${c.customer_name}` : "Simular cliente"}
           description={c ? `Você está vendo o chat como o cliente vê, em ${BRANDS[c.brand_id]}.`
             : "A mensagem entra pelo chat como a de um cliente real e passa por triagem, fila e IA ou equipe."}>
      {conversationId
        ? <CustomerChat data={live.data} onConversation={onConversation}
                        onShow={() => { onOpenChange(false); go("conversas", conversationId); }} />
        : <StartForm onStarted={onConversation} />}
    </Sheet>
  );
}

function StartForm({ onStarted }) {
  const [brand, setBrand] = useState("infinitepay");
  const [customer, setCustomer] = useState(0);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function start(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const result = await sendAsCustomer({ session: `tela-${uid()}`, brand, customer: CUSTOMERS[brand][customer], text });
      toast.success("Conversa iniciada");
      onStarted(result.conversation_id);
    } catch (err) {
      toast.error(`Conversa não iniciada: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form" onSubmit={start}>
      <div className="field">
        <span className="field-label" id="sim-brand">Marca</span>
        <div className="segmented" role="group" aria-labelledby="sim-brand">
          {Object.entries(BRANDS).map(([k, v]) => (
            <button key={k} type="button" aria-pressed={brand === k}
                    onClick={() => { setBrand(k); setCustomer(0); setText(""); }}>{v}</button>
          ))}
        </div>
      </div>
      <label className="field">
        <span className="field-label">Cliente</span>
        <select value={customer} onChange={(e) => setCustomer(Number(e.target.value))}>
          {CUSTOMERS[brand].map((c, i) => <option key={c.external_id} value={i}>{c.name}</option>)}
        </select>
      </label>
      <label className="field">
        <span className="field-label">Mensagem</span>
        <textarea value={text} onChange={(e) => setText(e.target.value)} required maxLength={4000} rows={3}
                  placeholder={brand === "jim" ? "What does the customer say?" : "O que o cliente escreve?"} />
      </label>
      <div className="chips" role="group" aria-label="Exemplos de mensagem">
        {SUGGESTIONS[brand].map((s) => (
          <button key={s} type="button" className="chip" aria-pressed={text === s} onClick={() => setText(s)}>{s}</button>
        ))}
      </div>
      <button type="submit" className="btn btn-primary btn-block" disabled={!text.trim() || busy}>Enviar mensagem</button>
    </form>
  );
}

function CustomerChat({ data, onConversation, onShow }) {
  const end = useRef(null);
  const messages = data?.messages ?? [];
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [messages.length]);
  if (!data) return <div className="skeleton skeleton-tall" aria-busy="true" />;
  const c = data.conversation;

  async function send(text) {
    try {
      const result = await sendAsCustomer({
        session: c.external_session_id, brand: c.brand_id, text,
        customer: { external_id: c.customer_external_id, name: c.customer_name, email: `${c.customer_external_id}@example.com` },
      });
      // Conversa encerrada: a mensagem abre outra, e o simulador passa a mostrar a nova
      if (result.conversation_id !== c.id) {
        toast("Nova conversa aberta para este cliente");
        onConversation(result.conversation_id);
      }
      return true;
    } catch (err) {
      toast.error(`Mensagem não enviada: ${err.message}`);
      return false;
    }
  }

  return (
    <div className="sim">
      <div className="sim-actions">
        <button type="button" className="btn btn-ghost" onClick={onShow}>
          <ExternalLink size={15} aria-hidden="true" /> Ver na plataforma
        </button>
        <button type="button" className="btn btn-ghost" onClick={() => onConversation(null)}>
          <RotateCcw size={15} aria-hidden="true" /> Outro cliente
        </button>
      </div>
      <ol className="sim-chat">
        {messages.map((m) => (
          <li key={m.id} className={m.author === "customer" ? "sim-msg sim-me" : "sim-msg sim-them"}>
            {m.author !== "customer" && <span className="sim-who">{m.author === "analyst" ? "Atendente" : "Assistente"}</span>}
            <p>{m.text}</p>
            <time>{time(m.created_at)}</time>
          </li>
        ))}
        <li ref={end} aria-hidden="true" />
      </ol>
      {c.channel !== "chat"
        ? <p className="note">Só dá para escrever como cliente em conversas de chat.</p>
        : (
          <>
            {c.status === "closed" && <p className="note">Conversa encerrada. A próxima mensagem abre outra.</p>}
            <Composer label={`Escrever como ${c.customer_name}`} placeholder="Escreva como o cliente" onSend={send} tone="customer" />
          </>
        )}
    </div>
  );
}
