// "Tus conversaciones", after the kit's Message inbox: the search box and the 48 px "+" button
// on top, then one row per conversation (the selected one on the lavender fill), and at the
// bottom what the browser keeps and how to delete it (SPEC 11c §4).
import { useId, useState } from "react";

import Icon from "@/components/Icon";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { STORAGE_TEXTS } from "@/lib/advisor/labels";
import type { StoredConversation } from "@/lib/advisor/store";
import { conversationPreview, filterConversations, lastActivity } from "@/lib/advisor/view";
import type { SearchItem } from "@/lib/search";
import { cn } from "@/lib/utils";

type Props = {
  conversations: readonly StoredConversation[];
  activeId: string | null;
  catalog: ReadonlyMap<string, SearchItem>;
  now: Date;
  onSelect: (id: string) => void;
  onNew: () => void;
  keepHistory: boolean;
  onKeepHistory: (keep: boolean) => void;
  onClear: () => void;
  /** False when the browser does not let the page save. */
  persistent: boolean;
  /** False inside the phone's sheet, whose own title already says it. */
  heading?: boolean;
};

export function ConversationList({
  conversations,
  activeId,
  catalog,
  now,
  onSelect,
  onNew,
  keepHistory,
  onKeepHistory,
  onClear,
  persistent,
  heading = true,
}: Props) {
  const [query, setQuery] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const searchId = useId();
  const keepId = useId();
  const shown = filterConversations(conversations, query);

  return (
    <div className="flex h-full min-h-0 flex-col gap-6">
      <div className="flex items-end gap-4">
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          {heading && <h2 className="text-title text-text-heading-alt">Tus conversaciones</h2>}
          <label htmlFor={searchId} className="sr-only">
            Buscar en tus conversaciones
          </label>
          <div className="flex h-(--size-control-md) items-center gap-2 rounded-md border-(length:--border-width-default) border-border-input bg-bg-subtle px-4 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-solid focus-within:outline-ring">
            <Icon name="search-outline" size={20} className="shrink-0 text-text-muted" />
            <input
              id={searchId}
              type="search"
              value={query}
              placeholder="Buscar…"
              onChange={(event) => setQuery(event.target.value)}
              className="min-w-0 flex-1 bg-transparent text-body-sm text-text-primary outline-hidden placeholder:text-text-muted"
            />
          </div>
        </div>
        <Button type="button" size="icon" onClick={onNew} aria-label="Nueva consulta" title="Nueva consulta">
          <Icon name="add-outline" size={24} />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto rounded-lg">
        {conversations.length === 0 ? (
          <p className="px-4 py-2 text-body-sm text-text-muted">
            Todavía no tienes conversaciones en este navegador.
          </p>
        ) : shown.length === 0 ? (
          <p className="px-4 py-2 text-body-sm text-text-muted">
            Ninguna conversación tiene «{query.trim()}».
          </p>
        ) : (
          <ul className="flex flex-col">
            {shown.map((conversation) => {
              const project = conversation.projectSlug ? catalog.get(conversation.projectSlug) : null;
              const active = conversation.id === activeId;
              return (
                <li key={conversation.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(conversation.id)}
                    aria-current={active ? "true" : undefined}
                    className={cn(
                      "flex w-full flex-col gap-1 border-b-(length:--border-width-default) border-border p-4 text-left outline-hidden transition-colors duration-(--duration-fast) hover:bg-bg-subtle focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring motion-reduce:transition-none",
                      active && "bg-bg-subtle",
                    )}
                  >
                    <span className="flex items-baseline justify-between gap-3">
                      <span className="min-w-0 truncate text-body font-bold text-text-primary">
                        {conversation.title}
                      </span>
                      <span className="shrink-0 text-body-sm text-text-muted">
                        {lastActivity(conversation.updatedAt, now)}
                      </span>
                    </span>
                    <span className="line-clamp-2 text-body-sm text-text-secondary">
                      {conversationPreview(conversation)}
                    </span>
                    {(project || conversation.closed) && (
                      <span className="mt-2 flex flex-wrap gap-2">
                        {project && (
                          <span className="inline-flex h-(--size-chip) items-center rounded-full border-(length:--border-width-default) border-border-input px-3 text-caption font-bold text-action-soft-text uppercase">
                            {project.name}
                          </span>
                        )}
                        {conversation.closed && (
                          <span className="inline-flex h-(--size-chip) items-center rounded-full bg-bg-selected px-3 text-caption font-bold text-text-secondary uppercase">
                            Cerrada
                          </span>
                        )}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="flex flex-col gap-3 border-t-(length:--border-width-default) border-border pt-4">
        {persistent ? (
          <>
            <div className="flex items-center justify-between gap-3">
              <label htmlFor={keepId} className="text-body-sm text-text-primary">
                {STORAGE_TEXTS.keepToggle}
              </label>
              <Switch id={keepId} checked={keepHistory} onCheckedChange={onKeepHistory} />
            </div>
            <p className="text-caption text-text-muted">
              {keepHistory ? STORAGE_TEXTS.keptHint : STORAGE_TEXTS.autoDeleteHint}
            </p>
          </>
        ) : (
          <p className="text-caption text-text-muted">{STORAGE_TEXTS.memoryOnly}</p>
        )}
        {conversations.length > 0 &&
          (confirmClear ? (
            <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Confirmar borrado">
              <p className="w-full text-body-sm text-text-primary">
                ¿Borrar todas tus conversaciones? {STORAGE_TEXTS.clearHint}
              </p>
              <Button
                type="button"
                size="sm"
                variant="dark"
                onClick={() => {
                  setConfirmClear(false);
                  onClear();
                }}
              >
                Sí, borrar
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => setConfirmClear(false)}>
                Cancelar
              </Button>
            </div>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="self-start px-0 text-action-soft-text hover:bg-transparent hover:text-action"
              onClick={() => setConfirmClear(true)}
            >
              {STORAGE_TEXTS.clearButton}
            </Button>
          ))}
      </div>
    </div>
  );
}
