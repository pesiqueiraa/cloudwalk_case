import { useMemo, useState } from "react";
import { Toaster } from "sonner";
import * as Tooltip from "@radix-ui/react-tooltip";
import { MessageSquarePlus } from "lucide-react";
import Analyst from "./screens/Analyst.jsx";
import Inbox from "./screens/Inbox.jsx";
import Admin from "./screens/Admin.jsx";
import AnalystMenu from "./components/AnalystMenu.jsx";
import SimulatorDrawer from "./components/SimulatorDrawer.jsx";
import { AppContext, readPref, savePref, useHashRoute } from "./hooks.js";
import { usePolling } from "./usePolling.js";
import { query } from "./api.js";

const NAV = [
  { key: "atendimento", label: "Atendimento", Component: Analyst },
  { key: "conversas", label: "Conversas", Component: Inbox },
  { key: "configuracao", label: "Configuração", Component: Admin },
];

export default function App() {
  const route = useHashRoute();
  const [analystId, setAnalystId] = useState(() => readPref("analystId", ""));
  const [simulator, setSimulator] = useState({ open: false, conversationId: null });
  const analysts = usePolling("/api/admin/analysts", 60000);
  const teams = usePolling("/api/admin/teams", 60000);

  const analyst = (analysts.data ?? []).find((a) => a.id === analystId) ?? null;
  const waiting = usePolling(analyst ? "/api/escalations" + query({ team_id: analyst.team_id }) : null, 4000);
  const waitingCount = (waiting.data ?? []).filter((c) => !c.assigned_analyst_id).length;

  const ctx = useMemo(() => {
    const teamList = teams.data ?? [];
    return {
      analyst,
      teams: teamList,
      teamName: Object.fromEntries(teamList.map((t) => [t.id, t.name])),
      teamsWithAnalysts: teamList.map((t) => ({ ...t, analysts: (analysts.data ?? []).filter((a) => a.team_id === t.id) })),
      chooseAnalyst: (id) => { setAnalystId(id); savePref("analystId", id); },
      openSimulator: (conversationId = null) => setSimulator({ open: true, conversationId }),
    };
  }, [analyst, teams.data, analysts.data]);

  const { Component } = NAV.find((n) => n.key === route.screen);

  return (
    <AppContext.Provider value={ctx}>
      <Tooltip.Provider delayDuration={300}>
        <div className="app">
          <header className="topbar">
            <a className="wordmark" href="#atendimento">
              <span className="wordmark-dot" aria-hidden="true" />
              Help Desk
            </a>
            <nav className="nav" aria-label="Áreas">
              {NAV.map((n) => (
                <a key={n.key} href={`#${n.key}`} aria-current={n.key === route.screen ? "page" : undefined}>
                  {n.label}
                  {n.key === "atendimento" && waitingCount > 0 && (
                    <span className="badge" aria-label={`${waitingCount} esperando`}>{waitingCount}</span>
                  )}
                </a>
              ))}
            </nav>
            <div className="topbar-end">
              <button type="button" className="btn btn-ghost" onClick={() => ctx.openSimulator()}>
                <MessageSquarePlus size={16} aria-hidden="true" />
                <span className="hide-sm">Simular cliente</span>
              </button>
              <AnalystMenu />
            </div>
          </header>
          <main className="main">
            <Component routeId={route.id} />
          </main>
        </div>
        <SimulatorDrawer {...simulator} onOpenChange={(open) => setSimulator((s) => ({ ...s, open }))}
                         onConversation={(conversationId) => setSimulator((s) => ({ ...s, conversationId }))} />
        <Toaster position="top-right" offset={68} mobileOffset={64} theme="system" />
      </Tooltip.Provider>
    </AppContext.Provider>
  );
}
