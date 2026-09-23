import { createApiClient } from "../src/index.js";

const client = createApiClient({ baseUrl: "https://api.example.test" });

async function checkContract() {
  const { data } = await client.GET("/health");
  if (data) {
    const status: "ok" = data.status;
    void status;
    // @ts-expect-error This field is absent from the authoritative response.
    data.probability;
  }
  const page = await client.GET("/v1/events", {
    params: { query: { limit: 10 } },
  });
  if (page.data) {
    const cursor: string | null = page.data.next_after_event_id;
    void cursor;
  }
  const event = await client.GET("/v1/events/{eventId}", {
    params: { path: { eventId: "e" } },
  });
  if (event.data) {
    const role: string | undefined = event.data.participants[0]?.role;
    void role;
    // @ts-expect-error Event reads do not invent prediction probabilities.
    event.data.probability;
  }
  // @ts-expect-error The event read slice does not support writes.
  await client.POST("/v1/events");
  const datasets = await client.GET("/v1/datasets");
  if (datasets.data) {
    const status: "NOT_CHECKED" | undefined =
      datasets.data.items[0]?.replay_status;
    void status;
  }
  const inspection = await client.GET("/v1/datasets/{rootHash}/inspection", {
    params: { path: { rootHash: "a".repeat(64) } },
  });
  if (inspection.data) {
    const eligible: false = inspection.data.metadata.backtest_eligible;
    const status: "VERIFIED" = inspection.data.replay_status;
    void eligible;
    void status;
    // @ts-expect-error Replay inspection is not a model probability.
    inspection.data.probability;
  }
  // @ts-expect-error The private catalog supports no HTTP writes.
  await client.POST("/v1/datasets");
  // @ts-expect-error The health route does not support writes.
  await client.POST("/health");
}

void checkContract;
