import createClient, { type ClientOptions } from "openapi-fetch";
import type { paths } from "./generated/schema.js";

export type { components, operations, paths } from "./generated/schema.js";

/** The caller supplies its API URL and optional transport; no global client state. */
export function createApiClient(options: ClientOptions & { baseUrl: string }) {
  return createClient<paths>(options);
}
