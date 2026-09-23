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
