import { describe, expect, it } from "vitest";

import { newConversation, type StoredMessage } from "../../src/lib/advisor/store";
import {
  cardProject,
  conversationPreview,
  conversationProjects,
  filterConversations,
  knownProjects,
  lastActivity,
  unansweredQuestion,
} from "../../src/lib/advisor/view";
import type { SearchItem } from "../../src/lib/search";

const item: SearchItem = {
  slug: "bosque-de-ditaires",
  name: "Bosque de Ditaires",
  developer: { name: "Piedra Azul", slug: "piedra-azul" },
  municipality: "itagui",
  neighborhood: "Ditaires",
  location: null,
  lastObservedOn: "2026-11-02",
  units: [
    {
      name: "Tipo A",
      bedrooms: 2,
      bathrooms: 2,
      areaM2: 59.9,
      areaBasis: "private",
      priceCop: 381_000_000,
      changePct: 4.4,
    },
  ],
  searchText: "bosque de ditaires",
};

function advisor(text: string, projects: string[]): StoredMessage {
  return { role: "advisor", text, tools: [], projects, at: "2026-11-25T15:00:00Z" };
}

function user(text: string): StoredMessage {
  return { role: "user", text, at: "2026-11-25T14:59:00Z" };
}

describe("cardProject", () => {
  it("takes the cheapest current unit type as the card's desde, with the project's day", () => {
    expect(cardProject(item).from).toMatchObject({
      name: "Tipo A",
      priceCop: 381_000_000,
      changePct: 4.4,
      observedOn: "2026-11-02",
    });
    expect(cardProject({ ...item, units: [] }).from).toBeNull();
  });
});

describe("the projects of a conversation", () => {
  it("lists the answers' projects once each, in order, and only the ones in the catalog", () => {
    const messages = [user("Hola"), advisor("a", ["b", "a"]), advisor("b", ["a", "c"])];
    expect(conversationProjects(messages)).toEqual(["b", "a", "c"]);
    const catalog = new Map([["bosque-de-ditaires", item]]);
    expect(knownProjects(["otro", "bosque-de-ditaires"], catalog)).toEqual([item]);
  });
});

describe("lastActivity", () => {
  const now = new Date("2026-11-25T15:00:00-05:00");
  it.each([
    ["2026-11-25T14:59:30-05:00", "ahora"],
    ["2026-11-25T14:15:00-05:00", "hace 45 min"],
    ["2026-11-25T09:00:00-05:00", "hace 6 h"],
    ["2026-11-24T22:00:00-05:00", "ayer"],
  ])("%s → %s", (iso, label) => {
    expect(lastActivity(iso, now)).toBe(label);
  });

  it("gives the date further back", () => {
    expect(lastActivity("2026-11-20T10:00:00-05:00", now)).toMatch(/20 nov/);
  });
});

describe("the conversation list", () => {
  const a = newConversation("a", [user("¿Qué hay en Itagüí?"), advisor("**Bosque** de [Ditaires](/x/)", [])], null);
  const b = newConversation("b", [user("Créditos")], null);

  it("previews the last answer as plain text", () => {
    expect(conversationPreview(a)).toBe("Bosque de Ditaires");
    expect(conversationPreview(b)).toBe("Créditos");
  });

  it("filters by title and messages, without accents or case", () => {
    expect(filterConversations([a, b], "itagui").map((c) => c.id)).toEqual(["a"]);
    expect(filterConversations([a, b], "DITAIRES").map((c) => c.id)).toEqual(["a"]);
    expect(filterConversations([a, b], "  ")).toHaveLength(2);
  });

  it("finds a question left without its answer", () => {
    expect(unansweredQuestion(b)).toBe("Créditos");
    expect(unansweredQuestion(a)).toBeNull();
    expect(unansweredQuestion(null)).toBeNull();
  });
});
