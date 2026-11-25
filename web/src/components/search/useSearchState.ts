/**
 * The search state of the island, kept in the URL (SPEC 11b §2).
 *
 * - Filters and order replace the history entry, so "Atrás" leaves the search in one step.
 * - Continuous changes (typing, sliders, the map) write after 250 ms: Safari throws after 100
 *   history writes in 30 s. A pending write is flushed before any link is followed, so coming
 *   back to the listing brings the search back.
 * - Only the map view on narrow screens pushes an entry, so "Atrás" goes back to the list.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { DEFAULT_SEARCH, parseSearch, type SearchState, serializeSearch } from "@/lib/search";

/** How a change reaches the history. */
export type HistoryWrite = "replace" | "replace-later" | "push";

const LATER_MS = 250;

function urlOf(state: SearchState): string {
  const query = serializeSearch(state);
  return `${window.location.pathname}${query ? `?${query}` : ""}`;
}

export function useSearchState(developers: readonly string[]) {
  // The first render matches the server HTML (no filters); the URL is read after hydration.
  const [state, setState] = useState<SearchState>(DEFAULT_SEARCH);
  const [ready, setReady] = useState(false);
  // Whether the reader has changed something, so the count is announced only from then on.
  const [changed, setChanged] = useState(false);
  const current = useRef(state);
  const pending = useRef<number | undefined>(undefined);

  /** Replaces the history entry with the current search, unless the URL already holds it. */
  const replaceNow = useCallback(() => {
    const url = urlOf(current.current);
    if (url !== `${window.location.pathname}${window.location.search}`) {
      window.history.replaceState(window.history.state, "", url);
    }
  }, []);

  /** Writes a waiting change now. */
  const flush = useCallback(() => {
    if (pending.current === undefined) return;
    window.clearTimeout(pending.current);
    pending.current = undefined;
    replaceNow();
  }, [replaceNow]);

  const update = useCallback(
    (change: (state: SearchState) => SearchState, write: HistoryWrite = "replace") => {
      const next = change(current.current);
      current.current = next;
      setState(next);
      setChanged(true);
      window.clearTimeout(pending.current);
      pending.current = undefined;
      if (write === "replace-later") {
        pending.current = window.setTimeout(() => {
          pending.current = undefined;
          replaceNow();
        }, LATER_MS);
      } else if (write === "push") {
        const url = urlOf(next);
        if (url !== `${window.location.pathname}${window.location.search}`) {
          window.history.pushState(null, "", url);
        }
      } else {
        replaceNow();
      }
    },
    [replaceNow],
  );

  useEffect(() => {
    const read = () => {
      window.clearTimeout(pending.current);
      pending.current = undefined;
      const next = parseSearch(new URLSearchParams(window.location.search), { developers });
      current.current = next;
      setState(next);
    };
    read();
    setReady(true);
    // Before a link is followed (capture phase), the URL must already hold the search.
    const beforeLeaving = (event: MouseEvent) => {
      if (event.target instanceof Element && event.target.closest("a[href]")) flush();
    };
    window.addEventListener("popstate", read);
    document.addEventListener("click", beforeLeaving, true);
    window.addEventListener("pagehide", flush);
    return () => {
      window.removeEventListener("popstate", read);
      document.removeEventListener("click", beforeLeaving, true);
      window.removeEventListener("pagehide", flush);
    };
  }, [developers, flush]);

  return { state, update, ready, changed };
}
