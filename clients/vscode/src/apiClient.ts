import { ApiErrorBody, CapabilitiesResponse, HealthResponse } from "./types";

export class BsamApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "BsamApiError";
  }
}

export class BsamApiClient {
  private readonly baseUrl: string;

  constructor(
    port: number,
    private readonly timeoutMs: number,
  ) {
    if (!Number.isInteger(port) || port < 1024 || port > 65535) {
      throw new Error("BSAM API port must be an integer from 1024 through 65535");
    }
    this.baseUrl = `http://127.0.0.1:${port}`;
  }

  health(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/api/v1/health", { method: "GET" });
  }

  capabilities(): Promise<CapabilitiesResponse> {
    return this.request<CapabilitiesResponse>("/api/v1/capabilities", { method: "GET" });
  }

  invoke<T>(tool: string, argumentsValue: Record<string, unknown>): Promise<T> {
    if (!/^[a-z][a-z0-9_]*$/.test(tool)) {
      throw new Error(`Invalid BSAM tool name: ${tool}`);
    }
    return this.request<T>(`/api/v1/tools/${tool}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(argumentsValue),
    });
  }

  private async request<T>(route: string, init: RequestInit): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await fetch(this.baseUrl + route, {
        ...init,
        cache: "no-store",
        signal: controller.signal,
      });
      const value = await response.json() as T | ApiErrorBody;
      if (!response.ok) {
        const body = value as ApiErrorBody;
        throw new BsamApiError(
          body.error?.code ?? "http_error",
          body.error?.message ?? `BSAM API returned HTTP ${response.status}`,
          response.status,
        );
      }
      return value as T;
    } catch (error) {
      if (error instanceof BsamApiError) {
        throw error;
      }
      if (error instanceof Error && error.name === "AbortError") {
        throw new BsamApiError("timeout", "BSAM API request timed out");
      }
      const message = error instanceof Error ? error.message : String(error);
      throw new BsamApiError("unavailable", `BSAM API is unavailable: ${message}`);
    } finally {
      clearTimeout(timeout);
    }
  }
}
