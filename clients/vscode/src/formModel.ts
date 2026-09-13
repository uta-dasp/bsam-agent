import { CapabilitiesResponse, QueryCapabilityRecord } from "./types";

export interface EditableParameter {
  name: string;
  currentValues: string[];
  defaultValue?: string;
  appendVerified: boolean;
}

export interface EditableCapability {
  capabilityId: string;
  block: string;
  construct: string;
  occurrence: number;
  line: number;
  parameters: EditableParameter[];
}

export function editableCapabilities(
  records: QueryCapabilityRecord[],
  capabilities: CapabilitiesResponse,
): EditableCapability[] {
  const manifest = new Map(
    capabilities.capabilities.operational_manifest.map((item) => [item.id, item]),
  );
  const result: EditableCapability[] = [];
  for (const record of records) {
    const definition = manifest.get(record.capability_id);
    if (!definition || record.location.source !== "<root>" || definition.operations.modify !== "verified") {
      continue;
    }
    const isSolver = definition.id === "block.solver";
    if (!definition.parent && !isSolver) {
      continue;
    }
    const editDefinitions = new Map(
      (definition.parameter_edits ?? []).map((item) => [item.name, item]),
    );
    const names = new Set(Object.keys(record.parameters));
    for (const item of definition.parameter_edits ?? []) {
      if (item.operations.insert === "verified") names.add(item.name);
    }
    if (definition.id === "construct.boundary-conditions") names.delete("name");
    const parameters = [...names].sort((a, b) => a.localeCompare(b)).map((name) => {
      const values = record.parameters[name] ?? [];
      const defaultValue = record.defaults[name];
      return {
        name,
        currentValues: values.map((item) => item.value),
        defaultValue: defaultValue === undefined ? undefined : String(defaultValue),
        appendVerified: editDefinitions.get(name)?.operations.insert === "verified",
      };
    });
    if (!parameters.length) continue;
    result.push({
      capabilityId: record.capability_id,
      block: definition.parent ?? definition.canonical,
      construct: definition.canonical,
      occurrence: record.occurrence,
      line: record.location.line,
      parameters,
    });
  }
  return result.sort((a, b) => a.line - b.line);
}
