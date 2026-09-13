export interface HealthResponse {
  status: "ok";
  api_version: string;
  workspace_root: string;
  max_request_bytes: number;
}

export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
  };
}

export interface SourceLocation {
  source?: string;
  line?: number;
  column?: number;
  line_end?: number;
  column_end?: number;
}

export interface ValidationDiagnostic {
  code?: string;
  severity?: string;
  message?: string;
  level?: string;
  provenance?: string;
  location?: SourceLocation;
}

export interface ValidationResponse {
  source_set_sha256: string;
  diagnostics: ValidationDiagnostic[];
  summary: {
    errors: number;
    warnings: number;
    [key: string]: unknown;
  };
}

export interface MeshImportResponse {
  format: string;
  provenance: {
    source: string;
    sha256: string;
  };
  summary: {
    nodes: number;
    elements: number;
    node_sets: number;
    element_sets: number;
    surfaces: number;
    orientations: number;
    element_types: string[];
  };
  [key: string]: unknown;
}

export interface OperationalCapability {
  id: string;
  kind: string;
  canonical: string;
  specification_maturity: string;
  operations: Record<string, string>;
  intents: Record<string, string>;
  parent?: string;
  entity_kind?: string;
  parameter_edits?: Array<{
    name: string;
    cardinality: string;
    operations: Record<string, string>;
  }>;
}

export interface CapabilitiesResponse {
  api_version: string;
  registry_version: string;
  bsam: Record<string, unknown>;
  capabilities: {
    operational_manifest: OperationalCapability[];
    [key: string]: unknown;
  };
  tools: string[];
  tool_contracts: Record<string, unknown>;
}

export interface ChangePlanResponse {
  plan_id: string;
  plan_digest: string;
  source_diff: string;
  validation: ValidationResponse;
  changed_model_paths?: string[];
  preview?: string;
  [key: string]: unknown;
}

export interface ApplyChangeResponse {
  plan_id: string;
  plan_digest: string;
  destination: string;
  output_sha256: string;
  output_files: string[];
  audit: string;
  validation: ValidationResponse;
  [key: string]: unknown;
}

export interface RunStatusResponse {
  state: string;
  classification: string;
  output_directory: string;
  source_set_sha256?: string;
  error?: string;
  artifacts?: string[];
  [key: string]: unknown;
}

export interface ReviewedPlan {
  source: string;
  planPath: string;
  planId: string;
  planDigest: string;
}

export interface QueryCapabilityRecord {
  id: string;
  capability_id: string;
  canonical: string;
  occurrence: number;
  location: {
    source: string;
    line: number;
  };
  parameters: Record<string, Array<{ value: string }>>;
  defaults: Record<string, unknown>;
  operations: Record<string, string>;
}

export interface QueryCapabilitiesResponse {
  source_set_sha256: string;
  query: string;
  matches: QueryCapabilityRecord[];
  summary: {
    matches: number;
    ambiguous: boolean;
  };
}
