// INTENTIONALLY FLAWED CodeScent fixture for TS test-quality smells.
// This is an INPUT to the scanner. Do NOT "fix" the smells below.
import { describe, expect, it, vi } from "vitest";

describe("smells", () => {
  it("asserts nothing", () => {
    const value = 1 + 1;
    console.log(value);
  });

  it("always passes", () => {
    expect(true).toBe(true);
  });

  it("empty body", () => {});

  it("over mocks", () => {
    const first = vi.fn();
    const second = vi.fn();
    const third = vi.spyOn(globalThis, "fetch");
    const fourth = vi.fn();
    first();
    second();
    void third;
    fourth();
  });
});
