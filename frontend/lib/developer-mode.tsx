"use client";

import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";

/**
 * Developer view: off by default, so an accountant sees the product and
 * not the scaffolding. On, it adds what a developer evaluating Aito wants:
 * the "reference implementation" banner, the QUALITY pages, and every
 * `$why` factor unabridged (see `lib/why-display.ts`).
 *
 * Turned on by `?dev=1` in the URL (shareable) or the switch at the foot
 * of the nav; remembered per browser.
 */
interface DeveloperModeContextType {
  developerMode: boolean;
  setDeveloperMode: (on: boolean) => void;
}

const DeveloperModeContext = createContext<DeveloperModeContextType>({
  developerMode: false,
  setDeveloperMode: () => {},
});

const STORAGE_KEY = "predictive-ledger-developer-mode";

function readInitial(): boolean {
  const fromUrl = new URL(window.location.href).searchParams.get("dev");
  if (fromUrl === "1") return true;
  if (fromUrl === "0") return false;
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function DeveloperModeProvider({ children }: { children: ReactNode }) {
  const [developerMode, setState] = useState(false);

  // window is undefined during the static export, so read after mount.
  useEffect(() => { setState(readInitial()); }, []);

  const setDeveloperMode = useCallback((on: boolean) => {
    setState(on);
    try { window.localStorage.setItem(STORAGE_KEY, on ? "1" : "0"); } catch { /* private window */ }
  }, []);

  return (
    <DeveloperModeContext.Provider value={{ developerMode, setDeveloperMode }}>
      {children}
    </DeveloperModeContext.Provider>
  );
}

export function useDeveloperMode() {
  return useContext(DeveloperModeContext);
}
