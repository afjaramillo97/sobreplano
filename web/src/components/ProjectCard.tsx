// The kit's large project card (352 wide, 200 high image). The whole card is one link, with
// one focus stop. "Desde" always comes with its unit type and its date (rule 6).
//
// Astro pages render it without hydrating it; the search island renders it in the browser,
// with the "desde" that passes the filters.
import type * as React from "react";
import type { Municipality } from "@/lib/api/client";
import { formatArea, formatCount, formatDate, formatMillions } from "@/lib/format";
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
};

export default function ProjectCard({
  project,
  from: fromProp,
  priority = false,
  headingLevel = 2,
  className,
  ...linkProps
}: Props) {
  const from = fromProp === undefined ? (project.from ?? null) : fromProp;
  const Heading = headingLevel === 3 ? "h3" : "h2";
  const place = [MUNICIPALITY_NAMES[project.municipality], project.neighborhood]
    .filter(Boolean)
    .join(", ");
  return (
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
}
