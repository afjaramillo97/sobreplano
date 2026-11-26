// The right column, after the kit's Message property preview: the project in context (image,
// name and place, the "desde" unit type's features, a few rows and "Ver ficha del proyecto"),
// or, without one, the small cards of the projects the conversation named.
import type { ReactNode } from "react";

import Icon from "@/components/Icon";
import PriceChangeBadge from "@/components/PriceChangeBadge";
import ProjectCard from "@/components/ProjectCard";
import ProjectImage from "@/components/ProjectImage";
import { buttonVariants } from "@/components/ui/button";
import { cardProject } from "@/lib/advisor/view";
import { formatArea, formatCount, formatDate, formatMillions } from "@/lib/format";
import { MUNICIPALITY_NAMES } from "@/lib/projects";
import type { SearchItem } from "@/lib/search";
import { cn } from "@/lib/utils";

type Props = {
  project: SearchItem | null;
  mentioned: readonly SearchItem[];
  /** Takes the project out of context; the panel then lists the mentioned ones. */
  onClose?: (() => void) | undefined;
  className?: string | undefined;
};

export function ProjectPanel({ project, mentioned, onClose, className }: Props) {
  if (project) return <ProjectInContext project={project} onClose={onClose} className={className} />;
  return (
    <section aria-labelledby="proyectos-conversacion" className={cn("flex flex-col gap-4", className)}>
      <h2 id="proyectos-conversacion" className="text-title text-text-heading-alt">
        Proyectos en esta conversación
      </h2>
      {mentioned.length === 0 ? (
        <p className="text-body-sm text-text-muted">
          Aquí aparecen los proyectos que mencione el asesor, con enlace a su ficha.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {mentioned.map((item) => (
            <li key={item.slug}>
              <ProjectCard project={cardProject(item)} size="sm" />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ProjectInContext({
  project,
  onClose,
  className,
}: {
  project: SearchItem;
  onClose: (() => void) | undefined;
  className: string | undefined;
}) {
  const from = project.units[0] ?? null;
  const place = [project.neighborhood, MUNICIPALITY_NAMES[project.municipality]]
    .filter(Boolean)
    .join(", ");
  return (
    <section aria-labelledby="proyecto-contexto" className={cn("flex flex-col gap-6", className)}>
      <div className="flex items-center justify-between gap-4">
        <p className="text-body-sm font-bold text-text-muted">Proyecto en esta consulta</p>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="flex size-(--size-control-sm) items-center justify-center rounded-md text-text-primary outline-hidden hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring"
          >
            <Icon name="close-outline" size={24} label={`Quitar ${project.name} de la consulta`} />
          </button>
        )}
      </div>
      <ProjectImage className="aspect-[323/200] rounded-md" />
      <div className="flex flex-col gap-1">
        <h2 id="proyecto-contexto" className="text-h3 text-text-heading-alt">
          {project.name}
        </h2>
        <p className="text-body-sm text-text-muted">{place}</p>
      </div>
      {from && (
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-2 text-body-sm text-text-secondary">
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
      )}
      <dl className="flex flex-col gap-3 border-y-(length:--border-width-default) border-border py-4 text-body-sm">
        <Row label="Desde">
          {from ? (
            <span className="text-right">
              <span className="font-bold text-text-price">{formatMillions(from.priceCop)}</span>
              <span className="block text-text-muted">
                {from.name}
                {project.lastObservedOn && ` · ${formatDate(project.lastObservedOn)}`}
              </span>
            </span>
          ) : (
            "Sin precio publicado"
          )}
        </Row>
        {from?.changePct != null && (
          <Row label="Desde el primer precio">
            <PriceChangeBadge changePct={from.changePct} />
          </Row>
        )}
        <Row label="Constructora">{project.developer.name}</Row>
      </dl>
      <a
        href={`/proyectos/${project.slug}/`}
        className={buttonVariants({ variant: "soft", className: "w-full" })}
      >
        Ver ficha del proyecto
      </a>
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="text-text-muted">{label}</dt>
      <dd className="font-bold text-text-primary">{children}</dd>
    </div>
  );
}
