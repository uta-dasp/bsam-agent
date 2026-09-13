import assert from "node:assert/strict";
import * as path from "node:path";
import test from "node:test";
import {
  relativeWorkspacePath,
  resolveDiagnosticSource,
  resolveRepositoryRoot,
  sameWorkspaceRoot,
} from "../pathing";

test("binds paths to the configured workspace", () => {
  const root = path.resolve("workspace");
  assert.equal(relativeWorkspacePath(root, path.join(root, "models", "case.in")), "models/case.in");
  assert.throws(() => relativeWorkspacePath(root, path.resolve("outside.in")), /outside/);
});

test("compares resolved workspace roots", () => {
  const root = path.resolve("workspace");
  assert.equal(sameWorkspaceRoot(root, root + path.sep), true);
  assert.equal(sameWorkspaceRoot(root, path.resolve("different")), false);
});

test("maps root and include diagnostic locations", () => {
  const root = path.resolve("workspace");
  const model = path.join(root, "models", "case.in");
  assert.equal(resolveDiagnosticSource(root, model, "<root>"), model);
  assert.equal(resolveDiagnosticSource(root, model, "models/include.in"), path.join(root, "models", "include.in"));
});

test("locates the source repository independently of the installed extension", () => {
  const workspace = path.resolve("D:/work");
  const repository = path.join(workspace, "bsam agent");
  const expectedProbe = path.join(repository, "src", "bsam_agent");
  assert.equal(
    resolveRepositoryRoot(workspace, path.resolve("D:/extensions/client"), "", (candidate) => candidate === expectedProbe),
    repository,
  );
});

test("requires an absolute configured repository root", () => {
  assert.throws(
    () => resolveRepositoryRoot(path.resolve("workspace"), path.resolve("extension"), "relative"),
    /absolute path/,
  );
});
