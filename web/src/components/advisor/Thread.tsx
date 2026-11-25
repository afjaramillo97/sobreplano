// The conversation: the bubbles of the kit's Message screen, each answer with the summary of
// its steps (its source) and the small cards of the projects it names. The messages are a
// role="log"; the steps of the reply in flight are a polite live region of their own.
import { lazy, Suspense } from "react";

import ProjectCard from "@/components/ProjectCard";
import { stepSummary } from "@/lib/advisor/labels";
import type { LinkPolicy } from "@/lib/advisor/links";
import type { StoredMessage } from "@/lib/advisor/store";
import { cardProject, knownProjects, messageTime } from "@/lib/advisor/view";
import type { SearchItem } from "@/lib/search";
import { Bubble } from "./Bubble";
import { StepTrace, type StepView } from "./StepTrace";

// react-markdown and remark-gfm are most of the page's weight; the empty page needs neither.
const AnswerMarkdown = lazy(() => import("./AnswerMarkdown"));

type Props = {
  messages: readonly StoredMessage[];
  /** The question in flight and the steps heard so far. */
  pending: { question: string; steps: readonly StepView[] } | null;
  catalog: ReadonlyMap<string, SearchItem>;
  policy: LinkPolicy;
};

export function Thread({ messages, pending, catalog, policy }: Props) {
  return (
    <>
      {/* role="log" goes on a div: axe does not allow it on a list. */}
      <div role="log" aria-label="Conversación con el asesor">
      <ol className="flex flex-col gap-6">
        {messages.map((message, index) => (
          // Messages only ever append, so the index is a stable key.
          <li key={index}>
            {message.role === "user" ? (
              <Bubble from="user" meta={<time dateTime={message.at}>{messageTime(message.at)}</time>}>
                {message.text}
              </Bubble>
            ) : (
              <AdvisorMessage message={message} catalog={catalog} policy={policy} />
            )}
          </li>
        ))}
        {pending && (
          <li>
            <Bubble from="user">{pending.question}</Bubble>
          </li>
        )}
      </ol>
      </div>
      {pending && <StepTrace steps={pending.steps} />}
    </>
  );
}

function AdvisorMessage({
  message,
  catalog,
  policy,
}: {
  message: StoredMessage & { role: "advisor" };
  catalog: ReadonlyMap<string, SearchItem>;
  policy: LinkPolicy;
}) {
  const projects = knownProjects(message.projects, catalog);
  const summary = stepSummary(message.tools);
  return (
    <Bubble
      from="advisor"
      meta={
        <>
          <time dateTime={message.at}>{messageTime(message.at)}</time>
          {summary.length > 0 && <> · {summary.join(" · ")}</>}
        </>
      }
      after={
        projects.length > 0 && (
          <ul
            className="grid w-full grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3"
            aria-label="Proyectos de esta respuesta"
          >
            {projects.map((item) => (
              <li key={item.slug}>
                <ProjectCard project={cardProject(item)} size="sm" className="h-full" />
              </li>
            ))}
          </ul>
        )
      }
    >
      <Suspense fallback={<p className="whitespace-pre-wrap">{message.text}</p>}>
        <AnswerMarkdown text={message.text} policy={policy} />
      </Suspense>
    </Bubble>
  );
}
