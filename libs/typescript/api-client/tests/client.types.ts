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
  // @ts-expect-error Future domain endpoints must not appear before implementation.
  await client.GET("/v1/events");
  // @ts-expect-error The health route does not support writes.
  await client.POST("/health");
}

void checkContract;
