// The empty state, after the kit's Message - Empty State: a title, one line on what the advisor
// does, and the suggested questions as buttons (they send at once). With a project in context
// the title names it and the questions are about it.
import { Button } from "@/components/ui/button";
import { AdvisorAvatar } from "./Bubble";

type Props = {
  projectName: string | null;
  questions: readonly string[];
  onPick: (question: string) => void;
  disabled: boolean;
};

export function Suggestions({ projectName, questions, onPick, disabled }: Props) {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center gap-6 py-4 text-center">
      <AdvisorAvatar className="flex" />
      <div className="flex flex-col gap-2">
        <h2 className="text-h3 text-text-heading-alt">
          {projectName ? `Pregunta sobre ${projectName}` : "Pregúntale al asesor"}
        </h2>
        <p className="text-body text-text-secondary">
          Responde con los precios y la historia de los proyectos que seguimos, y simula tu
          crédito o tu cuota inicial. Prueba con una de estas preguntas:
        </p>
      </div>
      <ul className="flex w-full flex-col gap-3" aria-label="Preguntas sugeridas">
        {questions.map((question) => (
          <li key={question}>
            <Button
              type="button"
              variant="outline"
              disabled={disabled}
              onClick={() => onPick(question)}
              className="h-auto min-h-(--size-control-md) w-full justify-start py-3 text-left whitespace-normal"
            >
              {question}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
