import { createApiClient } from "@edgeeagle/api-client";

export function createHealthReader(
  baseUrl: string,
  transport: typeof fetch = globalThis.fetch,
) {
  const client = createApiClient({ baseUrl, fetch: transport });
  return async (signal: AbortSignal) => {
    const { data, response } = await client.GET("/health", {
      signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
    });
    if (!response.ok || data?.status !== "ok") {
      throw new Error("API liveness check failed");
    }
    return data;
  };
}
