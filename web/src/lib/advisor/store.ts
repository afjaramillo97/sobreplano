/**
 * The advisor's conversations in the browser (SPEC 11c §4): one versioned localStorage key,
 * deleted after 7 days without activity unless the person keeps them, at most 30.
 *
 * The functions on AdvisorStore are pure and never mutate; readStore and writeStore are the
 * only ones that touch storage, and both survive a storage that is missing or full (private
 * mode, quota): the page then keeps the current conversation in memory and says so. Nothing
 * here leaves the browser.
 */

export const STORAGE_KEY = "sobreplano.asesor.v1";
export const INACTIVE_DAYS = 7;
export const MAX_CONVERSATIONS = 30;
export const TITLE_LENGTH = 60;

const DAY_MS = 24 * 60 * 60 * 1000;

export type StoredMessage =
  | { role: "user"; text: string; at: string }
  | { role: "advisor"; text: string; tools: string[]; projects: string[]; at: string };

export type StoredConversation = {
  /** The server's thread_id. */
  id: string;
  /** The first question, at most TITLE_LENGTH characters. */
  title: string;
  /** The project in context, when the page was opened from its page. */
  projectSlug: string | null;
  messages: StoredMessage[];
  /** ISO instant of the last activity, for the order and the 7-day deletion. */
  updatedAt: string;
  /** True once the server no longer takes messages in it (404, or 20 messages). */
  closed: boolean;
};

export type AdvisorStore = {
  /** False by default: conversations go after INACTIVE_DAYS without activity. */
  keepHistory: boolean;
  /** Most recent first, at most MAX_CONVERSATIONS. */
  conversations: StoredConversation[];
};

export const EMPTY_STORE: AdvisorStore = { keepHistory: false, conversations: [] };

/** The browser's localStorage if it can be written to, else null (private mode, blocked). */
export function browserStorage(): Storage | null {
  try {
    const storage = window.localStorage;
    const probe = `${STORAGE_KEY}.probe`;
    storage.setItem(probe, "1");
    storage.removeItem(probe);
    return storage;
  } catch {
    return null;
  }
}

/**
 * The stored conversations, without the ones inactive for more than INACTIVE_DAYS when
 * keepHistory is off. Unreadable data counts as empty: a broken key must not break the page.
 */
export function readStore(storage: Storage | null, now: Date): AdvisorStore {
  let raw: string | null = null;
  try {
    raw = storage?.getItem(STORAGE_KEY) ?? null;
  } catch {
    return EMPTY_STORE;
  }
  if (raw === null) return EMPTY_STORE;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return EMPTY_STORE;
  }
  if (!isRecord(data) || !Array.isArray(data.conversations)) return EMPTY_STORE;
  const store: AdvisorStore = {
    keepHistory: data.keepHistory === true,
    conversations: data.conversations
      .filter(isConversation)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, MAX_CONVERSATIONS),
  };
  return pruneInactive(store, now);
}

/** Save the store; false when storage is missing or full, so the page can say so. */
export function writeStore(storage: Storage | null, store: AdvisorStore): boolean {
  if (storage === null) return false;
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(store));
    return true;
  } catch {
    return false;
  }
}

/** Remove the key ("Borrar mis conversaciones"); false when storage could not be reached. */
export function clearStore(storage: Storage | null): boolean {
  if (storage === null) return false;
  try {
    storage.removeItem(STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}

/** The store without conversations inactive for more than INACTIVE_DAYS, unless kept. */
export function pruneInactive(store: AdvisorStore, now: Date): AdvisorStore {
  if (store.keepHistory) return store;
  const cutoff = now.getTime() - INACTIVE_DAYS * DAY_MS;
  return {
    ...store,
    conversations: store.conversations.filter((c) => Date.parse(c.updatedAt) >= cutoff),
  };
}

/** The first question as a title: one line, at most TITLE_LENGTH characters. */
export function titleFrom(question: string): string {
  const line = question.replace(/\s+/g, " ").trim();
  return line.length <= TITLE_LENGTH ? line : `${line.slice(0, TITLE_LENGTH - 1).trimEnd()}…`;
}

/**
 * A conversation with its first messages, titled by the first question. The server gives its
 * id with the first answer, so a new conversation is stored once that answer arrives.
 */
export function newConversation(
  id: string,
  messages: StoredMessage[],
  projectSlug: string | null,
): StoredConversation {
  const first = messages.find((m) => m.role === "user");
  return {
    id,
    title: titleFrom(first?.text ?? ""),
    projectSlug,
    messages,
    updatedAt: messages.at(-1)?.at ?? new Date(0).toISOString(),
    closed: false,
  };
}

/**
 * The store with conversation first (added or replaced), and the oldest one it pushed out
 * past MAX_CONVERSATIONS, if any, so the page can say so.
 */
export function upsertConversation(
  store: AdvisorStore,
  conversation: StoredConversation,
): { store: AdvisorStore; dropped: StoredConversation | null } {
  const others = store.conversations.filter((c) => c.id !== conversation.id);
  const conversations = [conversation, ...others];
  const dropped = conversations.length > MAX_CONVERSATIONS ? (conversations.at(-1) ?? null) : null;
  return {
    store: { ...store, conversations: conversations.slice(0, MAX_CONVERSATIONS) },
    dropped,
  };
}

/** The conversation with message appended and its activity moved to the message's time. */
export function appendMessage(
  conversation: StoredConversation,
  message: StoredMessage,
): StoredConversation {
  return {
    ...conversation,
    messages: [...conversation.messages, message],
    updatedAt: message.at,
  };
}

/** The store with that conversation closed: it can be read, but not written in. */
export function closeConversation(store: AdvisorStore, id: string): AdvisorStore {
  return {
    ...store,
    conversations: store.conversations.map((c) => (c.id === id ? { ...c, closed: true } : c)),
  };
}

export function setKeepHistory(store: AdvisorStore, keepHistory: boolean): AdvisorStore {
  return { ...store, keepHistory };
}

export function findConversation(store: AdvisorStore, id: string): StoredConversation | null {
  return store.conversations.find((c) => c.id === id) ?? null;
}

function isConversation(value: unknown): value is StoredConversation {
  if (!isRecord(value)) return false;
  const { id, title, projectSlug, messages, updatedAt, closed } = value;
  return (
    typeof id === "string" &&
    id !== "" &&
    typeof title === "string" &&
    (projectSlug === null || typeof projectSlug === "string") &&
    typeof updatedAt === "string" &&
    !Number.isNaN(Date.parse(updatedAt)) &&
    typeof closed === "boolean" &&
    Array.isArray(messages) &&
    messages.every(isMessage)
  );
}

function isMessage(value: unknown): value is StoredMessage {
  if (!isRecord(value) || typeof value.text !== "string" || typeof value.at !== "string") {
    return false;
  }
  if (value.role === "user") return true;
  return (
    value.role === "advisor" && isStringArray(value.tools) && isStringArray(value.projects)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}
