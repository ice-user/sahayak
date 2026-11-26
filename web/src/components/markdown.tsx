import ReactMarkdown from "react-markdown";
import { safeHttpUrl } from "@/lib/safe-url";

/**
 * Renders assistant markdown. Raw HTML is never rendered, images are dropped (a remote image would make
 * the reader's browser request an attacker-chosen URL), and only absolute http(s) links are clickable.
 */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        disallowedElements={["img"]}
        urlTransform={(url) => safeHttpUrl(url) ?? ""}
        components={{
          a: ({ href, children: c }) => {
            const safe = safeHttpUrl(href);
            if (!safe) return <span>{c}</span>;
            return (
              <a href={safe} target="_blank" rel="noopener noreferrer">
                {c}
              </a>
            );
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
