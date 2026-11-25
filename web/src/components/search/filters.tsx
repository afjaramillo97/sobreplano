// The filter controls, shared by the quick-filter popovers and the "Más filtros" sheet. Each
// applies at once: there is no "Aplicar" step (SPEC 11b).
import { useId } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import type { Municipality } from "@/lib/api/client";
import { formatMillionsShort } from "@/lib/format";
import { MUNICIPALITY_NAMES } from "@/lib/projects";
import { type PriceHistogram, ROOMS_MAX, ROOMS_MIN, type SortKey } from "@/lib/search";
import { cn } from "@/lib/utils";
import { SORT_OPTION } from "./labels";

const MILLION = 1_000_000;

/** A range slider's value, as filter bounds: a thumb at its end means "no bound". */
function toBounds(
  [low, high]: number[],
  range: { min: number; max: number },
): [number | null, number | null] {
  return [
    low === undefined || low <= range.min ? null : low,
    high === undefined || high >= range.max ? null : high,
  ];
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

type RangeProps = {
  min: number | null;
  max: number | null;
  onChange: (min: number | null, max: number | null) => void;
};

/** The price range with the histogram of the "desde" that pass the other filters. */
export function PriceFilter({
  histogram,
  min,
  max,
  onChange,
}: RangeProps & { histogram: PriceHistogram }) {
  const low = clamp(min ?? histogram.min, histogram.min, histogram.max);
  const high = clamp(max ?? histogram.max, histogram.min, histogram.max);
  const tallest = Math.max(1, ...histogram.bins);
  const width = (histogram.max - histogram.min) / histogram.bins.length;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-label text-text-primary">
        Precio desde
      </p>
      <p className="-mt-3 text-body-sm text-text-secondary">
        {formatMillionsShort(low)} a {formatMillionsShort(high)}
      </p>
      <div aria-hidden="true" className="flex h-16 items-end gap-0.5">
        {histogram.bins.map((count, i) => {
          const start = histogram.min + i * width;
          const inside = start + width > low && start < high;
          return (
            <span
              key={start}
              className={cn(
                "min-h-0.5 flex-1 rounded-t-sm",
                inside && count > 0 ? "bg-action" : "bg-border-input",
              )}
              style={{ height: `${(count / tallest) * 100}%` }}
            />
          );
        })}
      </div>
      <Slider
        min={histogram.min}
        max={histogram.max}
        step={MILLION}
        minStepsBetweenThumbs={1}
        value={[low, high]}
        onValueChange={(value) => onChange(...toBounds(value, histogram))}
        thumbLabels={["Precio mínimo", "Precio máximo"]}
        valueText={formatMillionsShort}
      />
    </div>
  );
}

/** The area range, in whole m². */
export function AreaFilter({
  range,
  min,
  max,
  onChange,
}: RangeProps & { range: { min: number; max: number } }) {
  const low = clamp(min ?? range.min, range.min, range.max);
  const high = clamp(max ?? range.max, range.min, range.max);
  const m2 = (value: number) => `${value} m²`;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-label text-text-primary">Área</p>
      <p className="-mt-3 text-body-sm text-text-secondary">
        {m2(low)} a {m2(high)}
      </p>
      <Slider
        min={range.min}
        max={range.max}
        step={1}
        minStepsBetweenThumbs={1}
        value={[low, high]}
        onValueChange={(value) => onChange(...toBounds(value, range))}
        thumbLabels={["Área mínima", "Área máxima"]}
        valueText={m2}
      />
    </div>
  );
}

/** A minimum of bedrooms or bathrooms: "Todas", 1+ ... 5+, as radio buttons. */
export function RoomsFilter({
  legend,
  noun,
  value,
  onChange,
}: {
  legend: string;
  /** Plural, for screen readers: "alcobas" reads "2 alcobas o más". */
  noun: string;
  value: number | null;
  onChange: (value: number | null) => void;
}) {
  const name = useId();
  const options: (number | null)[] = [null];
  for (let n = ROOMS_MIN; n <= ROOMS_MAX; n++) options.push(n);
  return (
    <fieldset>
      <legend className="text-label text-text-primary">{legend}</legend>
      <div className="mt-3 flex flex-wrap gap-2">
        {options.map((n) => (
          <label key={n ?? "todas"} className="cursor-pointer">
            <input
              type="radio"
              name={name}
              className="peer sr-only"
              checked={value === n}
              onChange={() => onChange(n)}
            />
            <span className="flex h-(--size-control-sm) min-w-12 items-center justify-center rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface px-3 text-body-sm text-text-secondary transition-colors duration-(--duration-fast) peer-checked:border-action peer-checked:bg-action-soft peer-checked:font-bold peer-checked:text-action-soft-text peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus-ring peer-focus-visible:outline-solid hover:border-action motion-reduce:transition-none">
              {n === null ? (
                "Todas"
              ) : (
                <>
                  <span aria-hidden="true">{n}+</span>
                  <span className="sr-only">
                    {n} {noun} o más
                  </span>
                </>
              )}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** The municipalities that have projects, as checkboxes. */
export function MunicipalityFilter({
  options,
  value,
  onChange,
}: {
  options: Municipality[];
  value: Municipality[];
  onChange: (value: Municipality[]) => void;
}) {
  const id = useId();
  return (
    <fieldset>
      <legend className="text-label text-text-primary">Municipio</legend>
      <ul className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3">
        {options.map((m) => (
          <li key={m} className="flex items-center gap-3">
            <Checkbox
              id={`${id}-${m}`}
              checked={value.includes(m)}
              onCheckedChange={(checked) =>
                onChange(checked === true ? [...value, m] : value.filter((x) => x !== m))
              }
            />
            <label htmlFor={`${id}-${m}`} className="cursor-pointer text-body text-text-primary">
              {MUNICIPALITY_NAMES[m]}
            </label>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}

/** The developers of the catalog, in a native select. */
export function DeveloperFilter({
  options,
  value,
  onChange,
}: {
  options: { slug: string; name: string }[];
  value: string | null;
  onChange: (value: string | null) => void;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-3">
      <label htmlFor={id} className="text-label text-text-primary">
        Constructora
      </label>
      <Select id={id} value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">Todas las constructoras</option>
        {options.map((d) => (
          <option key={d.slug} value={d.slug}>
            {d.name}
          </option>
        ))}
      </Select>
    </div>
  );
}

/** The kit's sort menu: 44 high rows, the chosen one lavender. */
export function SortOptions({
  value,
  onChange,
}: {
  value: SortKey;
  onChange: (value: SortKey) => void;
}) {
  const name = useId();
  return (
    <fieldset>
      <legend className="sr-only">Ordenar por</legend>
      {(Object.keys(SORT_OPTION) as SortKey[]).map((key) => (
        <label key={key} className="block cursor-pointer">
          <input
            type="radio"
            name={name}
            className="peer sr-only"
            checked={value === key}
            onChange={() => onChange(key)}
          />
          <span className="flex h-11 items-center px-6 text-body-sm text-text-primary transition-colors duration-(--duration-fast) peer-checked:bg-action-soft peer-checked:font-bold peer-checked:text-action-soft-text peer-focus-visible:outline-2 peer-focus-visible:-outline-offset-2 peer-focus-visible:outline-focus-ring peer-focus-visible:outline-solid hover:bg-bg-subtle motion-reduce:transition-none">
            {SORT_OPTION[key]}
          </span>
        </label>
      ))}
    </fieldset>
  );
}
