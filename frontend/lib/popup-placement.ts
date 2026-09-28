/**
 * Where to put a popup anchored to a button, so that it stays on screen.
 *
 * The why-popup used to open ABOVE its button unconditionally. Its cards run
 * to several hundred pixels, so on any invoice row in the upper half of the
 * screen the top of the explanation was cut off by the viewport edge.
 *
 * Order of preference: above if it fits, below if it fits, otherwise the
 * roomier side with the height capped so the popup scrolls inside itself.
 */

export interface AnchorRect { top: number; bottom: number; left: number; width: number; }
export interface Size { width: number; height: number; }

export interface Placement {
  placement: "above" | "below";
  /** Viewport y of the popup's top edge. */
  top: number;
  /** Viewport x of the popup's left edge. */
  left: number;
  /** Set only when the popup must scroll to fit. */
  maxHeight?: number;
  /** Arrow x within the popup, so it points at the button even when the
   *  popup is shifted to stay on screen. */
  arrowX: number;
}

const MARGIN = 12;
const GAP = 8;

export function placePopup(anchor: AnchorRect, popup: Size, viewport: Size): Placement {
  const spaceAbove = anchor.top - GAP - MARGIN;
  const spaceBelow = viewport.height - anchor.bottom - GAP - MARGIN;

  const centred = anchor.left + anchor.width / 2 - popup.width / 2;
  const left = Math.max(MARGIN, Math.min(viewport.width - popup.width - MARGIN, centred));
  const ARROW_INSET = 16;
  const arrowX = Math.max(ARROW_INSET, Math.min(popup.width - ARROW_INSET,
                                                anchor.left + anchor.width / 2 - left));

  if (popup.height <= spaceAbove) {
    return { placement: "above", top: anchor.top - GAP - popup.height, left, arrowX };
  }
  if (popup.height <= spaceBelow) {
    return { placement: "below", top: anchor.bottom + GAP, left, arrowX };
  }
  if (spaceAbove >= spaceBelow) {
    return { placement: "above", top: MARGIN, left, maxHeight: spaceAbove, arrowX };
  }
  return { placement: "below", top: anchor.bottom + GAP, left, maxHeight: spaceBelow, arrowX };
}
