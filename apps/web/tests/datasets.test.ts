import { describe, expect, it, vi } from "vitest";
import { createDatasetReader } from "../src/datasets";
import { listed, inspected, metadata } from "./dataset-fixture";

describe("catalog transport", () => {
  it("uses generated GET paths, no-store and cancellation", async () => {
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(listed))
      .mockResolvedValueOnce(Response.json(inspected));
    const reader = createDatasetReader("http://local.test/api", transport);
    const controller = new AbortController();
    expect(await reader.list(controller.signal)).toEqual(listed);
    expect(await reader.inspect(metadata.root_hash, controller.signal)).toEqual(
      inspected,
    );
    const request = transport.mock.calls[1][0] as Request;
    expect(request.url).toBe(
      `http://local.test/api/v1/datasets/${metadata.root_hash}/inspection`,
    );
    expect(request.method).toBe("GET");
    expect(request.cache).toBe("no-store");
    controller.abort();
    expect(request.signal.aborted).toBe(true);
  });
  it.each([
    null,
    {},
    { items: [null] },
    { items: [listed.items[0], listed.items[0]] },
    {
      items: [
        {
          ...listed.items[0],
          metadata: { ...metadata, backtest_eligible: true },
        },
      ],
    },
    {
      items: [
        {
          ...listed.items[0],
          metadata: { ...metadata, ineligibility_reasons: [] },
        },
      ],
    },
    { items: [{ ...listed.items[0], replay_status: "VERIFIED" }] },
  ])("rejects malformed listing %j", async (body) => {
    const reader = createDatasetReader("http://local.test", async () =>
      Response.json(body),
    );
    await expect(reader.list(new AbortController().signal)).rejects.toThrow();
  });
  it.each([
    { ...inspected, metadata: { ...metadata, root_hash: "c".repeat(64) } },
    { ...inspected, rights_verified: true },
    { ...inspected, replay_completed_at: "bad" },
  ])("rejects incompatible inspection", async (body) => {
    const reader = createDatasetReader("http://local.test", async () =>
      Response.json(body),
    );
    await expect(
      reader.inspect(metadata.root_hash, new AbortController().signal),
    ).rejects.toThrow();
  });
  it("rejects bad identities before transport and hides server failures", async () => {
    const transport = vi.fn<typeof fetch>(async () =>
      Response.json({ detail: "private" }, { status: 503 }),
    );
    const reader = createDatasetReader("http://local.test", transport);
    await expect(
      reader.inspect("bad", new AbortController().signal),
    ).rejects.toThrow("Invalid root");
    expect(transport).not.toHaveBeenCalled();
    await expect(reader.list(new AbortController().signal)).rejects.toThrow(
      "Catalog unavailable",
    );
    await expect(
      reader.inspect(metadata.root_hash, new AbortController().signal),
    ).rejects.toThrow("Replay inspection unavailable");
  });
});
