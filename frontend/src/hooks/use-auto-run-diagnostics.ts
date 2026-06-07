import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "autopilot:autoRunDiagnostics";

export function useAutoRunDiagnostics() {
  const [enabled, setEnabledState] = useState(false);

  useEffect(() => {
    try {
      setEnabledState(localStorage.getItem(STORAGE_KEY) === "1");
    } catch {
      setEnabledState(false);
    }
  }, []);

  const setEnabled = useCallback((value: boolean) => {
    setEnabledState(value);
    try {
      localStorage.setItem(STORAGE_KEY, value ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, []);

  return [enabled, setEnabled] as const;
}
