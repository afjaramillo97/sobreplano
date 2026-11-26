/**
 * localStorage for what the person saves on this device (SPEC 11d §4). Every function survives
 * a storage that is missing (private mode, blocked) or full: the caller then keeps its state in
 * memory and says so. Nothing here leaves the browser.
 */

/**
 * The browser's localStorage, or null when it cannot be reached. It does not probe with a
 * write: a full storage must still be read, and cleared.
 */
export function localStorageOrNull(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** The value under key, parsed; null without storage, without the key or with broken JSON. */
export function readJson(storage: Storage | null, key: string): unknown {
  try {
    const raw = storage?.getItem(key) ?? null;
    return raw === null ? null : JSON.parse(raw);
  } catch {
    return null;
  }
}

/** Save value under key; false when it could not be stored. */
export function writeJson(storage: Storage | null, key: string, value: unknown): boolean {
  if (storage === null) return false;
  try {
    storage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

/** Remove the key; false when the storage could not be reached. */
export function removeKey(storage: Storage | null, key: string): boolean {
  if (storage === null) return false;
  try {
    storage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}
