import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DatasetBrowser } from "../src/DatasetBrowser";
import { createDatasetReader, type DatasetReader } from "../src/datasets";
import { inspected, listed, metadata } from "./dataset-fixture";

function mount(reader: DatasetReader) {
  const queries = new QueryClient();
  return render(
    <QueryClientProvider client={queries}>
      <DatasetBrowser reader={reader} />
    </QueryClientProvider>,
  );
}
function reader() {
  return {
    list: vi.fn<DatasetReader["list"]>().mockResolvedValue(listed),
    inspect: vi.fn<DatasetReader["inspect"]>().mockResolvedValue(inspected),
  };
}

describe("private dataset browser", () => {
  it("lists provenance but inspects only on explicit request", async () => {
    const api = reader();
    mount(api);
    expect(screen.getByText("Loading retained catalog…")).toBeTruthy();
    await screen.findByText(metadata.operator_label);
    expect(api.inspect).not.toHaveBeenCalled();
    expect(screen.getByText(metadata.root_hash)).toBeTruthy();
    expect(
      screen.getByText("Unknown — not historically established"),
    ).toBeTruthy();
    expect(screen.getByText("RAW_AVAILABILITY_UNKNOWN")).toBeTruthy();
    expect(
      screen.getByText("Replay-only. Not backtest-eligible."),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Inspect replay" }));
    await screen.findByText("Backend replay observation: VERIFIED");
    expect(api.inspect).toHaveBeenCalledTimes(1);
    expect(api.inspect.mock.calls[0][0]).toBe(metadata.root_hash);
    expect(screen.getByText(inspected.replay_completed_at)).toBeTruthy();
    expect(
      screen.getByText(/Replay does not verify provider rights/),
    ).toBeTruthy();
    expect(screen.getByText(/Metadata listing: NOT_CHECKED/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh catalog" }));
    await waitFor(() => expect(api.list).toHaveBeenCalledTimes(2));
    await screen.findByText(metadata.operator_label);
    expect(
      screen.queryByText("Backend replay observation: VERIFIED"),
    ).toBeNull();
    expect(api.inspect).toHaveBeenCalledTimes(1);
  });
  it("hides previous success during a new inspection and after failure", async () => {
    const api = reader();
    let fail!: (reason: Error) => void;
    api.inspect.mockResolvedValueOnce(inspected).mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          fail = reject;
        }),
    );
    mount(api);
    fireEvent.click(
      await screen.findByRole("button", { name: "Inspect replay" }),
    );
    await screen.findByText("Backend replay observation: VERIFIED");
    fireEvent.click(screen.getByRole("button", { name: "Inspect replay" }));
    await screen.findByRole("button", { name: "Inspecting replay…" });
    expect(
      screen.queryByText("Backend replay observation: VERIFIED"),
    ).toBeNull();
    fail(new Error("private bucket credentials"));
    await screen.findByText(/Inspection failed or timed out/);
    expect(screen.queryByText(/private bucket credentials/)).toBeNull();
    expect(
      screen.queryByText("Backend replay observation: VERIFIED"),
    ).toBeNull();
    expect(api.inspect).toHaveBeenCalledTimes(2);
  });
  it("shows empty and unavailable states with explicit recovery", async () => {
    const api = reader();
    api.list
      .mockRejectedValueOnce(new Error("private"))
      .mockResolvedValueOnce({ items: [] });
    mount(api);
    await screen.findByRole("alert");
    expect(api.list).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Refresh catalog" }));
    await screen.findByText(/No dataset roots are selected/);
    expect(api.list).toHaveBeenCalledTimes(2);
  });
  it("cancels an in-flight replay when unmounted", async () => {
    const api = reader();
    api.inspect.mockImplementation(() => new Promise(() => {}));
    const view = mount(api);
    fireEvent.click(
      await screen.findByRole("button", { name: "Inspect replay" }),
    );
    await waitFor(() => expect(api.inspect).toHaveBeenCalledTimes(1));
    const signal = api.inspect.mock.calls[0][1];
    view.unmount();
    expect(signal.aborted).toBe(true);
  });
  it("renders provider-like labels as text, never markup", async () => {
    const api = reader();
    const label = "<img src=x onerror=alert(1)>";
    api.list.mockResolvedValue({
      items: [
        {
          metadata: { ...metadata, operator_label: label },
          replay_status: "NOT_CHECKED",
        },
      ],
    });
    mount(api);
    await screen.findByText(label);
    expect(screen.queryByRole("img")).toBeNull();
  });
  it("rejects invalid HTTP success rather than displaying eligibility", async () => {
    const transport = vi.fn<typeof fetch>(async () =>
      Response.json({
        items: [
          {
            ...listed.items[0],
            metadata: { ...metadata, backtest_eligible: true },
          },
        ],
      }),
    );
    mount(createDatasetReader("http://local.test", transport));
    await screen.findByRole("alert");
    expect(screen.queryByText(metadata.operator_label)).toBeNull();
    expect(transport).toHaveBeenCalledTimes(1);
  });
});
