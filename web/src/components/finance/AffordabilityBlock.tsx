// "¿Me alcanza?" under the price card of a project (SPEC 11d §6): with the data saved in this
// browser it answers at once; without it, it asks for the income and the savings here. The
// answer is always for the unit type of the "desde", and says with which rate.
import { useState } from "react";

import { type ProjectFit, projectFit } from "@/lib/affordability";
import { maxPaymentToIncome } from "@/lib/finance";
import { formatThousands, parseWhole, readIncome, readSavings } from "@/lib/finance-fields";
import { rateEaPct, type StoredFinances } from "@/lib/finances-store";
import { formatCop, formatDate, formatMillions, formatShare } from "@/lib/format";
import type { ReferenceRate } from "@/lib/reference-rate";
import Assumptions from "./Assumptions";
import RateNote from "./RateNote";
import TextField from "./TextField";
import { useFinances } from "./useFinances";

const linkClass =
  "cursor-pointer text-body-sm font-bold text-action-soft-text underline underline-offset-4 hover:text-action";

type Props = {
  /** The unit type of the "desde", its price and its day. */
  priceCop: number;
  unitName: string;
  observedOn: string;
  reference: ReferenceRate;
};

type Money = { income: string; savings: string };
const NO_MONEY: Money = { income: "", savings: "" };

function moneyOf({ incomeCop, savingsCop }: StoredFinances): Money {
  return {
    income: incomeCop === null ? "" : formatThousands(incomeCop),
    savings: savingsCop === null ? "" : formatThousands(savingsCop),
  };
}

export default function AffordabilityBlock({ priceCop, unitName, observedOn, reference }: Props) {
  const [texts, setTexts] = useState<Money>(NO_MONEY);
  // The fields show until both figures are known; then they fold behind "Cambiar".
  const [editing, setEditing] = useState(true);
  const [formKey, setFormKey] = useState(0);
  const { finances, memoryOnly, update, forget } = useFinances((saved) => {
    setTexts(moneyOf(saved));
    setEditing(saved.incomeCop === null || saved.savingsCop === null);
  });

  const income = readIncome(texts.income);
  const savings = readSavings(texts.savings);
  const rate = rateEaPct(finances, reference);
  const fit =
    income.value !== null && savings.value !== null
      ? projectFit(
          {
            incomeCop: income.value,
            savingsCop: savings.value,
            rateEaPct: rate,
            years: finances.years,
            downPaymentPct: finances.downPaymentPct,
            monthsToDelivery: finances.monthsToDelivery,
          },
          priceCop,
        )
      : null;

  function type(name: keyof Money, text: string) {
    setTexts((current) => ({ ...current, [name]: text }));
    const field = name === "income" ? readIncome(text) : readSavings(text);
    // A cleared field is forgotten; a wrong one keeps what was there.
    if (field.error === null || text.trim() === "") {
      update(name === "income" ? { incomeCop: field.value } : { savingsCop: field.value });
    }
  }

  function group(name: keyof Money) {
    const value = parseWhole(texts[name]);
    if (typeof value === "number") {
      setTexts((current) => ({ ...current, [name]: formatThousands(value) }));
    }
  }

  function forgetAll() {
    forget();
    setTexts(NO_MONEY);
    setEditing(true);
    setFormKey((key) => key + 1);
  }

  return (
    <section
      aria-labelledby="me-alcanza"
      className="flex flex-col gap-4 rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface p-6"
    >
      <h2 id="me-alcanza" className="text-title font-bold text-text-primary">
        ¿Me alcanza?
      </h2>
      <noscript>
        <p className="text-body-sm font-bold text-text-primary">
          Esta cuenta necesita JavaScript.
        </p>
      </noscript>

      {editing ? (
        <div key={formKey} className="flex flex-col gap-4">
          <TextField
            label="Ingreso mensual del hogar"
            inputMode="numeric"
            prefix="$"
            placeholder="Ej. 8.000.000"
            value={texts.income}
            error={income.error}
            onBlur={() => group("income")}
            onValue={(text) => type("income", text)}
          />
          <TextField
            label="Ahorro para la cuota inicial"
            inputMode="numeric"
            prefix="$"
            placeholder="Ej. 60.000.000"
            value={texts.savings}
            error={savings.error}
            onBlur={() => group("savings")}
            onValue={(text) => type("savings", text)}
          />
        </div>
      ) : (
        <p className="text-body-sm text-text-secondary">
          Con un ingreso de {formatCop(income.value ?? 0)} al mes y {formatCop(savings.value ?? 0)}{" "}
          de ahorro.{" "}
          <button type="button" onClick={() => setEditing(true)} className={linkClass}>
            Cambiar
          </button>
        </p>
      )}

      <div role="status" className="flex flex-col gap-2">
        {fit ? (
          <Verdict fit={fit} />
        ) : (
          <p className="text-body-sm text-text-secondary">
            Escribe tu ingreso y tu ahorro para saber si te alcanza.
          </p>
        )}
      </div>

      <p className="text-body-sm text-text-secondary">
        Para {unitName}, desde {formatMillions(priceCop)}, observado el {formatDate(observedOn)}.
        A {finances.years} años, con cuota inicial del {formatShare(finances.downPaymentPct)}.
      </p>
      <RateNote
        reference={reference}
        housing={finances.housing}
        custom={finances.rate.source === "custom" ? finances.rate.eaPct : null}
        onUseReference={() => update({ rate: { source: "reference" } })}
      />
      <a href="/calculadora/" className={linkClass}>
        Cambiar tasa, plazo o meses en la calculadora
      </a>

      <div className="flex flex-col items-start gap-2 border-t-(length:--border-width-default) border-border pt-4">
        <p className="text-body-sm text-text-muted">
          {memoryOnly
            ? "Este navegador no deja guardar datos: se pierden al salir de la página."
            : "Tus datos se guardan solo en este navegador."}
        </p>
        <button type="button" onClick={forgetAll} className={linkClass}>
          Olvidar mis datos
        </button>
      </div>
      <Assumptions />
    </section>
  );
}

function Verdict({ fit }: { fit: ProjectFit }) {
  const { mortgage, installment } = fit;
  const payment = formatCop(mortgage.monthlyPaymentCop);
  const share = formatShare(fit.paymentSharePct);
  if (fit.fits) {
    return (
      <>
        <p className="text-h3 text-text-price">Te alcanza</p>
        <p className="text-body-sm text-text-secondary">
          La cuota sería {payment} al mes, el {share} de tu ingreso, y tu ahorro cubre la cuota
          inicial de {formatCop(mortgage.downPaymentCop)}.
        </p>
      </>
    );
  }
  return (
    <>
      {fit.missingCop > 0 && (
        <>
          <p className="text-title font-bold text-text-primary">
            Te faltan {formatCop(fit.missingCop)} de cuota inicial
          </p>
          <p className="text-body-sm text-text-secondary">
            {installment
              ? `Serían ${formatCop(installment.cop)} al mes durante ${
                  installment.months === 1 ? "el mes" : `los ${installment.months} meses`
                } de obra (${formatShare(installment.incomeSharePct)} de tu ingreso).`
              : "Con los meses hasta la entrega, en la calculadora, verás cuánto sería al mes."}
          </p>
        </>
      )}
      {fit.overIncome && (
        <p className="text-body font-bold text-text-primary">
          La cuota sería {payment}, el {share} de tu ingreso; el máximo es{" "}
          {formatShare(maxPaymentToIncome * 100)}.
        </p>
      )}
    </>
  );
}
