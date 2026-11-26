import { describe, expect, it } from "vitest";
import { safeHttpUrl } from "./safe-url";

describe("safeHttpUrl", () => {
  it("accepts http and https", () => {
    expect(safeHttpUrl("https://nsap.nic.in/")).toBe("https://nsap.nic.in/");
    expect(safeHttpUrl(" http://example.org/a?b=1 ")).toBe("http://example.org/a?b=1");
  });
  it("rejects other schemes, relative URLs and non-strings", () => {
    for (const bad of ["javascript:alert(1)", "data:text/html,x", "//evil.com", "/schemes", "ftp://x.org", "", "https://", "  java\nscript:alert(1)"]) {
      expect(safeHttpUrl(bad)).toBeNull();
    }
    expect(safeHttpUrl(undefined)).toBeNull();
    expect(safeHttpUrl(42)).toBeNull();
  });
});
