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
