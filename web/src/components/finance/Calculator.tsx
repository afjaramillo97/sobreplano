// "¿Qué puedo comprar?" (SPEC 11d §6): the form at the left, the result at the right (below on a
// phone), recomputed as the person types. The maths is lib/calculator.ts; the data is saved in
// this browser only, and the only thing that leaves the page is precio_max, in the search link.
import { cx } from "class-variance-authority";
import { useId, useState } from "react";

import { buttonVariants } from "@/components/ui/button-variants";
import { calculate, type CalculatorResult } from "@/lib/calculator";
import { maxPaymentToIncome, maxYears, minYears } from "@/lib/finance";
import {
  type Field,
  formatDecimalInput,
  formatThousands,
  parseWhole,
  readDownPaymentPct,
  readIncome,
  readMonths,
  readRate,
  readSavings,
} from "@/lib/finance-fields";
import { EMPTY_FINANCES, type Housing, rateEaPct, type StoredFinances } from "@/lib/finances-store";
import {
  formatCop,
  formatCount,
  formatDate,
  formatMillions,
  formatRate,
  formatShare,
} from "@/lib/format";
import type { ReferenceRate } from "@/lib/reference-rate";
import type { SearchItem } from "@/lib/search";
import Assumptions from "./Assumptions";
import RateNote from "./RateNote";
import TextField from "./TextField";
import { useFinances } from "./useFinances";

const MAX_SHARE_PCT = maxPaymentToIncome * 100;
// Not a rule of the banks nor of the law: the guide the site gives (SPEC 11d §6).
const COMFORTABLE_SHARE_PCT = 30;
const TERMS = Array.from({ length: maxYears - minYears + 1 }, (_, i) => minYears + i);

const cardClass =
  "flex flex-col gap-6 rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface p-6";
const linkClass = "font-bold text-action-soft-text underline underline-offset-4 hover:text-action";

/** What the inputs hold, as typed. A null rate shows the reference one. */
type Texts = {
  income: string;
  savings: string;
  months: string;
  rate: string | null;
  downPaymentPct: string;
};

function textsOf(finances: StoredFinances): Texts {
  const money = (value: number | null) => (value === null ? "" : formatThousands(value));
  return {
    income: money(finances.incomeCop),
    savings: money(finances.savingsCop),
    months: finances.monthsToDelivery === null ? "" : String(finances.monthsToDelivery),
    rate: finances.rate.source === "custom" ? formatDecimalInput(finances.rate.eaPct) : null,
    downPaymentPct: formatDecimalInput(finances.downPaymentPct),
  };
}

type Props = { items: SearchItem[]; reference: ReferenceRate };

export default function Calculator({ items, reference }: Props) {
  const [texts, setTexts] = useState<Texts>(() => textsOf(EMPTY_FINANCES));
  const { finances, memoryOnly, update, forget } = useFinances((saved) => setTexts(textsOf(saved)));
  // Bumped by "Olvidar mis datos", so the fields start over without their old errors.
  const [formKey, setFormKey] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const referenceRate = rateEaPct({ ...finances, rate: { source: "reference" } }, reference);
  const rateText = texts.rate ?? formatDecimalInput(referenceRate);

  const income = readIncome(texts.income);
  const savings = readSavings(texts.savings);
  const months = readMonths(texts.months);
  const rate = readRate(rateText);
  const downPaymentPct = readDownPaymentPct(texts.downPaymentPct);
  const valid = [income, savings, months, rate, downPaymentPct].every((f) => f.error === null);
  // Only the money fields still empty: the person has nothing to fix, just to fill in.
  const onlyMissing =
    [months, rate, downPaymentPct].every((f) => f.error === null) &&
    [texts.income, texts.savings].every((text, i) =>
      text.trim() === "" ? true : (i === 0 ? income : savings).error === null,
    );
  // A collapsed section must not hide the reason there is no result.
  const settingsError = rate.error !== null || downPaymentPct.error !== null;

  const result =
    valid && income.value !== null && savings.value !== null
      ? calculate(
          {
            incomeCop: income.value,
            savingsCop: savings.value,
            rateEaPct: rate.value!,
            years: finances.years,
            downPaymentPct: downPaymentPct.value!,
            monthsToDelivery: months.value,
          },
          items,
        )
      : null;

  /** The input shows what was typed; only a value that reads right is kept. */
  function type(name: keyof Texts, text: string, field: Field, patch: Partial<StoredFinances>) {
    setTexts((current) => ({ ...current, [name]: text }));
    // A cleared field is forgotten; a half-typed or wrong one keeps what was there.
    if (field.error === null || text.trim() === "") update(patch);
  }

  /** On leaving a money field, its thousands get their dots. */
  function group(name: "income" | "savings") {
    const value = parseWhole(texts[name]);
    if (typeof value === "number") {
      setTexts((current) => ({ ...current, [name]: formatThousands(value) }));
    }
  }

  function backToReference() {
    setTexts((current) => ({ ...current, rate: null }));
    update({ rate: { source: "reference" } });
  }

  function forgetAll() {
    forget();
    setTexts(textsOf(EMPTY_FINANCES));
    setFormKey((key) => key + 1);
  }

  return (
    <div className="page py-8 lg:py-12">
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,480px)]">
        <div key={formKey} className="flex min-w-0 flex-col gap-6">
          <section aria-labelledby="hogar" className={cardClass}>
            <h2 id="hogar" className="text-title font-bold text-text-primary">
              Tu hogar
            </h2>
            <TextField
              label="Ingreso mensual del hogar"
              inputMode="numeric"
              prefix="$"
              placeholder="Ej. 8.000.000"
              value={texts.income}
              error={income.error}
              onBlur={() => group("income")}
              onValue={(text) => {
                const field = readIncome(text);
                type("income", text, field, { incomeCop: field.value });
              }}
            />
            <TextField
              label="Ahorro para la cuota inicial"
              inputMode="numeric"
              prefix="$"
              placeholder="Ej. 60.000.000"
              hint="Lo que ya tienes para abonar, cesantías incluidas."
              value={texts.savings}
              error={savings.error}
              onBlur={() => group("savings")}
              onValue={(text) => {
                const field = readSavings(text);
                type("savings", text, field, { savingsCop: field.value });
              }}
            />
          </section>

          <section aria-labelledby="vivienda" className={cardClass}>
            <h2 id="vivienda" className="text-title font-bold text-text-primary">
              La vivienda
            </h2>
            <HousingChoice value={finances.housing} onChange={(housing) => update({ housing })} />
            <TextField
              label="Meses hasta la entrega (opcional)"
              inputMode="numeric"
              placeholder="Ej. 24"
              hint="Para saber cuánto pagarías durante la obra."
              value={texts.months}
              error={months.error}
              onValue={(text) => {
                const field = readMonths(text);
                type("months", text, field, { monthsToDelivery: field.value });
              }}
            />

            <details
              open={settingsOpen || settingsError}
              onToggle={(event) => setSettingsOpen(event.currentTarget.open)}
              className="border-t-(length:--border-width-default) border-border pt-4"
            >
              <summary className="cursor-pointer text-label text-action-soft-text">
                Ajustes del crédito
              </summary>
              <div className="mt-4 flex flex-col gap-6">
                <TextField
                  label="Tasa de interés (efectiva anual)"
                  inputMode="decimal"
                  suffix="% E.A."
                  value={rateText}
                  error={rate.error}
                  onValue={(text) => {
                    const field = readRate(text);
                    setTexts((current) => ({ ...current, rate: text }));
                    if (field.value !== null) {
                      update({ rate: { source: "custom", eaPct: field.value } });
                    }
                  }}
                />
                <TermSelect value={finances.years} onChange={(years) => update({ years })} />
                <TextField
                  label="Cuota inicial"
                  inputMode="decimal"
                  suffix="%"
                  value={texts.downPaymentPct}
                  error={downPaymentPct.error}
                  onValue={(text) => {
                    const field = readDownPaymentPct(text);
                    type("downPaymentPct", text, field, {
                      downPaymentPct: field.value ?? EMPTY_FINANCES.downPaymentPct,
                    });
                  }}
                />
              </div>
            </details>

            <RateNote
              reference={reference}
              housing={finances.housing}
              custom={finances.rate.source === "custom" ? finances.rate.eaPct : null}
              onUseReference={backToReference}
            />
          </section>

          <div className="flex flex-col items-start gap-3">
            <p className="text-body-sm text-text-secondary">
              {memoryOnly
                ? "Este navegador no deja guardar datos: se pierden al salir de la página. No salen de tu dispositivo."
                : "Tu ingreso y tu ahorro se guardan solo en este navegador. No salen de tu dispositivo."}
            </p>
            <button
              type="button"
              onClick={forgetAll}
              className={cx(buttonVariants({ variant: "outline", size: "sm" }), "cursor-pointer")}
            >
              Olvidar mis datos
            </button>
          </div>
        </div>

        <Result
          result={result}
          years={finances.years}
          rate={rate.value}
          downPaymentPct={downPaymentPct.value}
          incomplete={onlyMissing ? "missing" : "invalid"}
        />
      </div>
      <Assumptions className="mt-8" />
    </div>
  );
}

function HousingChoice({ value, onChange }: { value: Housing; onChange: (v: Housing) => void }) {
  const name = useId();
  const options: [Housing, string][] = [
    ["no-vis", "No VIS"],
    ["vis", "VIS"],
  ];
  return (
    <fieldset>
      <legend className="text-label text-text-primary">Tipo de vivienda</legend>
      <div className="mt-2 flex flex-wrap gap-2">
        {options.map(([housing, label]) => (
          <label key={housing} className="cursor-pointer">
            <input
              type="radio"
              name={name}
              className="peer sr-only"
              checked={value === housing}
              onChange={() => onChange(housing)}
            />
            <span className="flex h-(--size-control-md) items-center rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface px-6 text-body text-text-secondary peer-checked:border-action peer-checked:bg-action-soft peer-checked:font-bold peer-checked:text-text-primary peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-solid peer-focus-visible:outline-ring">
              {label}
            </span>
          </label>
        ))}
      </div>
      <p className="mt-2 text-body-sm text-text-muted">
        VIS es la vivienda de interés social. La constructora te dice si el proyecto lo es.
      </p>
    </fieldset>
  );
}

function TermSelect({ value, onChange }: { value: number; onChange: (years: number) => void }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-label text-text-primary">
        Plazo del crédito
      </label>
      {/* The shape of ui/select with the chevron drawn in CSS: its icon would bring every
          icon of the site into the island. */}
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          className="h-(--size-control-md) w-full cursor-pointer appearance-none rounded-md border-(length:--border-width-strong) border-input bg-muted py-2 pr-12 pl-4 text-body text-foreground outline-hidden focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring"
        >
          {TERMS.map((years) => (
            <option key={years} value={years}>
              {years} años
            </option>
          ))}
        </select>
        <span
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 right-5 size-2 -translate-y-3/4 rotate-45 border-r-2 border-b-2 border-primary"
        />
      </div>
    </div>
  );
}

type ResultProps = {
  result: CalculatorResult | null;
  years: number;
  rate: number | null;
  downPaymentPct: number | null;
  incomplete: "missing" | "invalid";
};

/** The figures of the kit's Rental Portfolio: one big number, then the rest in a grid. */
function Result({ result, years, rate, downPaymentPct, incomplete }: ResultProps) {
  return (
    <section aria-labelledby="resultado" className={cardClass}>
      <h2 id="resultado" className="text-title font-bold text-text-primary">
        Tu resultado
      </h2>
      <div role="status" className="flex flex-col gap-6">
        {result ? (
          <Figures
            result={result}
            years={years}
            rate={rate!}
            downPaymentPct={downPaymentPct!}
          />
        ) : (
          <p className="text-body text-text-secondary">
            {incomplete === "invalid"
              ? "Revisa los campos marcados para ver el resultado."
              : "Escribe tu ingreso mensual y tu ahorro para ver hasta cuánto puedes comprar."}
          </p>
        )}
      </div>
      {result && <Projects result={result} />}
    </section>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    // The value shows above its label; in the DOM the term still comes first.
    <div className="flex flex-col-reverse justify-end gap-1">
      <dt className="text-body-sm text-text-muted">{label}</dt>
      <dd className="text-title font-bold text-text-primary tabular-nums">{value}</dd>
    </div>
  );
}

function limitText(result: CalculatorResult, downPaymentPct: number): string {
  const { limitedBy, maxPriceCop, maxMonthlyPaymentCop } = result.affordability;
  const share = formatShare(downPaymentPct);
  if (limitedBy === "income") {
    return `Lo limita tu ingreso: la cuota no puede pasar del ${formatShare(MAX_SHARE_PCT)}, ${formatCop(maxMonthlyPaymentCop)} al mes.`;
  }
  return maxPriceCop > 0
    ? `Lo limita tu ahorro: alcanza para la cuota inicial del ${share} de este precio.`
    : `Lo limita tu ahorro: para comprar necesitas la cuota inicial, el ${share} del precio.`;
}

function Figures({
  result,
  years,
  rate,
  downPaymentPct,
}: {
  result: CalculatorResult;
  years: number;
  rate: number;
  downPaymentPct: number;
}) {
  const { affordability, mortgage, paymentSharePct, construction } = result;
  return (
    <>
      <div className="flex flex-col gap-1">
        <p className="text-body text-text-muted">Puedes comprar hasta</p>
        <p className="text-price-lg text-text-price">{formatCop(affordability.maxPriceCop)}</p>
        <p className="text-body-sm text-text-secondary">{limitText(result, downPaymentPct)}</p>
      </div>

      {mortgage && paymentSharePct !== null && (
        <>
          <dl className="grid grid-cols-1 gap-4 border-y-(length:--border-width-default) border-border py-4 sm:grid-cols-2">
            <Figure label="Cuota mensual" value={formatCop(mortgage.monthlyPaymentCop)} />
            <Figure label="Cuota inicial" value={formatCop(affordability.downPaymentCop)} />
            <Figure label="Préstamo" value={formatCop(affordability.loanCop)} />
            <Figure label={`Tasa, a ${years} años`} value={`${formatRate(rate)} E.A.`} />
          </dl>
          <ShareBar sharePct={paymentSharePct} />
        </>
      )}

      {construction && (
        <div className="flex flex-col gap-1">
          <p className="text-label text-text-primary">Durante la obra</p>
          <p className="text-body-sm text-text-secondary">
            {construction.kind === "covered"
              ? "Tu ahorro cubre la cuota inicial: no tendrías cuotas durante la obra."
              : `Si pagas ${formatCop(construction.installmentCop)} al mes durante ${
                  construction.months === 1 ? "el mes" : `los ${construction.months} meses`
                } de obra (${formatShare(construction.incomeSharePct)} de tu ingreso), podrías llegar a ${formatCop(construction.priceCop)}.`}
          </p>
        </div>
      )}
    </>
  );
}

/** The payment against the income, on a scale to 50 % with the two marks of SPEC 11d §6. */
function ShareBar({ sharePct }: { sharePct: number }) {
  const scale = 50;
  const width = `${(Math.min(sharePct, scale) / scale) * 100}%`;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-label text-text-primary">
        La cuota es el {formatShare(sharePct)} de tu ingreso
      </p>
      <div aria-hidden="true" className="relative h-2 rounded-full bg-action-soft">
        <div className="h-2 rounded-full bg-action" style={{ width }} />
        {/* 30 and 40 over a scale of 50. */}
        <span className="absolute -top-1 left-[60%] h-4 w-0.5 bg-action-dark" />
        <span className="absolute -top-1 left-[80%] h-4 w-0.5 bg-action-dark" />
      </div>
      <ul className="flex flex-col gap-1 text-body-sm text-text-secondary">
        <li>
          Hasta {formatShare(COMFORTABLE_SHARE_PCT)} de tu ingreso: holgado (es una guía, no una
          regla del banco).
        </li>
        <li>Hasta {formatShare(MAX_SHARE_PCT)}: el máximo que permite la ley.</li>
      </ul>
    </div>
  );
}

function Projects({ result }: { result: CalculatorResult }) {
  const { matches, cheapest, affordability } = result;
  const price = affordability.maxPriceCop;
  if (matches > 0) {
    return (
      <a
        href={`/proyectos/?precio_max=${price}`}
        // No size variant: this label wraps on phones, so the height is a minimum.
        className={cx(
          buttonVariants({ size: null }),
          "min-h-(--size-control-lg) w-full px-8 py-4 text-center whitespace-normal!",
        )}
      >
        Ver {formatCount(matches, "proyecto", "proyectos")} hasta {formatMillions(price)}
      </a>
    );
  }
  return (
    <div className="flex flex-col gap-4 border-t-(length:--border-width-default) border-border pt-4">
      <p className="text-body font-bold text-text-primary">
        Ningún proyecto del catálogo llega a ese precio.
        {cheapest.length > 0 && " Los más baratos:"}
      </p>
      <ul className="flex flex-col gap-4">
        {cheapest.map((project) => (
          <li key={project.slug} className="flex flex-col gap-1 text-body-sm">
            <a href={`/proyectos/${project.slug}/`} className={linkClass}>
              {project.name}
            </a>
            <span className="text-text-secondary">
              Desde {formatMillions(project.priceCop)} · {project.unitName}
              {project.observedOn && `, observado el ${formatDate(project.observedOn)}`}
            </span>
            <span className="font-bold text-text-primary">
              Te faltarían {formatMillions(project.missingCop)}
            </span>
          </li>
        ))}
      </ul>
      {cheapest.length > 0 && (
        <p className="text-body-sm text-text-muted">
          Precios desde publicados por las constructoras. Pueden no incluir parqueadero, cuarto
          útil, acabados ni gastos de escrituración.
        </p>
      )}
      <a href="/proyectos/" className={cx(buttonVariants({ variant: "soft" }), "w-full")}>
        Ver todos los proyectos
      </a>
    </div>
  );
}
