"use client";

import { createContext, useContext, useState, ReactNode } from "react";

/**
 * "Data flow tour" mode: when on, each page renders small numbered
 * badges next to UI elements that came from a specific Aito call, and
 * the AitoPanel highlights those calls. Builds evaluator trust by
 * making every claim traceable to a query.
 */
interface TourContextType {
  tourOn: boolean;
  setTourOn: (v: boolean) => void;
}

const TourContext = createContext<TourContextType>({
  tourOn: false,
  setTourOn: () => {},
});

export function TourProvider({ children }: { children: ReactNode }) {
  const [tourOn, setTourOn] = useState(false);
  return (
    <TourContext.Provider value={{ tourOn, setTourOn }}>
      {children}
    </TourContext.Provider>
  );
}

export function useTour() {
  return useContext(TourContext);
}
