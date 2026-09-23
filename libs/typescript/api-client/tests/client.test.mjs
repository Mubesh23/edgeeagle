import assert from "node:assert/strict";
import test from "node:test";
import { createApiClient } from "@edgeeagle/api-client";

test("the generated health operation uses the supplied transport", async () => {
  const requests = [];
  const client = createApiClient({
    baseUrl: "https://api.example.test",
    fetch: async (request) => {
      requests.push(request);
      return Response.json({ status: "ok" });
    },
  });
  const { data, response } = await client.GET("/health");
  assert.deepEqual(data, { status: "ok" });
  assert.equal(response.status, 200);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "https://api.example.test/health");
  assert.equal(requests[0].method, "GET");
});

test("HTTP failures remain visible to the caller", async () => {
  const client = createApiClient({
    baseUrl: "https://api.example.test",
    fetch: async () =>
      Response.json({ detail: "unavailable" }, { status: 503 }),
  });
  const result = await client.GET("/health");
  assert.equal(result.data, undefined);
  assert.equal(result.response.status, 503);
  assert.deepEqual(result.error, { detail: "unavailable" });
});

test("event queries preserve filters and canonical path identity", async () => {
  const requests = [];
  const client = createApiClient({
    baseUrl: "https://api.example.test",
    fetch: async (request) => {
      requests.push(request);
      return Response.json({ items: [], next_after_event_id: null });
    },
  });
  const result = await client.GET("/v1/events", {
    params: { query: { limit: 2, sport_id: "sport-a", after_event_id: "e-a" } },
  });
  assert.deepEqual(result.data, { items: [], next_after_event_id: null });
  const url = new URL(requests[0].url);
  assert.equal(url.searchParams.get("limit"), "2");
  assert.equal(url.searchParams.get("sport_id"), "sport-a");
  assert.equal(url.searchParams.get("after_event_id"), "e-a");
  await client.GET("/v1/events/{eventId}", {
    params: { path: { eventId: "canonical-e" } },
  });
  assert.equal(new URL(requests[1].url).pathname, "/v1/events/canonical-e");
  assert.equal(requests[1].method, "GET");
});
