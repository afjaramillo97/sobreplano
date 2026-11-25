// The advisor page (SPEC 11c), after the kit's Message screen: the conversations on the left,
// the thread in the middle and the project in context on the right. Below 1024 px the thread
// takes the screen and the other two open as sheets (Message and Message - Details, mobile).
//
// One island (client:load). Its server render is the empty state; in the browser it reads the
// stored conversations and the URL (?c=thread, ?proyecto=slug), sends one question at a time
// and turns every failure into the text and action of §6.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import Icon from "@/components/Icon";
import { Button, buttonVariants } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { errorView, remainingLabel } from "@/lib/advisor/labels";
import { linkPolicy } from "@/lib/advisor/links";
import {
  type AdvisorStore,
  appendMessage,
  browserStorage,
  clearStore,
  closeConversation,
  EMPTY_STORE,
  findConversation,
  newConversation,
  readStore,
  setKeepHistory,
  type StoredConversation,
  type StoredMessage,
  upsertConversation,
  writeStore,
} from "@/lib/advisor/store";
import { STORAGE_TEXTS } from "@/lib/advisor/labels";
import { AdvisorClient, type AdvisorError } from "@/lib/advisor/stream";
import { suggestionsFor } from "@/lib/advisor/suggestions";
import { conversationProjects, knownProjects, unansweredQuestion } from "@/lib/advisor/view";
import type { SearchItem } from "@/lib/search";
import { Composer } from "./Composer";
import { ConversationList } from "./ConversationList";
import { ProjectPanel } from "./ProjectPanel";
import type { StepView } from "./StepTrace";
import { Suggestions } from "./Suggestions";
import { Thread } from "./Thread";

type Props = {
  /** The catalog of the build: the cards, the panel and the project in context come from it. */
  items: SearchItem[];
  /** Hosts of the developers' sites, the only external links an answer may keep. */
  allowedHosts: string[];
};

type Pending = { question: string; steps: StepView[] };
type Failure = { error: AdvisorError; question: string; at: Date };

/** The API the browser talks to; the page says so when it is missing instead of failing. */
const API_URL = import.meta.env.PUBLIC_API_URL as string | undefined;

export default function AdvisorPage({ items, allowedHosts }: Props) {
  const catalog = useMemo(() => new Map(items.map((item) => [item.slug, item])), [items]);
  const policy = useMemo(() => linkPolicy(allowedHosts), [allowedHosts]);
  const client = useMemo(() => (API_URL ? new AdvisorClient(API_URL) : null), []);

  const [ready, setReady] = useState(false);
  const storage = useRef<Storage | null>(null);
  const [store, setStore] = useState<AdvisorStore>(EMPTY_STORE);
  const [persistent, setPersistent] = useState(true);
  const [activeId, setActiveId] = useState<string | null>(null);
  // The project of a new conversation; a stored one carries its own.
  const [contextSlug, setContextSlug] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [listOpen, setListOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // The store as of the last render, for the handlers that run after an await.
  const storeRef = useRef(store);
  storeRef.current = store;

  const active = activeId ? findConversation(store, activeId) : null;
  const projectSlug = active ? active.projectSlug : contextSlug;
  const project = projectSlug ? (catalog.get(projectSlug) ?? null) : null;
  const messages = active?.messages ?? [];
  const mentioned = knownProjects(conversationProjects(messages), catalog);
  const busy = pending !== null;
  const blocked = busy || secondsLeft > 0 || client === null;

  // Read the stored conversations and the URL once, in the browser.
  useEffect(() => {
    storage.current = browserStorage();
    const read = readStore(storage.current, new Date());
    setStore(read);
    // Saving at once makes the 7-day deletion stick.
    setPersistent(writeStore(storage.current, read));
    const params = new URLSearchParams(window.location.search);
    const id = params.get("c");
    const slug = params.get("proyecto");
    if (id && findConversation(read, id)) setActiveId(id);
    else if (slug && catalog.has(slug)) setContextSlug(slug);
    setReady(true);
    inputRef.current?.focus();
  }, [catalog]);

  // The URL follows the open conversation, so a reload or a shared link brings it back.
  useEffect(() => {
    if (!ready) return;
    const params = new URLSearchParams();
    if (activeId) params.set("c", activeId);
    else if (contextSlug) params.set("proyecto", contextSlug);
    const query = params.toString();
    window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
  }, [ready, activeId, contextSlug]);

  // The newest message stays in view; the empty state starts at its title.
  useEffect(() => {
    const element = scrollRef.current;
    if (element && (messages.length > 0 || pending)) element.scrollTop = element.scrollHeight;
  }, [messages.length, pending, failure]);

  // The per-minute limit counts down; at zero the send button comes back by itself.
  useEffect(() => {
    if (failure?.error.kind !== "rate-minute") return;
    const until = failure.at.getTime() + failure.error.retryAfterSeconds * 1000;
    const tick = () => {
      const left = Math.max(0, Math.ceil((until - Date.now()) / 1000));
      setSecondsLeft(left);
      if (left === 0) setFailure(null);
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [failure]);

  const save = useCallback((next: AdvisorStore) => {
    storeRef.current = next;
    setStore(next);
    if (!writeStore(storage.current, next)) setPersistent(false);
  }, []);

  /** Store the conversation first in the list, telling when the oldest one had to go. */
  const saveConversation = useCallback(
    (conversation: StoredConversation) => {
      const { store: next, dropped } = upsertConversation(storeRef.current, conversation);
      save(next);
      if (dropped) setNotice(STORAGE_TEXTS.dropped);
    },
    [save],
  );

  const send = useCallback(
    async (question: string, conversation: StoredConversation | null, slug: string | null) => {
      if (!client || client.busy) return;
      const asked: StoredMessage = { role: "user", text: question, at: new Date().toISOString() };
      // In a stored conversation the question is kept before the answer: if the tab closes
      // mid-turn, the page shows it unanswered and offers to ask it again.
      let current = conversation ? appendMessage(conversation, asked) : null;
      if (current) saveConversation(current);
      setPending({ question, steps: [] });
      setFailure(null);
      setNotice(null);
      setDraft("");

      const result = await client.send({
        message: question,
        threadId: conversation?.id ?? null,
        onStep: (step) =>
          setPending((now) => {
            if (!now) return now;
            if (step.phase === "start") {
              return { ...now, steps: [...now.steps, { tool: step.tool, done: false }] };
            }
            const index = now.steps.findIndex((s) => s.tool === step.tool && !s.done);
            if (index === -1) return now;
            const steps = now.steps.map((s, i) => (i === index ? { ...s, done: true } : s));
            return { ...now, steps };
          }),
      });
      setPending(null);

      if (result.ok) {
        const { answer } = result;
        const reply: StoredMessage = {
          role: "advisor",
          text: answer.reply,
          tools: answer.toolsUsed,
          projects: answer.projects,
          at: new Date().toISOString(),
        };
        current = current
          ? appendMessage(current, reply)
          : newConversation(answer.threadId, [asked, reply], slug);
        saveConversation(current);
        setActiveId(current.id);
        setRemaining(answer.remainingToday);
        inputRef.current?.focus();
        return;
      }

      const { error } = result;
      if (error.kind === "busy") return;
      // The question did not get an answer: it leaves the conversation and waits elsewhere.
      if (current) {
        current = { ...current, messages: current.messages.slice(0, -1) };
        saveConversation(current);
      }
      if (error.kind === "gone" || error.kind === "full") {
        save(closeConversation(storeRef.current, conversation?.id ?? ""));
      }
      setFailure({ error, question, at: new Date() });
      if (error.kind === "gone") {
        // The server forgot the conversation: the question goes on in a new one by itself.
        setActiveId(null);
        setContextSlug(slug);
        void send(question, null, slug);
        return;
      }
      if (error.kind === "rate-minute" || error.kind === "rate-day" || error.kind === "budget") {
        setDraft(question); // nothing was asked: the question waits in the box
      }
      inputRef.current?.focus();
    },
    [client, save, saveConversation],
  );

  const ask = (question: string) => {
    const text = question.trim();
    if (!text || blocked) return;
    const writable = active && !active.closed ? active : null;
    void send(text, writable, writable ? writable.projectSlug : projectSlug);
  };

  const startNew = (keepProject: boolean, question = "") => {
    setActiveId(null);
    setContextSlug(keepProject ? projectSlug : null);
    setFailure(null);
    setNotice(null);
    setDraft(question);
    setListOpen(false);
    inputRef.current?.focus();
  };

  const select = (id: string) => {
    setActiveId(id);
    setFailure(null);
    setNotice(null);
    setListOpen(false);
    inputRef.current?.focus();
  };

  const retryUnanswered = (question: string) => {
    if (!active || blocked) return;
    // Drop the unanswered question; send() writes it again with its answer.
    const trimmed = { ...active, messages: active.messages.slice(0, -1) };
    saveConversation(trimmed);
    void send(question, trimmed.closed ? null : trimmed, trimmed.projectSlug);
  };

  const view = failure ? errorView(failure.error, failure.at, secondsLeft) : null;
  const unanswered = !busy && !failure ? unansweredQuestion(active) : null;
  const suggestions = suggestionsFor(project);
  const empty = messages.length === 0 && !pending;

  const list = (heading: boolean) => (
    <ConversationList
      heading={heading}
      conversations={store.conversations}
      activeId={activeId}
      catalog={catalog}
      now={new Date()}
      onSelect={select}
      onNew={() => startNew(false)}
      keepHistory={store.keepHistory}
      onKeepHistory={(keep) => save(setKeepHistory(storeRef.current, keep))}
      onClear={() => {
        clearStore(storage.current);
        storeRef.current = { ...EMPTY_STORE, keepHistory: store.keepHistory };
        setStore(storeRef.current);
        writeStore(storage.current, storeRef.current);
        startNew(false);
      }}
      persistent={persistent}
    />
  );
  const panel = (
    <ProjectPanel
      project={project}
      mentioned={mentioned}
      onClose={
        project && !active
          ? () => {
              setContextSlug(null);
              setPanelOpen(false);
            }
          : undefined
      }
    />
  );

  return (
    // As wide as the kit's 1440 px screen, wider than the site's container: the thread needs
    // the room between the list and the panel.
    <div className="mx-auto grid h-[calc(100dvh-var(--size-nav-mobile))] w-full max-w-[1440px] grid-cols-1 gap-6 px-4 py-4 sm:px-6 md:h-[calc(100dvh-var(--size-nav))] lg:grid-cols-[280px_minmax(0,1fr)_280px] lg:py-6 xl:grid-cols-[351px_minmax(0,1fr)_323px]">
      <h1 className="sr-only">Asesor de Sobreplano</h1>

      <aside aria-label="Tus conversaciones" className="hidden min-h-0 lg:block">
        {list(true)}
      </aside>

      <section
        aria-label={active ? active.title : "Nueva consulta"}
        className="flex min-h-0 flex-col gap-4 rounded-lg bg-bg-subtle p-3 sm:p-6"
      >
        <div className="flex h-(--size-control-md) shrink-0 items-center justify-between gap-3 rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface px-4 sm:px-6">
          <p className="min-w-0 truncate text-body-sm font-bold text-text-primary">
            {active ? active.title : "Nueva consulta"}
          </p>
          <div className="flex shrink-0 items-center gap-1 lg:hidden">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => setListOpen(true)}
              aria-label="Tus conversaciones"
              title="Tus conversaciones"
            >
              <Icon name="unordered-list-outline" size={20} />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => setPanelOpen(true)}
              aria-label={project ? `Proyecto: ${project.name}` : "Proyectos en esta conversación"}
              title={project ? project.name : "Proyectos"}
            >
              <Icon name="properties-outline" size={20} />
            </Button>
          </div>
        </div>

        <div ref={scrollRef} className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-1 py-2">
          {empty ? (
            <Suggestions
              projectName={project?.name ?? null}
              questions={suggestions}
              onPick={ask}
              disabled={blocked}
            />
          ) : (
            <Thread messages={messages} pending={pending} catalog={catalog} policy={policy} />
          )}
          {active?.closed && !failure && (
            <div className="flex flex-col items-start gap-3 rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface p-4">
              <p className="text-body-sm text-text-primary">
                Esta conversación ya no recibe preguntas. Puedes leerla o seguir en una nueva.
              </p>
              <Button type="button" size="sm" onClick={() => startNew(true)}>
                Nueva consulta
              </Button>
            </div>
          )}
          {unanswered && (
            <div className="flex flex-col items-start gap-3 rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface p-4">
              <p className="text-body-sm text-text-primary">Esta pregunta quedó sin respuesta.</p>
              <Button type="button" size="sm" variant="soft" onClick={() => retryUnanswered(unanswered)} disabled={blocked}>
                Preguntar de nuevo
              </Button>
            </div>
          )}
        </div>

        <div className="flex shrink-0 flex-col gap-3">
          {view && view.text && failure && (
            <div
              role="alert"
              className="flex flex-col items-start gap-3 rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface p-4"
            >
              <p className="text-body-sm font-bold text-text-primary">{view.text}</p>
              {view.note && <p className="text-body-sm text-text-secondary">{view.note}</p>}
              {view.action === "retry" && (
                <Button type="button" size="sm" onClick={() => ask(failure.question)} disabled={blocked}>
                  Reintentar
                </Button>
              )}
              {view.action === "search" && (
                <a href="/proyectos/" className={buttonVariants({ size: "sm", variant: "soft" })}>
                  Seguir con la búsqueda
                </a>
              )}
              {view.action === "new-conversation" && (
                <Button type="button" size="sm" onClick={() => startNew(true, failure.question)}>
                  Nueva consulta
                </Button>
              )}
            </div>
          )}
          {notice && (
            <p role="status" className="text-body-sm text-text-secondary">
              {notice}
            </p>
          )}
          {client === null && (
            <p role="alert" className="text-body-sm font-bold text-text-primary">
              El asesor no está disponible en esta versión del sitio.
            </p>
          )}
          <Composer
            value={draft}
            onChange={setDraft}
            onSubmit={() => ask(draft)}
            disabled={blocked || (active?.closed ?? false)}
            remaining={remainingLabel(remaining)}
            inputRef={inputRef}
          />
        </div>
      </section>

      <aside aria-label="Proyecto" className="hidden min-h-0 overflow-y-auto lg:block">
        {panel}
      </aside>

      <Sheet open={listOpen} onOpenChange={setListOpen} title="Tus conversaciones" className="lg:hidden">
        {list(false)}
      </Sheet>
      <Sheet
        open={panelOpen}
        onOpenChange={setPanelOpen}
        title={project ? "Proyecto" : "Proyectos"}
        className="lg:hidden"
      >
        {panel}
      </Sheet>
    </div>
  );
}
