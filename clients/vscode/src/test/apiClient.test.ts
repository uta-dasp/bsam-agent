import assert from "node:assert/strict";
import { createServer, Server } from "node:http";
import test from "node:test";
import { BsamApiClient, BsamApiError } from "../apiClient";

async function listeningServer(): Promise<{ server: Server; port: number }> {
  const server = createServer((request, response) => {
    response.setHeader("Content-Type", "application/json");
    if (request.url === "/api/v1/health") {
      response.end(JSON.stringify({
        status: "ok",
        api_version: "0.4.0",
        workspace_root: "C:\\workspace",
        max_request_bytes: 1_048_576,
      }));
      return;
    }
    if (request.url === "/api/v1/tools/validate_model") {
      response.statusCode = 400;
      response.end(JSON.stringify({ error: { code: "invalid_arguments", message: "bad source" } }));
      return;
    }
    response.statusCode = 404;
    response.end(JSON.stringify({ error: { code: "not_found", message: "missing" } }));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert(address && typeof address === "object");
  return { server, port: address.port };
}

test("reads the workspace-bound health contract", async () => {
  const { server, port } = await listeningServer();
  try {
    const health = await new BsamApiClient(port, 1000).health();
    assert.equal(health.api_version, "0.4.0");
    assert.equal(health.workspace_root, "C:\\workspace");
  } finally {
    server.close();
  }
});

test("normalizes deterministic API errors", async () => {
  const { server, port } = await listeningServer();
  try {
    await assert.rejects(
      new BsamApiClient(port, 1000).invoke("validate_model", { source: "bad.in" }),
      (error: unknown) => error instanceof BsamApiError
        && error.code === "invalid_arguments"
        && error.status === 400,
    );
  } finally {
    server.close();
  }
});

test("rejects unsafe tool-route names before transport", async () => {
  const client = new BsamApiClient(8765, 1000);
  assert.throws(() => client.invoke("../health", {}), /Invalid BSAM tool name/);
});
