/**
 * The person's finances as an island holds them (SPEC 11d §4): empty on the server, read from
 * this browser after the first render, and saved on every change the person makes.
 *
 * onLoad fills the island's inputs with what was read. It runs again when the browser brings
 * the page back from its history cache, where another page may have changed the data.
 */
import { useEffect, useState } from "react";

import { localStorageOrNull } from "@/lib/browser-storage";
import {
  clearFinances,
  EMPTY_FINANCES,
  readFinances,
  type StoredFinances,
  writeFinances,
} from "@/lib/finances-store";

export function useFinances(onLoad?: (saved: StoredFinances) => void) {
  const [finances, setFinances] = useState<StoredFinances>(EMPTY_FINANCES);
  // True when the browser does not keep the data: the island says so and works in memory.
  const [memoryOnly, setMemoryOnly] = useState(false);

  useEffect(() => {
    function load(restored: boolean) {
      const storage = localStorageOrNull();
      setMemoryOnly(storage === null);
      // Without storage the memory of this page is all there is: keep it.
      if (storage === null) return;
      const saved = readFinances(storage);
      if (!saved && !restored) return;
      setFinances(saved ?? EMPTY_FINANCES);
      onLoad?.(saved ?? EMPTY_FINANCES);
    }
    const onShow = (event: PageTransitionEvent) => {
      if (event.persisted) load(true);
    };
    load(false);
    window.addEventListener("pageshow", onShow);
    return () => window.removeEventListener("pageshow", onShow);
    // Once, on mount: onLoad only sets state, so the first one serves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Only changes are saved, so a visit without them leaves nothing behind. */
  function update(patch: Partial<StoredFinances>) {
    const next = { ...finances, ...patch };
    setFinances(next);
    setMemoryOnly(!writeFinances(localStorageOrNull(), next));
  }

  function forget() {
    clearFinances(localStorageOrNull());
    setFinances(EMPTY_FINANCES);
  }

  return { finances, memoryOnly, update, forget };
}
