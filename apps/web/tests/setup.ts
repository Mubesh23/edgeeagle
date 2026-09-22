import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

beforeEach(() => {
  vi.stubGlobal("fetch", () => {
    throw new Error("Real network requests forbidden in unit tests");
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
