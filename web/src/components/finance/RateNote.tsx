// Where the rate of a result comes from (SPEC 11d §3): the week, the source and its license are
// always in view, and a person's own rate offers the way back to the reference one.
import { formatDate, formatRate } from "@/lib/format";
import type { Housing } from "@/lib/finances-store";
import type { ReferenceRate } from "@/lib/reference-rate";

const HOUSING_NAMES: Record<Housing, string> = { vis: "VIS", "no-vis": "No VIS" };
const linkClass = "font-bold text-action-soft-text underline underline-offset-4 hover:text-action";

type Props = {
  reference: ReferenceRate;
  housing: Housing;
  /** The person's own rate, or null while the reference one applies. */
  custom: number | null;
  onUseReference?: () => void;
};

export default function RateNote({ reference, housing, custom, onUseReference }: Props) {
  const { rateEaPct } = housing === "vis" ? reference.vis : reference.noVis;
  const name = HOUSING_NAMES[housing];
  return (
    <div className="flex flex-col items-start gap-2 text-body-sm text-text-secondary">
      {custom !== null && (
        <p className="font-bold text-text-primary">
          Estás usando tu tasa: {formatRate(custom)} E.A.
        </p>
      )}
      <p>
        {custom === null
          ? `Tasa promedio de los bancos para vivienda ${name}`
          : `La de referencia para vivienda ${name}`}
        : {formatRate(rateEaPct)} E.A., semana del {formatDate(reference.cutOff)}. Fuente:{" "}
        <a href={reference.sourceUrl} target="_blank" rel="noopener" className={linkClass}>
          Superfinanciera (datos abiertos)
          <span className="sr-only"> (se abre en otra pestaña)</span>
        </a>
        , licencia CC BY-SA 4.0.
      </p>
      <p>Es un promedio de lo que prestaron los bancos esa semana. Tu banco puede darte otra.</p>
      {custom !== null && onUseReference && (
        <button
          type="button"
          onClick={onUseReference}
          className={`cursor-pointer ${linkClass}`}
        >
          Usar la tasa de referencia
        </button>
      )}
    </div>
  );
}
