import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";

// Busca agora e a cada `ms` (padrão 2 s). path nulo = não busca.
export function usePolling(path, ms = 2000) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const pathRef = useRef(path);
  pathRef.current = path;

  const load = useCallback(async () => {
    const current = pathRef.current;
    if (!current) return;
    try {
      const result = await api(current);
      if (pathRef.current === current) {
        setData(result);
        setError(null);
      }
    } catch (e) {
      if (pathRef.current === current) setError(e.message);
    }
  }, []);

  useEffect(() => {
    setData(null);
    if (!path) return undefined;
    load();
    const id = setInterval(load, ms);
    return () => clearInterval(id);
  }, [path, ms, load]);

  return { data, error, reload: load };
}
