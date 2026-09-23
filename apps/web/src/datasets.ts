import { createApiClient, type components } from "@edgeeagle/api-client";

export type DatasetMetadata = components["schemas"]["DatasetMetadata"];
export type DatasetInspection = components["schemas"]["DatasetInspection"];
type Listing = components["schemas"]["DatasetListResponse"];

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Invalid catalog response");
  }
  return value as Record<string, unknown>;
}
function text(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}
function digest(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[0-9a-f]{64}$/.test(value) &&
    value.length === 64
  );
}
function count(value: unknown): boolean {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(text);
}
function timestamp(value: unknown): boolean {
  return (
    typeof value === "string" &&
    /(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}
function metadata(value: unknown): void {
  const m = record(value);
  const raw = record(m.raw);
  const capture = record(raw.capture);
  const source = record(capture.data_source_id);
  if (
    !digest(m.root_hash) ||
    !text(m.operator_label) ||
    !count(m.declared_row_count) ||
    !count(m.page_count) ||
    !text(m.parser_version) ||
    !text(m.normalizer_version) ||
    m.usage !== "REPLAY_ONLY" ||
    m.backtest_eligible !== false ||
    !strings(m.ineligibility_reasons) ||
    !m.ineligibility_reasons.includes("REPLAY_ONLY_CONTRACT") ||
    !m.ineligibility_reasons.includes("CONTEXT_AVAILABILITY_UNPROVEN") ||
    !digest(raw.sha256) ||
    !count(raw.size_bytes) ||
    !text(source.value) ||
    !text(capture.resource) ||
    !timestamp(capture.ingested_at) ||
    ![capture.available_at, capture.effective_at, capture.observed_at].every(
      (v) => v === null || timestamp(v),
    ) ||
    (capture.available_at === null &&
      !m.ineligibility_reasons.includes("RAW_AVAILABILITY_UNKNOWN"))
  ) {
    throw new Error("Invalid catalog metadata");
  }
}
function listing(value: unknown): asserts value is Listing {
  const { items } = record(value);
  if (!Array.isArray(items) || items.length > 32)
    throw new Error("Invalid catalog list");
  const roots = new Set();
  for (const value of items) {
    const item = record(value);
    metadata(item.metadata);
    const root = record(item.metadata).root_hash;
    if (item.replay_status !== "NOT_CHECKED" || roots.has(root)) {
      throw new Error("Invalid catalog listing");
    }
    roots.add(root);
  }
}
function inspection(
  value: unknown,
  root: string,
): asserts value is DatasetInspection {
  const result = record(value);
  metadata(result.metadata);
  if (
    record(result.metadata).root_hash !== root ||
    result.replay_status !== "VERIFIED" ||
    result.verification_scope !== "RETAINED_ARTIFACT_REPLAY" ||
    result.database_acceptance_verified !== false ||
    result.kickoff_accuracy_verified !== false ||
    result.rights_verified !== false ||
    !count(result.receipt_count) ||
    !count(result.participant_count) ||
    !timestamp(result.replay_completed_at) ||
    !timestamp(result.asserted_starts_at_min) ||
    !timestamp(result.asserted_starts_at_max) ||
    ![
      result.sport_ids,
      result.competition_ids,
      result.season_ids,
      result.context_versions,
    ].every(strings)
  ) {
    throw new Error("Invalid replay inspection");
  }
}

export function createDatasetReader(
  baseUrl: string,
  transport: typeof fetch = globalThis.fetch,
) {
  const client = createApiClient({ baseUrl, fetch: transport });
  return {
    async list(signal: AbortSignal): Promise<Listing> {
      const { data, response } = await client.GET("/v1/datasets", {
        signal: AbortSignal.any([signal, AbortSignal.timeout(15000)]),
        cache: "no-store",
      });
      if (!response.ok) throw new Error("Catalog unavailable");
      listing(data);
      return data;
    },
    async inspect(
      root: string,
      signal: AbortSignal,
    ): Promise<DatasetInspection> {
      if (!digest(root)) throw new Error("Invalid root identity");
      const { data, response } = await client.GET(
        "/v1/datasets/{rootHash}/inspection",
        {
          params: { path: { rootHash: root } },
          signal: AbortSignal.any([signal, AbortSignal.timeout(60000)]),
          cache: "no-store",
        },
      );
      if (!response.ok) throw new Error("Replay inspection unavailable");
      inspection(data, root);
      return data;
    },
  };
}
export type DatasetReader = ReturnType<typeof createDatasetReader>;
