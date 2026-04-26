"use client";

import { useTour } from "@/lib/tour-context";

interface TourBadgeProps {
  /** Step number that matches an entry in AitoPanelConfig.flow_steps */
  n: number;
}

/**
 * Small numbered chip rendered next to a UI element. Visible only when
 * the data-flow tour is on. The number ties the element to a step in
 * the AitoPanel's "Data flow on this page" section.
 */
export default function TourBadge({ n }: TourBadgeProps) {
  const { tourOn } = useTour();
  if (!tourOn) return null;
  return <span className="tour-badge" title={`Step ${n} — see right panel`}>{n}</span>;
}
