import { describe, expect, it } from "vitest";

import {
  appendMessage,
  clearStore,
  closeConversation,
  EMPTY_STORE,
  MAX_CONVERSATIONS,
  newConversation,
  readStore,
  setKeepHistory,
  STORAGE_KEY,
  titleFrom,
  upsertConversation,
  writeStore,
  type AdvisorStore,
  type StoredConversation,
  type StoredMessage,
} from "../../src/lib/advisor/store";

const NOW = new Date("2026-11-25T15:00:00Z");
const DAY_MS = 24 * 60 * 60 * 1000;

/** An in-memory Storage; `full` makes every write throw, as a browser over its quota does. */
class MemoryStorage implements Storage {
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

function daysAgo(days: number): string {
  return new Date(NOW.getTime() - days * DAY_MS).toISOString();
}

function user(text: string, at: string): StoredMessage {
  return { role: "user", text, at };
}

function advisor(text: string, at: string): StoredMessage {
  return { role: "advisor", text, tools: ["search_projects"], projects: [], at };
}

function conversation(id: string, updatedAt: string): StoredConversation {
  const messages = [user(`Pregunta ${id}`, updatedAt), advisor("Respuesta", updatedAt)];
  return newConversation(id, messages, null);
}

function storeWith(...conversations: StoredConversation[]): AdvisorStore {
  return { keepHistory: false, conversations };
}

describe("readStore and writeStore", () => {
  it("round-trips the conversations", () => {
    const storage = new MemoryStorage();
    const store = storeWith(conversation("a", daysAgo(1)));
    expect(writeStore(storage, store)).toBe(true);
    expect(readStore(storage, NOW)).toEqual(store);
  });

  it("starts empty without the key, with broken JSON or with another shape", () => {
    const storage = new MemoryStorage();
    expect(readStore(storage, NOW)).toEqual(EMPTY_STORE);
    storage.data.set(STORAGE_KEY, "{broken");
    expect(readStore(storage, NOW)).toEqual(EMPTY_STORE);
    storage.data.set(STORAGE_KEY, JSON.stringify(["a"]));
    expect(readStore(storage, NOW)).toEqual(EMPTY_STORE);
  });

  it("drops conversations that are not well formed and keeps the rest", () => {
    const storage = new MemoryStorage();
    const good = conversation("a", daysAgo(1));
    storage.data.set(
      STORAGE_KEY,
      JSON.stringify({
        keepHistory: false,
        conversations: [good, { id: "b" }, { ...good, id: "c", messages: [{ role: "x" }] }],
      }),
    );
    expect(readStore(storage, NOW).conversations).toEqual([good]);
  });

  it("works without storage: nothing to read, and a write says it failed", () => {
    expect(readStore(null, NOW)).toEqual(EMPTY_STORE);
    expect(writeStore(null, storeWith(conversation("a", daysAgo(0))))).toBe(false);
    expect(clearStore(null)).toBe(false);
  });

  it("says when storage is full, so the page can stay in memory", () => {
    const storage = new MemoryStorage();
    storage.full = true;
    expect(writeStore(storage, storeWith(conversation("a", daysAgo(0))))).toBe(false);
    expect(storage.data.size).toBe(0);
  });

  it("clears the key", () => {
    const storage = new MemoryStorage();
    writeStore(storage, storeWith(conversation("a", daysAgo(0))));
    expect(clearStore(storage)).toBe(true);
    expect(readStore(storage, NOW)).toEqual(EMPTY_STORE);
  });
});

describe("the 7-day deletion", () => {
  const storage = new MemoryStorage();
  const recent = conversation("recent", daysAgo(6.9));
  const old = conversation("old", daysAgo(7.1));

  it("deletes a conversation inactive for more than 7 days when the day changes", () => {
    writeStore(storage, storeWith(recent, old));
    expect(readStore(storage, NOW).conversations.map((c) => c.id)).toEqual(["recent"]);
    // A day later the recent one is old too.
    const tomorrow = new Date(NOW.getTime() + DAY_MS);
    expect(readStore(storage, tomorrow).conversations).toEqual([]);
  });

  it("keeps them all when the person keeps their history", () => {
    writeStore(storage, setKeepHistory(storeWith(recent, old), true));
    const read = readStore(storage, new Date(NOW.getTime() + 30 * DAY_MS));
    expect(read.keepHistory).toBe(true);
    expect(read.conversations.map((c) => c.id)).toEqual(["recent", "old"]);
  });
});

describe("the conversations", () => {
  it("puts an updated conversation first", () => {
    const a = conversation("a", daysAgo(2));
    const b = conversation("b", daysAgo(1));
    const later = appendMessage(a, user("¿Y ahora?", daysAgo(0)));
    const { store } = upsertConversation(storeWith(b, a), later);
    expect(store.conversations.map((c) => c.id)).toEqual(["a", "b"]);
    expect(store.conversations[0]?.updatedAt).toBe(daysAgo(0));
    expect(store.conversations[0]?.messages).toHaveLength(3);
  });

  it("keeps at most 30 and hands back the oldest it dropped", () => {
    const thirty = Array.from({ length: MAX_CONVERSATIONS }, (_, i) =>
      conversation(`c${i}`, daysAgo(i / 10)),
    );
    const newest = conversation("new", daysAgo(0));
    const { store, dropped } = upsertConversation(storeWith(...thirty), newest);
    expect(store.conversations).toHaveLength(MAX_CONVERSATIONS);
    expect(store.conversations[0]?.id).toBe("new");
    expect(dropped?.id).toBe(`c${MAX_CONVERSATIONS - 1}`);
    expect(upsertConversation(storeWith(), conversation("x", daysAgo(0))).dropped).toBeNull();
  });

  it("closes a conversation the server no longer takes", () => {
    const store = closeConversation(storeWith(conversation("a", daysAgo(0))), "a");
    expect(store.conversations[0]?.closed).toBe(true);
  });

  it("titles a conversation with its first question, one line and at most 60 characters", () => {
    expect(titleFrom("  ¿Qué hay\nen Sabaneta?  ")).toBe("¿Qué hay en Sabaneta?");
    const long = titleFrom("a".repeat(80));
    expect(long).toHaveLength(60);
    expect(long.endsWith("…")).toBe(true);
    const fromProject = newConversation("a", [user("Hola", daysAgo(0))], "arrayanes");
    expect(fromProject.projectSlug).toBe("arrayanes");
  });
});
