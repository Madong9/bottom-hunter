import { describe, expect, it } from "vitest";

import { readableText } from "./readableText";

describe("readableText", () => {
  it("removes stored HTML and decodes common entities", () => {
    expect(
      readableText("<body><p>Revenue &amp; profit&nbsp;improved.</p></body>"),
    ).toBe("Revenue & profit improved.");
  });

  it("preserves ordinary Chinese and comparison text", () => {
    expect(readableText("美团 PE < 20，仍需核验"))
      .toBe("美团 PE < 20，仍需核验");
  });
});
