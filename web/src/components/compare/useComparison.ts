/**
 * The selection to compare as an island holds it (SPEC 11d §4): read from this browser after
 * the first render, and again when the page comes back from the history cache, since another
 * page may have changed it.
 */
import { useEffect, useState } from "react";

import { localStorageOrNull } from "@/lib/browser-storage";
import { clearComparison, readComparison, writeComparison } from "@/lib/compare-store";

export function useComparison() {
  const [slugs, setSlugs] = useState<string[]>([]);
  const [ready, setReady] = useState(false);
  // True when the browser does not keep the selection: it lives as long as the page.
  const [memoryOnly, setMemoryOnly] = useState(false);

  useEffect(() => {
    function load() {
      const storage = localStorageOrNull();
      setMemoryOnly(storage === null);
      if (storage !== null) setSlugs(readComparison(storage));
      setReady(true);
    }
    const onShow = (event: PageTransitionEvent) => {
      if (event.persisted) load();
    };
    load();
    window.addEventListener("pageshow", onShow);
    return () => window.removeEventListener("pageshow", onShow);
  }, []);

  function save(next: string[]) {
    setSlugs(next);
    setMemoryOnly(!writeComparison(localStorageOrNull(), next));
  }

  function clear() {
    setSlugs([]);
    clearComparison(localStorageOrNull());
  }

  return { slugs, ready, memoryOnly, save, clear };
}
