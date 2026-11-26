// What every figure of the finance screens leaves out (SPEC 11d §6).
//
// The finance islands join classes with cx, not cn: tailwind-merge alone would take them past
// their JavaScript budget, so no class here overrides another.
import { cx } from "class-variance-authority";

export default function Assumptions({ className }: { className?: string }) {
  return (
    <p className={cx("text-body-sm text-text-muted", className)}>
      Los cálculos suponen una tasa fija en pesos y no incluyen seguros ni gastos de
      escrituración y registro. No son una oferta ni una preaprobación de un banco.
    </p>
  );
}
