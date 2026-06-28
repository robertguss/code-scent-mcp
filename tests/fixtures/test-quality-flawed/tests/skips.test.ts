// INTENTIONALLY FLAWED CodeScent fixture for the TS skip cluster smell.
// This is an INPUT to the scanner. Do NOT "fix" the skips below.
import { describe, expect, it } from "vitest";
import { add } from "../src/math";

describe("skips", () => {
  it.skip("one", () => {
    expect(add(1, 2)).toBe(3);
  });

  it.skip("two", () => {
    expect(add(2, 2)).toBe(4);
  });

  it.todo("three");
});
