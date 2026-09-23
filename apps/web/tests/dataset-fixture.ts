import type { DatasetInspection, DatasetMetadata } from "../src/datasets";

// Authored contract fixture, never a captured private dataset.
export const metadata: DatasetMetadata = {
  root_hash: "a".repeat(64),
  operator_label: "Authored test season",
  declared_row_count: 2,
  page_count: 1,
  usage: "REPLAY_ONLY",
  backtest_eligible: false,
  parser_version: "test-parser-v1",
  normalizer_version: "test-normalizer-v1",
  ineligibility_reasons: [
    "REPLAY_ONLY_CONTRACT",
    "CONTEXT_AVAILABILITY_UNPROVEN",
    "RAW_AVAILABILITY_UNKNOWN",
  ],
  raw: {
    sha256: "b".repeat(64),
    size_bytes: 100,
    capture: {
      data_source_id: { value: "authored-source" },
      resource: "authored.csv",
      ingested_at: "2026-09-23T00:00:00Z",
      available_at: null,
      effective_at: null,
      observed_at: null,
    },
  },
};
export const listed = {
  items: [{ metadata, replay_status: "NOT_CHECKED" as const }],
};
export const inspected: DatasetInspection = {
  metadata,
  replay_status: "VERIFIED",
  verification_scope: "RETAINED_ARTIFACT_REPLAY",
  database_acceptance_verified: false,
  kickoff_accuracy_verified: false,
  rights_verified: false,
  receipt_count: 2,
  participant_count: 4,
  replay_completed_at: "2026-09-23T01:00:00Z",
  asserted_starts_at_min: "2025-01-01T12:00:00Z",
  asserted_starts_at_max: "2025-01-02T12:00:00Z",
  sport_ids: ["soccer"],
  competition_ids: ["authored-league"],
  season_ids: ["authored-season"],
  context_versions: ["authored-context-v1"],
};
