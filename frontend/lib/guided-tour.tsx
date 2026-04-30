"use client";

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from "react";

export interface GuidedTourStop {
  /** 1-based for display. */
  n: number;
  href: string;
  title: string;
  /** Why this stop matters for an evaluator. Plain prose, 1–2 sentences. */
  pitch: string;
  /** What to actually do on the page. */
  action: string;
  /** Aito call that powers the stop, for the tooltip. */
  call: string;
}

export const TOUR_STOPS: GuidedTourStop[] = [
  {
    n: 1,
    href: "/",
    title: "Same vendor, four tenants, four GLs",
    pitch:
      "One Aito instance serves 255 tenants. The query carries customer_id; each tenant's history conditions independently. No per-tenant model file.",
    action: "Pick another shared vendor in the chip row — watch every card retone.",
    call: "_predict gl_code WHERE customer_id, vendor",
  },
  {
    n: 2,
    href: "/formfill",
    title: "Smart Form Fill — multi-field _predict",
    pitch:
      "Type any vendor; GL, approver, cost centre and VAT all predict in one server round-trip. The whole template is the joint mode of historical invoices for that vendor — not a chain of predict calls.",
    action: "Pick a vendor from the recent list (or type a new one). Each predicted field carries $why.",
    call: "_search joint mode + per-field _predict",
  },
  {
    n: 3,
    href: "/matching",
    title: "Payment Matching via link traversal",
    pitch:
      "Bank transaction → invoice via a single _predict on the link field. Most teams build payment matching with rule scripts; here it's one query over the schema's foreign-key relationship.",
    action: "Pick a bank transaction — see the predicted invoice_id with confidence and $why.",
    call: "_predict invoice_id WHERE bank_txn fields",
  },
  {
    n: 4,
    href: "/quality/predictions",
    title: "Per-tenant _evaluate — honest accuracy",
    pitch:
      "Real accuracy from held-out test splits, per tenant. Not cherry-picked — including the small ones where confidence is low and the demo says so.",
    action: "Switch tenants in the topbar — accuracy numbers reflow immediately.",
    call: "_evaluate WHERE customer_id (cases mode)",
  },
];

const STORAGE_KEY = "predictive-ledger-guided-tour";

interface GuidedTourContextType {
  active: boolean;
  step: number;
  start: () => void;
  next: () => void;
  prev: () => void;
  end: () => void;
  goTo: (i: number) => void;
}

const GuidedTourContext = createContext<GuidedTourContextType>({
  active: false,
  step: 0,
  start: () => {},
  next: () => {},
  prev: () => {},
  end: () => {},
  goTo: () => {},
});

export function GuidedTourProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState(false);
  const [step, setStep] = useState(0);

  // Persist active state across navigations (the static export does
  // hard reloads on first visit, so context alone is not enough).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        if (parsed?.active && typeof parsed.step === "number") {
          setActive(true);
          setStep(Math.max(0, Math.min(TOUR_STOPS.length - 1, parsed.step)));
        }
      } catch { /* corrupted state — ignore and start fresh */ }
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (active) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ active, step }));
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, [active, step]);

  const navigate = useCallback((href: string) => {
    if (typeof window === "undefined") return;
    if (window.location.pathname.replace(/\/$/, "") !== href.replace(/\/$/, "")) {
      window.location.assign(href);
    }
  }, []);

  const start = useCallback(() => {
    setActive(true);
    setStep(0);
    navigate(TOUR_STOPS[0].href);
  }, [navigate]);

  const next = useCallback(() => {
    setStep((s) => {
      const ns = Math.min(TOUR_STOPS.length - 1, s + 1);
      navigate(TOUR_STOPS[ns].href);
      return ns;
    });
  }, [navigate]);

  const prev = useCallback(() => {
    setStep((s) => {
      const ns = Math.max(0, s - 1);
      navigate(TOUR_STOPS[ns].href);
      return ns;
    });
  }, [navigate]);

  const end = useCallback(() => {
    setActive(false);
    setStep(0);
  }, []);

  const goTo = useCallback(
    (i: number) => {
      const ns = Math.max(0, Math.min(TOUR_STOPS.length - 1, i));
      setStep(ns);
      navigate(TOUR_STOPS[ns].href);
    },
    [navigate],
  );

  return (
    <GuidedTourContext.Provider value={{ active, step, start, next, prev, end, goTo }}>
      {children}
    </GuidedTourContext.Provider>
  );
}

export function useGuidedTour() {
  return useContext(GuidedTourContext);
}
