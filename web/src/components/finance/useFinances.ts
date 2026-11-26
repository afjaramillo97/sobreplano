/**
 * The person's finances as an island holds them (SPEC 11d §4): empty on the server, read from
 * this browser after the first render, and saved on every change the person makes.
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
    const storage = localStorageOrNull();
    setMemoryOnly(storage === null);
    const saved = readFinances(storage);
    if (saved) {
      setFinances(saved);
      onLoad?.(saved);
    }
    // Once, on mount: later changes come from this island itself.
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
