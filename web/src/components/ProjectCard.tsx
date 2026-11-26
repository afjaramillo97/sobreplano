// The kit's large project card (352 wide, 200 high image) and, as size="sm", the small card
// of the kit's Message screen (the link card inside a bubble: 48 lavender square, two lines).
// The whole card is one link, with one focus stop. "Desde" always comes with its unit type and
// its date (rule 6).
//
// Astro pages render it without hydrating it; the search island renders it in the browser,
// with the "desde" that passes the filters.
import type * as React from "react";
import type { Municipality } from "@/lib/api/client";
import { formatArea, formatChange, formatCount, formatDate, formatMillions } from "@/lib/format";
import { MUNICIPALITY_NAMES } from "@/lib/projects";
import { cn } from "@/lib/utils";
import Icon from "./Icon";
import PriceChangeBadge from "./PriceChangeBadge";
import ProjectImage from "./ProjectImage";

/** The unit type a card shows as its "desde"; a UnitTypeView fits. */
export type CardUnit = {
  name: string;
  bedrooms: number | null;
  bathrooms: number | null;
  areaM2: number;
  areaBasis: "private" | "built";
  priceCop: number | null;
  changePct: number | null;
  /** The day of its price. */
  observedOn: string | null;
};

/** What a card shows of a project; a ProjectView fits. */
export type CardProject = {
  slug: string;
  name: string;
  developer: { name: string };
  municipality: Municipality;
  neighborhood: string | null;
  from?: CardUnit | null;
};

type Props = Omit<React.ComponentProps<"a">, "href" | "children"> & {
  project: CardProject;
  /** The "desde" to show, when it is not the project's own (a search with unit filters). */
  from?: CardUnit | null;
  /** For the first card on screen: its image loads eagerly. */
  priority?: boolean;
  /** Heading level of the project name, so the page outline stays in order. */
  headingLevel?: 2 | 3;
  /** "sm": the small card of the advisor's answers and panel (SPEC 11c). */
  size?: "md" | "sm";
  /** A control over the image's top right corner, such as the search's "Comparar". It is a
      sibling of the link, never inside it: controls do not nest. */
  action?: React.ReactNode;
};

export default function ProjectCard({
  project,
  from: fromProp,
  priority = false,
  headingLevel = 2,
  size = "md",
  action,
  className,
  ...linkProps
}: Props) {
  const from = fromProp === undefined ? (project.from ?? null) : fromProp;
  const Heading = headingLevel === 3 ? "h3" : "h2";
  const place = [MUNICIPALITY_NAMES[project.municipality], project.neighborhood]
    .filter(Boolean)
    .join(", ");
  if (size === "sm") {
    return <SmallCard project={project} from={from} place={place} className={className} {...linkProps} />;
  }
  const card = (
    <a
      href={`/proyectos/${project.slug}/`}
      className={cn(
        "group relative flex h-full flex-col rounded-md border-(length:--border-width-default) border-border bg-bg-surface transition-colors duration-(--duration-fast) ease-out hover:border-border-input",
        className,
      )}
      {...linkProps}
    >
      <div className="relative">
        <ProjectImage className="aspect-[352/200] rounded-t-md" priority={priority} />
        {/* In the flow below the image, nudged 12 down and 8 left past the card's edge: the
            layout of the approved SPEC 11a captures (the badge is position: relative). */}
        {from?.changePct != null && (
          <PriceChangeBadge changePct={from.changePct} ribbon className="-bottom-3 -left-2" />
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-6">
        {from?.priceCop != null ? (
          <div className="flex flex-col">
            <p className="flex items-baseline gap-1">
              <span className="text-body text-text-muted">desde</span>
              <span className="text-price-lg text-text-price">{formatMillions(from.priceCop)}</span>
            </p>
            <p className="text-body-sm text-text-muted">
              {from.name} · precio del {from.observedOn && formatDate(from.observedOn)}
            </p>
          </div>
        ) : (
          <p className="text-label text-text-secondary">Sin precio publicado</p>
        )}
        <Heading className="text-h3 text-text-primary">{project.name}</Heading>
        <p className="text-body font-medium text-text-muted">
          {project.developer.name} · {place}
        </p>
        {from && (
          <div className="mt-auto pt-4">
            <hr className="mb-4 border-t-(length:--border-width-default) border-border" />
            <ul className="flex flex-wrap items-center gap-x-4 gap-y-3 text-body-sm text-text-secondary">
              {from.bedrooms != null && (
                <li className="inline-flex items-center gap-2">
                  <Icon name="bed-outline" size={20} className="text-action" />
                  {formatCount(from.bedrooms, "alcoba", "alcobas")}
                </li>
              )}
              {from.bathrooms != null && (
                <li className="inline-flex items-center gap-2">
                  <Icon name="bath-outline" size={20} className="text-action" />
                  {formatCount(from.bathrooms, "baño", "baños")}
                </li>
              )}
              <li className="inline-flex items-center gap-2">
                <Icon name="square-meters-outline" size={20} className="text-action" />
                {formatArea(from.areaM2)}
                <span className="sr-only">
                  {from.areaBasis === "private" ? "de área privada" : "de área construida"}
                </span>
              </li>
            </ul>
          </div>
        )}
      </div>
    </a>
  );
  if (!action) return card;
  return (
    <div className="relative h-full">
      {card}
      <div className="absolute top-3 right-3">{action}</div>
    </div>
  );
}

type SmallCardProps = Omit<React.ComponentProps<"a">, "href" | "children"> & {
  project: CardProject;
  from: CardUnit | null;
  place: string;
};

/** The small card: name, "desde" with its change, and the unit type and day of that price. */
function SmallCard({ project, from, place, className, ...linkProps }: SmallCardProps) {
  return (
    <a
      href={`/proyectos/${project.slug}/`}
      className={cn(
        "flex items-start gap-4 rounded-md border-(length:--border-width-default) border-border bg-bg-surface p-2 pr-4 text-left transition-colors duration-(--duration-fast) ease-out outline-hidden hover:border-border-input focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring motion-reduce:transition-none",
        className,
      )}
      {...linkProps}
    >
      <span className="flex size-12 shrink-0 items-center justify-center rounded-md bg-bg-selected text-action">
        <Icon name="properties-outline" size={24} />
      </span>
      <span className="flex min-w-0 flex-col gap-0.5 py-1">
        <span className="text-body-sm font-bold text-text-primary">{project.name}</span>
        {from?.priceCop != null ? (
          <>
            <span className="text-body-sm text-text-secondary">
              desde <span className="font-bold text-text-price">{formatMillions(from.priceCop)}</span>
              {from.changePct != null && <> · {formatChange(from.changePct)}</>}
            </span>
            <span className="text-body-sm text-text-muted">
              {from.name} · precio del {from.observedOn && formatDate(from.observedOn)}
            </span>
          </>
        ) : (
          <span className="text-body-sm text-text-muted">Sin precio publicado</span>
        )}
        <span className="text-body-sm text-text-muted">{place}</span>
      </span>
    </a>
  );
}
