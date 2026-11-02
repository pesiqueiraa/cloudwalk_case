import { useEffect, useState } from "react";
import Chat from "./screens/Chat.jsx";
import Admin from "./screens/Admin.jsx";
import Analyst from "./screens/Analyst.jsx";

const SCREENS = {
  chat: { label: "Conversas", component: Chat },
  analyst: { label: "Analista", component: Analyst },
  admin: { label: "Filas e regras", component: Admin },
};

function currentScreen() {
  const hash = window.location.hash.replace("#", "");
  return SCREENS[hash] ? hash : "chat";
}

export default function App() {
  const [screen, setScreen] = useState(currentScreen);
  useEffect(() => {
    const onHash = () => setScreen(currentScreen());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const Screen = SCREENS[screen].component;

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Help Desk <small>AI first</small></span>
        <nav>
          {Object.entries(SCREENS).map(([key, { label }]) => (
            <a key={key} href={`#${key}`} className={key === screen ? "active" : ""}>{label}</a>
          ))}
        </nav>
        <span className="muted small">dados sintéticos · atualiza a cada 2 s</span>
      </header>
      <main>
        <Screen />
      </main>
    </div>
  );
}
