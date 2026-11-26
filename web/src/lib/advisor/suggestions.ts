/**
 * Suggested questions of the advisor's empty state (SPEC 11c §6): general ones, or three about
 * the project in context when the page was opened from its page. The project travels in the
 * question itself, by name; the API has no context field.
 */
import type { Municipality } from "../api/client";
import { MUNICIPALITY_NAMES } from "../projects";

export const GENERAL_SUGGESTIONS: readonly string[] = [
  "¿Qué proyectos hay en Itagüí por menos de 300 millones?",
  "¿Cuáles proyectos han subido más desde que los siguen?",
  "Compara los dos proyectos más baratos de Envigado",
  "Gano 6 millones y tengo 40 ahorrados, ¿qué puedo comprar?",
];

export type SuggestionProject = { name: string; municipality: Municipality };

/** The questions to suggest: about the project when there is one, the general ones if not. */
export function suggestionsFor(project: SuggestionProject | null): string[] {
  if (project === null) return [...GENERAL_SUGGESTIONS];
  const { name } = project;
  return [
    `¿Cuánto ha subido ${name}?`,
    `¿Cuánto pagaría al mes de cuota inicial en ${name}?`,
    `Compara ${name} con otros proyectos de ${MUNICIPALITY_NAMES[project.municipality]}`,
  ];
}
