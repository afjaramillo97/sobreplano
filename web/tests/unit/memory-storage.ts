/** An in-memory Storage; `full` makes every write throw, as a browser over its quota does. */
export class MemoryStorage implements Storage {
  data = new Map<string, string>();
  full = false;
  get length() {
    return this.data.size;
  }
  clear() {
    this.data.clear();
  }
  getItem(key: string) {
    return this.data.get(key) ?? null;
  }
  key(index: number) {
    return [...this.data.keys()][index] ?? null;
  }
  removeItem(key: string) {
    this.data.delete(key);
  }
  setItem(key: string, value: string) {
    if (this.full) throw new DOMException("quota", "QuotaExceededError");
    this.data.set(key, value);
  }
}
