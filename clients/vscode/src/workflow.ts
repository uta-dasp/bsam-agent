import * as path from "node:path";

function safeStem(source: string): string {
  const extension = path.extname(source);
  const stem = path.basename(source, extension);
  return stem.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "model";
}

export function timestampToken(now = new Date()): string {
  return now.toISOString().replace(/[-:]/g, "").replace(".", "-");
}

export function defaultPlanPath(source: string, now = new Date()): string {
  return `.bsam-agent/plans/${safeStem(source)}-${timestampToken(now)}.json`;
}

export function defaultChangeDestination(source: string, now = new Date()): string {
  const name = path.basename(source);
  return `.bsam-agent/changes/${safeStem(source)}-${timestampToken(now)}/${name}`;
}

export function defaultRunDirectory(source: string, now = new Date()): string {
  return `.bsam-agent/runs/${safeStem(source)}-${timestampToken(now)}`;
}

export function nonEmpty(value: string | undefined): string | undefined {
  const normalized = value?.trim();
  return normalized ? normalized : undefined;
}
