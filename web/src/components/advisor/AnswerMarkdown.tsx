// An advisor answer as Markdown (react-markdown and remark-gfm, for the comparison tables).
// The answer is untrusted input (docs/security.md): raw HTML is skipped, images are dropped and
// every link goes through the page's link policy, so one the policy refuses stays as text.
// Loaded lazily by the page: the first screen needs none of it.
import { memo } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import type { LinkPolicy } from "@/lib/advisor/links";

type Props = { text: string; policy: LinkPolicy };

function components(policy: LinkPolicy): Components {
  return {
    a({ href, children }) {
      const link = href ? policy(href) : null;
      if (!link) return <span>{children}</span>;
      return link.external ? (
        <a
          href={link.href}
          target="_blank"
          rel="noopener noreferrer"
          className="font-bold text-action-soft-text underline underline-offset-2 hover:text-action"
        >
          {children}
          <span className="sr-only"> (se abre en otra pestaña)</span>
        </a>
      ) : (
        <a
          href={link.href}
          className="font-bold text-action-soft-text underline underline-offset-2 hover:text-action"
        >
          {children}
        </a>
      );
    },
    // Answers are short: headings would be louder than the page's own.
    h1: ({ children }) => <p className="font-bold">{children}</p>,
    h2: ({ children }) => <p className="font-bold">{children}</p>,
    h3: ({ children }) => <p className="font-bold">{children}</p>,
    h4: ({ children }) => <p className="font-bold">{children}</p>,
    p: ({ children }) => <p>{children}</p>,
    ul: ({ children }) => <ul className="flex list-disc flex-col gap-1 pl-5">{children}</ul>,
    ol: ({ children }) => <ol className="flex list-decimal flex-col gap-1 pl-5">{children}</ol>,
    strong: ({ children }) => <strong className="font-bold">{children}</strong>,
    table: ({ children }) => (
      // The table scrolls inside the bubble, never the page; a scrollable region must take
      // the focus, so a keyboard can scroll it (axe: scrollable-region-focusable).
      <div
        tabIndex={0}
        className="max-w-full overflow-x-auto rounded-sm outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring"
      >
        <table className="w-full border-collapse text-body-sm tabular-nums">{children}</table>
      </div>
    ),
    th: ({ children }) => (
      <th className="border-b-(length:--border-width-default) border-border-input px-3 py-2 text-left font-bold whitespace-nowrap">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="border-b-(length:--border-width-default) border-border px-3 py-2 whitespace-nowrap">
        {children}
      </td>
    ),
    code: ({ children }) => <code className="rounded-sm bg-bg-subtle px-1">{children}</code>,
    hr: () => <hr className="border-t-(length:--border-width-default) border-border" />,
  };
}

function AnswerMarkdown({ text, policy }: Props) {
  return (
    <div className="flex flex-col gap-3 break-words">
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        disallowedElements={["img"]}
        components={components(policy)}
      >
        {text}
      </Markdown>
    </div>
  );
}

// One per message: an answer never changes once it arrived.
export default memo(AnswerMarkdown);
