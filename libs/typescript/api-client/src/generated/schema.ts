/** Generated from FastAPI via scripts/generate-contracts. Do not edit. */
export interface paths {
  "/health": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Health */
    get: operations["get_health"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/v1/datasets": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * List Datasets
     * @description Read selected roots only; never imply that full replay was checked.
     */
    get: operations["list_datasets"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/v1/datasets/{rootHash}/inspection": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * Inspect Dataset
     * @description Freshly replay retained artifacts; never upgrade historical eligibility.
     */
    get: operations["inspect_dataset"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/v1/events": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Events */
    get: operations["list_events"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/v1/events/{eventId}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Get Event */
    get: operations["get_event"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
}
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    /**
     * DataSourceId
     * @description Opaque internally assigned source identity, not a provider-native ID.
     */
    DataSourceId: {
      /** Value */
      value: string;
    };
    /** DatasetErrorResponse */
    DatasetErrorResponse: {
      /** Detail */
      detail: string;
    };
    /** DatasetInspection */
    DatasetInspection: {
      /**
       * Asserted Starts At Max
       * Format: date-time
       */
      asserted_starts_at_max: string;
      /**
       * Asserted Starts At Min
       * Format: date-time
       */
      asserted_starts_at_min: string;
      /** Competition Ids */
      competition_ids: string[];
      /** Context Versions */
      context_versions: string[];
      /**
       * Database Acceptance Verified
       * @default false
       * @constant
       */
      database_acceptance_verified: false;
      /**
       * Kickoff Accuracy Verified
       * @default false
       * @constant
       */
      kickoff_accuracy_verified: false;
      metadata: components["schemas"]["DatasetMetadata"];
      /** Participant Count */
      participant_count: number;
      /** Receipt Count */
      receipt_count: number;
      /**
       * Replay Completed At
       * Format: date-time
       */
      replay_completed_at: string;
      /**
       * Replay Status
       * @default VERIFIED
       * @constant
       */
      replay_status: "VERIFIED";
      /**
       * Rights Verified
       * @default false
       * @constant
       */
      rights_verified: false;
      /** Season Ids */
      season_ids: string[];
      /** Sport Ids */
      sport_ids: string[];
      /**
       * Verification Scope
       * @default RETAINED_ARTIFACT_REPLAY
       * @constant
       */
      verification_scope: "RETAINED_ARTIFACT_REPLAY";
    };
    /** DatasetListResponse */
    DatasetListResponse: {
      /** Items */
      items: components["schemas"]["DatasetListing"][];
    };
    /** DatasetListing */
    DatasetListing: {
      metadata: components["schemas"]["DatasetMetadata"];
      /**
       * Replay Status
       * @default NOT_CHECKED
       * @constant
       */
      replay_status: "NOT_CHECKED";
    };
    /** DatasetMetadata */
    DatasetMetadata: {
      /**
       * Backtest Eligible
       * @default false
       * @constant
       */
      backtest_eligible: false;
      /** Declared Row Count */
      declared_row_count: number;
      /** Ineligibility Reasons */
      ineligibility_reasons: string[];
      /**
       * Normalizer Version
       * @default football-data-results-mappings-v1
       */
      normalizer_version: string;
      /** Operator Label */
      operator_label: string;
      /** Page Count */
      page_count: number;
      /**
       * Parser Version
       * @default football-data-results-season-csv-v1
       */
      parser_version: string;
      raw: components["schemas"]["RawPayloadReference"];
      /** Root Hash */
      root_hash: string;
      /**
       * Usage
       * @default REPLAY_ONLY
       * @constant
       */
      usage: "REPLAY_ONLY";
    };
    /** EventDetailResponse */
    EventDetailResponse: {
      /** Competition Id */
      competition_id: string;
      /** Event Id */
      event_id: string;
      /** Participants */
      participants: components["schemas"]["EventEntryResponse"][];
      /** Season Id */
      season_id: string;
      /** Sport Id */
      sport_id: string;
      /**
       * Starts At
       * Format: date-time
       */
      starts_at: string;
      /** Status */
      status: string;
      /** Venue Location */
      venue_location: string | null;
    };
    /** EventEntryResponse */
    EventEntryResponse: {
      /** Participant Id */
      participant_id: string;
      /** Role */
      role: string;
    };
    /** EventErrorResponse */
    EventErrorResponse: {
      /** Detail */
      detail: string;
    };
    /** EventListResponse */
    EventListResponse: {
      /** Items */
      items: components["schemas"]["EventResponse"][];
      /** Next After Event Id */
      next_after_event_id: string | null;
    };
    /** EventResponse */
    EventResponse: {
      /** Competition Id */
      competition_id: string;
      /** Event Id */
      event_id: string;
      /** Season Id */
      season_id: string;
      /** Sport Id */
      sport_id: string;
      /**
       * Starts At
       * Format: date-time
       */
      starts_at: string;
      /** Status */
      status: string;
      /** Venue Location */
      venue_location: string | null;
    };
    /** HTTPValidationError */
    HTTPValidationError: {
      /** Detail */
      detail?: components["schemas"]["ValidationError"][];
    };
    /**
     * HealthResponse
     * @description Process liveness only; this does not assert dependency readiness.
     */
    HealthResponse: {
      /**
       * Status
       * @default ok
       * @constant
       */
      status: "ok";
    };
    /** RawCapture */
    RawCapture: {
      /** Available At */
      available_at?: string | null;
      data_source_id: components["schemas"]["DataSourceId"];
      /** Effective At */
      effective_at?: string | null;
      /**
       * Ingested At
       * Format: date-time
       */
      ingested_at: string;
      /** Observed At */
      observed_at?: string | null;
      /** Resource */
      resource: string;
    };
    /** RawPayloadReference */
    RawPayloadReference: {
      capture: components["schemas"]["RawCapture"];
      /** Sha256 */
      sha256: string;
      /** Size Bytes */
      size_bytes: number;
    };
    /** ValidationError */
    ValidationError: {
      /** Context */
      ctx?: Record<string, never>;
      /** Input */
      input?: unknown;
      /** Location */
      loc: (string | number)[];
      /** Message */
      msg: string;
      /** Error Type */
      type: string;
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
  get_health: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HealthResponse"];
        };
      };
    };
  };
  list_datasets: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["DatasetListResponse"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["DatasetErrorResponse"];
        };
      };
    };
  };
  inspect_dataset: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        rootHash: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["DatasetInspection"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["DatasetErrorResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["DatasetErrorResponse"];
        };
      };
    };
  };
  list_events: {
    parameters: {
      query?: {
        limit?: number;
        after_event_id?: string | null;
        sport_id?: string | null;
        competition_id?: string | null;
        status?: string | null;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["EventListResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["EventErrorResponse"];
        };
      };
    };
  };
  get_event: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        eventId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["EventDetailResponse"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["EventErrorResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["EventErrorResponse"];
        };
      };
    };
  };
}
