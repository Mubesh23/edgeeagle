import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { createHealthReader } from "../src/health";

function mount(readHealth: ReturnType<typeof createHealthReader>) {
  const client = new QueryClient({
    defaultOptions: { queries: { gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <App readHealth={readHealth} />
    </QueryClientProvider>,
  );
}
describe("foundation shell", () => {
  it("shows loading until the generated client returns liveness", async () => {
    let respond!: (value: Response) => void;
    const transport = vi.fn<typeof fetch>(
      () =>
        new Promise((resolve) => {
          respond = resolve;
        }),
    );
    mount(createHealthReader("http://local.test/api", transport));
    expect(screen.getByRole("status").textContent).toContain("Checking API");
    respond(Response.json({ status: "ok" }));
    await screen.findByText("API process is responding.");
    expect(transport.mock.calls[0]?.[0]).toBeInstanceOf(Request);
    expect((transport.mock.calls[0]?.[0] as Request).url).toBe(
      "http://local.test/api/health",
    );
  });
  it("shows failure and supports an explicit retry", async () => {
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({}, { status: 503 }))
      .mockResolvedValueOnce(Response.json({ status: "ok" }));
    mount(createHealthReader("http://local.test/api", transport));
    fireEvent.click(
      await screen.findByRole("button", { name: "Retry connection" }),
    );
    await screen.findByText("API process is responding.");
    expect(transport).toHaveBeenCalledTimes(2);
  });
  it.each([null, {}, { status: "bad" }])(
    "rejects invalid successful payload %j",
    async (body) => {
      const reader = createHealthReader("http://local.test", async () =>
        Response.json(body),
      );
      await expect(reader(new AbortController().signal)).rejects.toThrow();
    },
  );
  it("surfaces network failures", async () => {
    mount(
      createHealthReader("http://local.test", async () => {
        throw new TypeError("offline");
      }),
    );
    await screen.findByRole("button", { name: "Retry connection" });
  });
});
