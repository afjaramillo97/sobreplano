// The cards of the search results, and the "desde" each one shows. Shared by the list and the
// map's floating card.
import ProjectCard, { type CardUnit } from "@/components/ProjectCard";
import { isComparisonFull } from "@/lib/compare-store";
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
  /** The "Comparar" checkbox of each card (SPEC 11d): the chosen slugs and how to toggle one. */
  compare?: { slugs: string[]; toggle: (slug: string) => void };
  className?: string;
};

export function ResultCards({
  results,
  headingLevel = 2,
  highlighted = null,
  onHighlight,
  priority = false,
  compare,
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
              action={
                compare && (
                  <CompareCheckbox
                    name={result.item.name}
                    checked={compare.slugs.includes(slug)}
                    full={isComparisonFull(compare.slugs)}
                    onToggle={() => compare.toggle(slug)}
                  />
                )
              }
            />
          </li>
        );
      })}
    </ul>
  );
}

function CompareCheckbox({
  name,
  checked,
  full,
  onToggle,
}: {
  name: string;
  checked: boolean;
  full: boolean;
  onToggle: () => void;
}) {
  const disabled = full && !checked;
  return (
    // Without JavaScript it could not work, so it shows only with it.
    <label
      title={disabled ? "Ya elegiste el máximo de proyectos" : undefined}
      className={cn(
        "flex h-(--size-control-sm) cursor-pointer items-center gap-2 rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface px-3 text-body-sm font-bold text-text-primary shadow-sm no-js:hidden",
        disabled && "cursor-default opacity-50",
      )}
    >
      {/* Native, not Radix: its server render carries a style attribute the CSP blocks. Drawn
          like ui/checkbox, in the action color even unchecked (DESIGN.md, rule 11). */}
      <span className="relative flex size-5 shrink-0">
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={onToggle}
          aria-label={`Comparar ${name}`}
          className="peer size-5 cursor-pointer appearance-none rounded-sm border-(length:--border-width-strong) border-primary bg-background outline-hidden checked:bg-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring disabled:cursor-default"
        />
        <span
          aria-hidden="true"
          className="pointer-events-none absolute top-1 left-[7px] hidden h-2.5 w-1.5 rotate-45 border-r-2 border-b-2 border-primary-foreground peer-checked:block"
        />
      </span>
      Comparar
    </label>
  );
}
