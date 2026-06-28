// Healthy CodeScent fixture: well-formed TS tests that must produce ZERO
// test-quality findings (the no-false-positive acceptance bar).
import { describe, expect, it, vi } from "vitest";
import { add } from "../src/math";

describe("healthy", () => {
  it("adds numbers", () => {
    expect(add(1, 2)).toBe(3);
  });

  it("verifies a single interaction", () => {
    const spy = vi.fn();
    spy("input");
    expect(spy).toHaveBeenCalledWith("input");
  });
});
