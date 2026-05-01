"use client";

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from "react";
import { useRouter } from "next/navigation";

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
// Drop tour-resume state after this long. A visitor who abandons
// the tour and returns days later should land on the home page,
// not be ambushed by step 3 of a flow they barely remember starting.
const STORAGE_TTL_MS = 6 * 60 * 60 * 1000;  // 6 hours

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
  const router = useRouter();
  const [active, setActive] = useState(false);
  const [step, setStep] = useState(0);

  // Resume an in-progress tour, but only if the saved state is fresh.
  // Stale state (visitor closed the tab days ago) is discarded.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) return;
    try {
      const parsed = JSON.parse(stored);
      const fresh = typeof parsed?.savedAt === "number" && Date.now() - parsed.savedAt < STORAGE_TTL_MS;
      if (parsed?.active && typeof parsed.step === "number" && fresh) {
        setActive(true);
        setStep(Math.max(0, Math.min(TOUR_STOPS.length - 1, parsed.step)));
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (active) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ active, step, savedAt: Date.now() }));
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, [active, step]);

  const navigate = useCallback((href: string) => {
    if (typeof window === "undefined") return;
    if (window.location.pathname.replace(/\/$/, "") !== href.replace(/\/$/, "")) {
      // Soft client-side navigation — no full page reload, no flash.
      // The provider lives at the layout level so context state
      // (active, step) survives the route change.
      router.push(href);
    }
  }, [router]);

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
