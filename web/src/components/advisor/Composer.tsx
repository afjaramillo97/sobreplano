// The kit's message box: a white 1.5 px bordered box, the text on top and, at the bottom, the
// character count on the left and the Send button on the right. Enter sends, Shift+Enter breaks
// the line. The notice of §6 sits under it, always.
import type { RefObject } from "react";

import Icon from "@/components/Icon";
import { Button } from "@/components/ui/button";
import { NOTICE } from "@/lib/advisor/labels";

export const MAX_MESSAGE_LENGTH = 1000;

const count = new Intl.NumberFormat("es-CO");

type Props = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  /** A reply is running or a limit is counting down: nothing can be sent. */
  disabled: boolean;
  /** "Te quedan 4 preguntas hoy", when few are left. */
  remaining: string | null;
  inputRef: RefObject<HTMLTextAreaElement | null>;
};

export function Composer({ value, onChange, onSubmit, disabled, remaining, inputRef }: Props) {
  const empty = value.trim() === "";
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (!disabled && !empty) onSubmit();
      }}
    >
      <div className="flex flex-col gap-3 rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface p-4 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-solid focus-within:outline-ring">
        <label htmlFor="pregunta" className="sr-only">
          Tu pregunta para el asesor
        </label>
        <textarea
          id="pregunta"
          ref={inputRef}
          value={value}
          rows={1}
          maxLength={MAX_MESSAGE_LENGTH}
          placeholder="Escribe tu pregunta…"
          aria-describedby="pregunta-conteo pregunta-aviso"
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            // isComposing: Enter also confirms an accent or a word in an input method.
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              if (!disabled && !empty) onSubmit();
            }
          }}
          // field-sizing: the box grows with the text, up to 160 px, then scrolls.
          className="field-sizing-content max-h-40 min-h-6 w-full resize-none bg-transparent text-body text-text-primary outline-hidden placeholder:text-text-muted"
        />
        <div className="flex items-center justify-between gap-4">
          <p id="pregunta-conteo" className="text-body-sm text-text-muted tabular-nums">
            {count.format(value.length)}/{count.format(MAX_MESSAGE_LENGTH)}
            <span className="sr-only"> caracteres</span>
          </p>
          <div className="flex items-center gap-4">
            {remaining && (
              <p className="text-body-sm font-bold text-action-soft-text" data-testid="remaining">
                {remaining}
              </p>
            )}
            <Button type="submit" size="sm" disabled={disabled || empty}>
              Enviar
              <Icon name="send-bold" size={16} />
            </Button>
          </div>
        </div>
      </div>
      <p id="pregunta-aviso" className="text-caption text-text-muted">
        {NOTICE}{" "}
        <a
          href="/terminos/"
          className="font-bold text-action-soft-text underline underline-offset-2 hover:text-action"
        >
          Términos de uso
        </a>
      </p>
    </form>
  );
}
