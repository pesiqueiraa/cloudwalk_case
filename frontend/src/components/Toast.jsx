import { createContext, useCallback, useContext, useState } from "react";

const ToastContext = createContext(() => {});

export function useToast() {
  return useContext(ToastContext);
}

// Confirma cada ação com o mesmo verbo do botão ("Assumir caso" → "Caso assumido")
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const show = useCallback((text, tone = "ok") => {
    const id = Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "error" ? 6000 : 3000);
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className={`toast toast-${t.tone}`}>{t.text}</div>)}
      </div>
    </ToastContext.Provider>
  );
}
