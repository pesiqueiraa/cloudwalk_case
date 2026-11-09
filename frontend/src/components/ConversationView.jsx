import { useState } from "react";
import { readPref, savePref, useApp, useMedia } from "../hooks.js";
import CaseHeader from "./CaseHeader.jsx";
import ContextPanel from "./ContextPanel.jsx";
import Sheet from "./Sheet.jsx";
import Thread from "./Thread.jsx";
import TraceDrawer from "./TraceDrawer.jsx";

// Conversa no centro; contexto ao lado (ou em gaveta, em telas estreitas); auditoria sob demanda
export default function ConversationView({ data, onBack, actions, footer }) {
  const { teamName } = useApp();
  const wide = useMedia("(min-width: 1200px)");
  const [contextPref, setContextPref] = useState(() => readPref("contextOpen", "1") === "1");
  const [narrowContext, setNarrowContext] = useState(false);
  const [trace, setTrace] = useState(false);
  const c = data.conversation;
  const contextOpen = wide ? contextPref : narrowContext;

  function toggleContext() {
    if (wide) { savePref("contextOpen", contextPref ? "0" : "1"); setContextPref(!contextPref); }
    else setNarrowContext(!narrowContext);
  }

  return (
    <div className={wide && contextPref ? "conv conv-with-context" : "conv"}>
      <section className="pane pane-conv" aria-label={`Conversa com ${c.customer_name}`}>
        <CaseHeader conversation={c} onBack={onBack} onTrace={() => setTrace(true)}
                    onToggleContext={toggleContext} contextOpen={contextOpen}>
          {actions}
        </CaseHeader>
        <div className="thread-scroll">
          <Thread messages={data.messages} audit={data.audit} customerName={c.customer_name}
                  analystName={c.assigned_analyst_name} />
        </div>
        {footer && <div className="conv-foot">{footer}</div>}
      </section>
      {wide && contextPref && (
        <aside className="pane pane-ctx" aria-label="Contexto do atendimento">
          <ContextPanel data={data} teamName={teamName} />
        </aside>
      )}
      {!wide && (
        <Sheet open={narrowContext} onOpenChange={setNarrowContext} title="Contexto do atendimento" width="380px">
          <ContextPanel data={data} teamName={teamName} />
        </Sheet>
      )}
      <TraceDrawer open={trace} onOpenChange={setTrace} events={data.audit} />
    </div>
  );
}
