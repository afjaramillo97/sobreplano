// The comparison of 2 to 4 projects (SPEC 11d §5), after the table of the kit's detail page: the
// URL says which, the person chooses private or built area, and the lowest price per m² is marked
// in words. From 1024 px every project is a column; below that two at a time, each with its own
// selector.
//
// Classes are joined with cx, and nothing imports the icons: this island has a JavaScript budget.
import { cx } from "class-variance-authority";
import { type ReactNode, useEffect, useId, useState } from "react";

import Assumptions from "@/components/finance/Assumptions";
import NativeSelect from "@/components/finance/NativeSelect";
import RateNote from "@/components/finance/RateNote";
import { useFinances } from "@/components/finance/useFinances";
import { buttonVariants } from "@/components/ui/button-variants";
import { type ProjectFit, projectFit } from "@/lib/affordability";
import { localStorageOrNull } from "@/lib/browser-storage";
import {
  type AreaBasis,
  areaOf,
  type CompareItem,
  lowestPerM2,
  pricePerM2,
} from "@/lib/compare";
import { MIN_COMPARED, parseCompare, writeComparison } from "@/lib/compare-store";
import { rateEaPct, type StoredFinances } from "@/lib/finances-store";
import {
  formatArea,
  formatChange,
  formatCop,
  formatCount,
  formatDate,
  formatMillions,
  formatShare,
} from "@/lib/format";
import { MUNICIPALITY_NAMES } from "@/lib/projects";
import type { ReferenceRate } from "@/lib/reference-rate";
import { useMediaQuery } from "@/lib/use-media-query";

const linkClass = "font-bold text-action-soft-text underline underline-offset-4 hover:text-action";

type Props = { items: CompareItem[]; reference: ReferenceRate };

export default function Comparison({ items, reference }: Props) {
  // Null until the URL is read: the server cannot know it.
  const [slugs, setSlugs] = useState<string[] | null>(null);

  useEffect(() => {
    const known = new Set(items.map((item) => item.slug));
    const asked = parseCompare(window.location.search, known);
    // A shared link shows the same to anyone: it replaces what this browser had.
    if (asked !== null) writeComparison(localStorageOrNull(), asked);
    setSlugs(asked ?? []);
  }, [items]);

  const projects = (slugs ?? []).flatMap((slug) => items.find((item) => item.slug === slug) ?? []);

  return (
    // Tall from the start, so the footer does not move when the table arrives.
    <div className="page min-h-dvh py-8 lg:py-12">
      {slugs === null ? (
        <p className="text-body text-text-secondary">Cargando la comparación…</p>
      ) : projects.length < MIN_COMPARED ? (
        <Empty />
      ) : (
        <Table projects={projects} reference={reference} />
      )}
    </div>
  );
}

function Empty() {
  return (
    <div className="flex flex-col items-start gap-4 rounded-md border-(length:--border-width-default) border-border bg-bg-subtle p-8">
      <h2 className="text-h3 text-text-primary">Elige al menos 2 proyectos</h2>
      <p className="text-body text-text-secondary">
        En la búsqueda, marca «Comparar» en 2 a 4 proyectos y toca «Ver comparación». También
        puedes sumarlos con «Agregar al comparador» desde cada ficha.
      </p>
      <a href="/proyectos/" className={buttonVariants()}>
        Ir a la búsqueda
      </a>
    </div>
  );
}

type Row = { label: string; cell: (project: CompareItem) => ReactNode };

function Table({ projects, reference }: { projects: CompareItem[]; reference: ReferenceRate }) {
  const [basis, setBasis] = useState<AreaBasis>("private");
  // Below 1024 px, which two projects show.
  const [columns, setColumns] = useState<[number, number]>([0, 1]);
  const { finances } = useFinances();
  const isDesktop = useMediaQuery("(min-width: 1024px)");

  const shown = isDesktop ? projects : columns.flatMap((index) => projects[index] ?? []);
  // Over every compared project, so the mark does not change with the columns on screen.
  const lowest = lowestPerM2(projects, basis);
  const money = householdOf(finances);

  const rows: Row[] = [
    { label: "Constructora y municipio", cell: Developer },
    { label: "Desde", cell: From },
    { label: "Cambio desde el primer precio", cell: Change },
    {
      label: `Tipologías, por área ${basis === "private" ? "privada" : "construida"}`,
      cell: (project) => <Units project={project} basis={basis} lowest={lowest} />,
    },
    {
      label: "Última observación",
      cell: (project) =>
        project.lastObservedOn ? formatDate(project.lastObservedOn) : "Sin precios",
    },
  ];
  if (money) {
    const input = { ...money, rateEaPct: rateEaPct(finances, reference) };
    rows.push({
      label: "¿Me alcanza?",
      cell: (project) =>
        project.from ? (
          <Fit fit={projectFit(input, project.from.priceCop)} />
        ) : (
          "Sin precio publicado"
        ),
    });
  }

  const headerClass = "p-2 text-left align-top lg:p-4";
  const cellClass = "p-2 align-top text-body-sm break-words text-text-secondary lg:p-4";
  const rowClass = "border-b-(length:--border-width-default) border-border";

  return (
    <div className="flex flex-col gap-8">
      <AreaChoice value={basis} onChange={setBasis} />

      {!isDesktop && projects.length > 2 && (
        <ColumnChoice projects={projects} columns={columns} onChange={setColumns} />
      )}

      <table className="w-full table-fixed border-collapse">
        <caption className="sr-only">
          Comparación de {formatCount(projects.length, "proyecto", "proyectos")}
        </caption>
        <thead>
          <tr className="bg-bg-subtle">
            {isDesktop && <td className="w-48" />}
            {shown.map((project) => (
              <th key={project.slug} scope="col" className={headerClass}>
                <a
                  href={`/proyectos/${project.slug}/`}
                  className="text-body font-bold break-words text-text-primary underline underline-offset-4 hover:text-action"
                >
                  {project.name}
                </a>
              </th>
            ))}
          </tr>
        </thead>
        {isDesktop ? (
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className={rowClass}>
                <th scope="row" className={cx(headerClass, "text-body-sm font-bold text-text-primary")}>
                  {row.label}
                </th>
                {shown.map((project) => (
                  <td key={project.slug} className={cellClass}>
                    {row.cell(project)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        ) : (
          // On a phone the label spans both columns, in its own row group.
          rows.map((row) => (
            <tbody key={row.label} className={rowClass}>
              <tr>
                <th
                  scope="rowgroup"
                  colSpan={2}
                  className="px-2 pt-4 text-left text-body-sm font-bold text-text-primary"
                >
                  {row.label}
                </th>
              </tr>
              <tr>
                {shown.map((project) => (
                  <td key={project.slug} className={cellClass}>
                    {row.cell(project)}
                  </td>
                ))}
              </tr>
            </tbody>
          ))
        )}
      </table>

      <p className="text-body-sm text-text-muted">
        Precios desde publicados por las constructoras: pueden no incluir parqueadero, cuarto
        útil, acabados ni gastos de escrituración. El área es la que reporta cada constructora; si
        falta, no la estimamos.
      </p>

      {money ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-body-sm text-text-secondary">
            «¿Me alcanza?» usa un ingreso de {formatCop(money.incomeCop)} al mes y{" "}
            {formatCop(money.savingsCop)} de ahorro, a {money.years} años, con cuota inicial del{" "}
            {formatShare(money.downPaymentPct)}, para el precio desde de cada proyecto.
          </p>
          <RateNote
            reference={reference}
            housing={finances.housing}
            custom={finances.rate.source === "custom" ? finances.rate.eaPct : null}
          />
          <a href="/calculadora/" className={cx("text-body-sm", linkClass)}>
            Cambiar mis datos o la tasa en la calculadora
          </a>
        </div>
      ) : (
        <p className="text-body-sm text-text-secondary">
          Escribe tu ingreso y tu ahorro{" "}
          <a href="/calculadora/" className={linkClass}>
            en la calculadora
          </a>{" "}
          para ver aquí si cada proyecto te alcanza.
        </p>
      )}

      <a href="/proyectos/" className={cx(buttonVariants({ variant: "soft" }), "self-start")}>
        Cambiar la selección
      </a>
      <Assumptions />
    </div>
  );
}

/** The saved figures "¿Me alcanza?" needs, or null without income and savings. */
function householdOf(finances: StoredFinances) {
  const { incomeCop, savingsCop, years, downPaymentPct, monthsToDelivery } = finances;
  if (incomeCop === null || savingsCop === null) return null;
  return { incomeCop, savingsCop, years, downPaymentPct, monthsToDelivery };
}

function AreaChoice({ value, onChange }: { value: AreaBasis; onChange: (v: AreaBasis) => void }) {
  const name = useId();
  const options: [AreaBasis, string][] = [
    ["private", "Área privada"],
    ["built", "Área construida"],
  ];
  return (
    <fieldset>
      <legend className="text-label text-text-primary">Área para el precio por m²</legend>
      <div className="mt-2 flex flex-wrap gap-2">
        {options.map(([basis, label]) => (
          <label key={basis} className="cursor-pointer">
            <input
              type="radio"
              name={name}
              className="peer sr-only"
              checked={value === basis}
              onChange={() => onChange(basis)}
            />
            <span className="flex h-(--size-control-md) items-center rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface px-4 text-body-sm text-text-secondary peer-checked:border-action peer-checked:bg-action-soft peer-checked:font-bold peer-checked:text-text-primary peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-solid peer-focus-visible:outline-ring">
              {label}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function ColumnChoice({
  projects,
  columns,
  onChange,
}: {
  projects: CompareItem[];
  columns: [number, number];
  onChange: (columns: [number, number]) => void;
}) {
  const id = useId();
  /** Choosing the project of the other column swaps them: never the same twice. */
  function choose(side: 0 | 1, index: number) {
    const next: [number, number] = [...columns];
    if (columns[1 - side] === index) next[1 - side] = columns[side];
    next[side] = index;
    onChange(next);
  }
  // One above the other on a phone: side by side they would cut the names.
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {([0, 1] as const).map((side) => (
        <div key={side} className="flex min-w-0 flex-col gap-2">
          <label htmlFor={`${id}-${side}`} className="text-label text-text-primary">
            Columna {side + 1}
          </label>
          <NativeSelect
            id={`${id}-${side}`}
            value={columns[side]}
            onChange={(event) => choose(side, Number(event.target.value))}
          >
            {projects.map((project, index) => (
              <option key={project.slug} value={index}>
                {project.name}
              </option>
            ))}
          </NativeSelect>
        </div>
      ))}
    </div>
  );
}

function Developer(project: CompareItem) {
  const place = [MUNICIPALITY_NAMES[project.municipality], project.neighborhood]
    .filter(Boolean)
    .join(", ");
  return (
    <>
      <span className="block font-bold text-text-primary">{project.developer}</span>
      <span className="block">{place}</span>
    </>
  );
}

function From({ from }: CompareItem) {
  if (!from) return "Sin precio publicado";
  return (
    <>
      <span className="block text-price text-text-price">{formatMillions(from.priceCop)}</span>
      <span className="block">{from.name}</span>
      {from.observedOn && <span className="block">observado el {formatDate(from.observedOn)}</span>}
    </>
  );
}

function Change({ changePct, firstObservedOn }: CompareItem) {
  if (changePct === null || !firstObservedOn) return "Aún no hay cambio que mostrar";
  return (
    <>
      {/* The kit's price change badge without its icon (rule 5). */}
      <span className="inline-flex min-h-(--size-chip) items-center rounded-sm bg-change-bg px-2 text-caption font-bold text-change-text uppercase">
        {formatChange(changePct)}
      </span>
      <span className="mt-1 block">desde el {formatDate(firstObservedOn)}</span>
    </>
  );
}

function Units({
  project,
  basis,
  lowest,
}: {
  project: CompareItem;
  basis: AreaBasis;
  lowest: number | null;
}) {
  if (project.units.length === 0) return "Sin precio vigente";
  return (
    <ul className="flex flex-col gap-4">
      {project.units.map((unit, index) => {
        const area = areaOf(unit, basis);
        const perM2 = pricePerM2(unit, basis);
        const rooms = [
          unit.bedrooms !== null && formatCount(unit.bedrooms, "alcoba", "alcobas"),
          unit.bathrooms !== null && formatCount(unit.bathrooms, "baño", "baños"),
        ].filter(Boolean);
        return (
          // Two unit types may share a name.
          <li key={`${unit.name}-${index}`} className="flex flex-col tabular-nums">
            <span className="font-bold text-text-primary">{unit.name}</span>
            {rooms.length > 0 && <span>{rooms.join(" · ")}</span>}
            {area !== null && <span>{formatArea(area)}</span>}
            <span className="font-bold text-text-primary">
              {perM2 === null ? "No reportada" : `${formatCop(perM2)} /m²`}
            </span>
            {perM2 !== null && perM2 === lowest && (
              <span className="self-start rounded-sm bg-action-soft px-2 text-caption font-bold text-action-soft-text">
                Menor $/m²
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Fit({ fit }: { fit: ProjectFit }) {
  const payment = formatCop(fit.mortgage.monthlyPaymentCop);
  const share = formatShare(fit.paymentSharePct);
  if (fit.fits) {
    return (
      <>
        <span className="block text-body font-bold text-text-price">Te alcanza</span>
        <span className="block">
          Cuota de {payment}, el {share} de tu ingreso
        </span>
      </>
    );
  }
  return (
    <>
      {fit.missingCop > 0 && (
        <span className="block font-bold text-text-primary">
          Te faltan {formatCop(fit.missingCop)} de cuota inicial
        </span>
      )}
      {fit.installment && (
        <span className="block">{formatCop(fit.installment.cop)} al mes durante la obra</span>
      )}
      {fit.overIncome && (
        <span className="block font-bold text-text-primary">
          Cuota de {payment}, el {share} de tu ingreso (máximo 40 %)
        </span>
      )}
    </>
  );
}
