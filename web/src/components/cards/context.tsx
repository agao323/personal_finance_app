"use client";

/**
 * The cards the layout already loaded, shared with whatever page is on the right.
 *
 * The list and the detail need the same data, and the layout is the one that survives
 * navigation between cards. Passing it down through context means clicking a card does not
 * refetch the wallet, and `reload` gives any panel one way to say "something changed" —
 * the single refresh signal ticket 061 established.
 */

import { createContext, useContext } from "react";

import type { Cards } from "./types";

export interface CardsState {
  cards: Cards | null;
  pending: boolean;
  error: string | null;
  reload: () => void;
  /** Bumped by `reload`. Panels that fetch their own data key off it. */
  revision: number;
}

export const CardsContext = createContext<CardsState>({
  cards: null,
  pending: true,
  error: null,
  reload: () => {},
  revision: 0,
});

export function useCards(): CardsState {
  return useContext(CardsContext);
}
