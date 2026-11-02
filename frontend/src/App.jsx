import { useEffect, useState } from "react";
import Inbox from "./screens/Inbox.jsx";
import Analyst from "./screens/Analyst.jsx";
import Admin from "./screens/Admin.jsx";
import { usePolling } from "./usePolling.js";
import { query } from "./api.js";
import { ToastProvider } from "./components/Toast.jsx";

const SCREENS = {
  inbox: { label: "Atendimentos", Component: Inbox },
  queue: { label: "Fila da minha equipe", Component: Analyst },
  admin: { label: "Filas e regras", Component: Admin },
};

function screenFromHash() {
  const hash = window.location.hash.replace("#", "");
  return SCREENS[hash] ? hash : "inbox";
}

// Preferência só deste navegador; a tela funciona sem ela
function readAnalyst() {
  try { return localStorage.getItem("helpdesk.analystId") ?? ""; } catch { return ""; }
}
function saveAnalyst(id) {
  try { localStorage.setItem("helpdesk.analystId", id); } catch { /* sem armazenamento: tudo bem */ }
}

export default function App() {
  const [screen, setScreen] = useState(screenFromHash);
  const [analystId, setAnalystId] = useState(readAnalyst);
  const analysts = usePolling("/api/admin/analysts", 60000);
  const teams = usePolling("/api/admin/teams", 60000);
  const analyst = (analysts.data ?? []).find((a) => a.id === analystId) ?? null;
  const teamName = Object.fromEntries((teams.data ?? []).map((t) => [t.id, t.name]));
  const waiting = usePolling(analyst ? "/api/escalations" + query({ team_id: analyst.team_id }) : null, 4000);
  const waitingCount = (waiting.data ?? []).filter((c) => !c.assigned_analyst_id).length;

  useEffect(() => {
    const onHash = () => setScreen(screenFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const { Component } = SCREENS[screen];
  const teamsWithAnalysts = (teams.data ?? []).map((t) => ({
    ...t, analysts: (analysts.data ?? []).filter((a) => a.team_id === t.id),
  }));

  return (
    <ToastProvider>
      <div className="shell">
        <aside className="sidebar">
          <div className="wordmark">
            Help Desk
            <span>InfinitePay e JIM</span>
          </div>
          <nav aria-label="Áreas">
            {Object.entries(SCREENS).map(([key, { label }]) => (
              <a key={key} href={`#${key}`} aria-current={key === screen ? "page" : undefined}>
                {label}
                {key === "queue" && analyst && waitingCount > 0 && (
                  <span className="count" title="casos esperando alguém assumir">{waitingCount}</span>
                )}
              </a>
            ))}
          </nav>
          <div className="me">
            <label htmlFor="me">Você é</label>
            <select id="me" value={analystId}
                    onChange={(e) => { setAnalystId(e.target.value); saveAnalyst(e.target.value); }}>
              <option value="">Escolha um analista</option>
              {teamsWithAnalysts.map((t) => (
                <optgroup key={t.id} label={t.name}>
                  {t.analysts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </optgroup>
              ))}
            </select>
            {analyst && <p>Equipe {teamName[analyst.team_id] ?? analyst.team_id}</p>}
          </div>
          <p className="sidebar-note">Clientes e casos são sintéticos. As telas se atualizam sozinhas.</p>
        </aside>
        <main className="content">
          <Component analyst={analyst} teamName={teamName} />
        </main>
      </div>
    </ToastProvider>
  );
}
