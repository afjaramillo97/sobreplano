// The cards of the search results, and the "desde" each one shows. Shared by the list and the
// map's floating card.
import ProjectCard, { type CardUnit } from "@/components/ProjectCard";
import type { SearchResult } from "@/lib/search";
import { cn } from "@/lib/utils";

/** The "desde" a card shows: the unit type that passes the search, priced on its project's day. */
export function cardUnit({ item, from }: SearchResult): CardUnit | null {
  return from ? { ...from, observedOn: item.lastObservedOn } : null;
}

type Props = {
  results: SearchResult[];
  headingLevel?: 2 | 3;
  /** The project whose pill has the pointer or the focus: its card is outlined. */
  highlighted?: string | null;
  onHighlight?: ((slug: string | null) => void) | undefined;
  /** Whether the first card's image loads eagerly. */
  priority?: boolean;
  className?: string;
};

export function ResultCards({
  results,
  headingLevel = 2,
  highlighted = null,
  onHighlight,
  priority = false,
  className,
}: Props) {
  return (
    <ul className={cn("grid gap-8 md:grid-cols-2", className)}>
      {results.map((result, i) => {
        const slug = result.item.slug;
        return (
          <li key={slug}>
            <ProjectCard
              project={result.item}
              from={cardUnit(result)}
              priority={priority && i === 0}
              headingLevel={headingLevel}
              data-highlighted={highlighted === slug}
              className="data-[highlighted=true]:border-action"
              onPointerEnter={onHighlight && (() => onHighlight(slug))}
              onPointerLeave={onHighlight && (() => onHighlight(null))}
              onFocus={onHighlight && (() => onHighlight(slug))}
              onBlur={onHighlight && (() => onHighlight(null))}
            />
          </li>
        );
      })}
    </ul>
  );
}
