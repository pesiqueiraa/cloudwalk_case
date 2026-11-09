import { createContext, useContext, useEffect, useState } from "react";

// Rota por hash: "#atendimento/<id da conversa>". Sem roteador.
export const SCREENS = ["atendimento", "conversas", "configuracao"];

function parseHash() {
  const [screen, id] = window.location.hash.replace(/^#\/?/, "").split("/");
  return { screen: SCREENS.includes(screen) ? screen : "atendimento", id: id || null };
}

export function useHashRoute() {
  const [route, setRoute] = useState(parseHash);
  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return route;
}

export function go(screen, id) {
  window.location.hash = id ? `${screen}/${id}` : screen;
}

export function useMedia(queryText) {
  const [matches, setMatches] = useState(() => window.matchMedia(queryText).matches);
  useEffect(() => {
    const list = window.matchMedia(queryText);
    const onChange = () => setMatches(list.matches);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [queryText]);
  return matches;
}

// Preferências só deste navegador; a tela funciona sem elas
export function readPref(key, fallback) {
  try { return localStorage.getItem(`helpdesk.${key}`) ?? fallback; } catch { return fallback; }
}
export function savePref(key, value) {
  try { localStorage.setItem(`helpdesk.${key}`, value); } catch { /* sem armazenamento: tudo bem */ }
}

// Quem está usando a tela e como abrir o simulador, disponíveis em qualquer tela
export const AppContext = createContext(null);
export const useApp = () => useContext(AppContext);
