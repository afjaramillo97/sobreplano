/**
 * What the advisor page shows of its data (SPEC 11c): the card of a catalog project, the
 * projects a conversation names, and the times and previews of the conversation list. Pure,
 * so the page only lays out and tests/unit/advisor-view.test.ts pins the rules.
 */
import type { CardProject } from "@/components/ProjectCard";

import { formatDate } from "../format";
import { normalizeText, type SearchItem } from "../search";
import type { StoredConversation, StoredMessage } from "./store";

/** The card of a catalog project: its "desde" is the cheapest current unit type. */
export function cardProject(item: SearchItem): CardProject {
  const cheapest = item.units[0];
  return {
    slug: item.slug,
    name: item.name,
    developer: item.developer,
    municipality: item.municipality,
    neighborhood: item.neighborhood,
    from: cheapest
      ? {
          name: cheapest.name,
          bedrooms: cheapest.bedrooms,
          bathrooms: cheapest.bathrooms,
          areaM2: cheapest.areaM2,
          areaBasis: cheapest.areaBasis,
          priceCop: cheapest.priceCop,
          changePct: cheapest.changePct,
          observedOn: item.lastObservedOn,
        }
      : null,
  };
}

/** The slugs the conversation's answers name, each once, in order of first mention. */
export function conversationProjects(messages: readonly StoredMessage[]): string[] {
  const slugs = new Set<string>();
  for (const message of messages) {
    if (message.role === "advisor") for (const slug of message.projects) slugs.add(slug);
  }
  return [...slugs];
}

/** The catalog items of those slugs, skipping the ones the build does not have. */
export function knownProjects(
  slugs: readonly string[],
  catalog: ReadonlyMap<string, SearchItem>,
): SearchItem[] {
  return slugs.flatMap((slug) => {
    const item = catalog.get(slug);
    return item ? [item] : [];
  });
}

const clock = new Intl.DateTimeFormat("es-CO", { hour: "numeric", minute: "2-digit" });

/** The time of a message, as the kit puts it under each bubble: "3:45 p. m.". */
export function messageTime(iso: string): string {
  return clock.format(new Date(iso));
}

const HOUR_MS = 60 * 60 * 1000;

/** When a conversation was last active, for the list: "hace 5 min", "hace 3 h", "ayer", "7 nov 2026". */
export function lastActivity(iso: string, now: Date): string {
  const at = new Date(iso);
  const elapsed = now.getTime() - at.getTime();
  if (elapsed < 60 * 1000) return "ahora";
  if (elapsed < HOUR_MS) return `hace ${Math.floor(elapsed / 60_000)} min`;
  if (at.toDateString() === now.toDateString()) return `hace ${Math.floor(elapsed / HOUR_MS)} h`;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (at.toDateString() === yesterday.toDateString()) return "ayer";
  const day = `${at.getFullYear()}-${String(at.getMonth() + 1).padStart(2, "0")}-${String(at.getDate()).padStart(2, "0")}`;
  return formatDate(day);
}

const PREVIEW_LENGTH = 90;

/** The last answer as one line of plain text, for the list: Markdown marks and links go. */
export function conversationPreview(conversation: StoredConversation): string {
  const last = conversation.messages.findLast((m) => m.role === "advisor") ?? conversation.messages.at(-1);
  if (!last) return "";
  const plain = last.text
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1") // links and images keep their text
    .replace(/[|*_`#>~-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return plain.length <= PREVIEW_LENGTH ? plain : `${plain.slice(0, PREVIEW_LENGTH - 1).trimEnd()}…`;
}

/** The conversations whose title or messages contain the query, ignoring accents and case. */
export function filterConversations(
  conversations: readonly StoredConversation[],
  query: string,
): StoredConversation[] {
  const needle = normalizeText(query);
  if (needle === "") return [...conversations];
  return conversations.filter((c) =>
    normalizeText([c.title, ...c.messages.map((m) => m.text)].join(" ")).includes(needle),
  );
}

/** Whether the conversation ends in a question without an answer (the tab closed mid-turn). */
export function unansweredQuestion(conversation: StoredConversation | null): string | null {
  const last = conversation?.messages.at(-1);
  return last?.role === "user" ? last.text : null;
}
