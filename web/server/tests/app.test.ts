// @vitest-environment node

import type { FastifyInstance } from "fastify";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProofResponse } from "../../contracts/index.js";
import { PythonWorkerTimeoutError } from "../src/errors.js";
import { createProofServer } from "../src/app.js";
import { proofRequest, unknownResponse } from "./test-helpers.js";

const openServers: FastifyInstance[] = [];

function track(server: FastifyInstance): FastifyInstance {
  openServers.push(server);
  return server;
}

afterEach(async () => {
  await Promise.all(openServers.splice(0).map((server) => server.close()));
});

describe("proof API", () => {
  it("reports gateway queue state without starting Python", async () => {
    const executor = vi.fn(async () => unknownResponse());
    const server = track(createProofServer({ executor }));

    const response = await server.inject({ method: "GET", url: "/api/health" });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({
      status: "ok",
      activeWorkers: 0,
      queuedRequests: 0,
    });
    expect(response.headers["x-content-type-options"]).toBe("nosniff");
    expect(response.headers["x-frame-options"]).toBe("DENY");
    expect(response.headers["content-security-policy"]).toContain(
      "default-src 'self'",
    );
    expect(executor).not.toHaveBeenCalled();
  });

  it("returns every mathematical outcome with HTTP 200", async () => {
    const executor = vi.fn(async () => unknownResponse());
    const server = track(createProofServer({ executor }));

    const response = await server.inject({
      method: "POST",
      url: "/api/prove",
      payload: proofRequest(),
    });

    expect(response.statusCode).toBe(200);
    expect(response.json().outcome).toBe("UNKNOWN");
    expect(executor).toHaveBeenCalledOnce();
  });

  it.each([
    ["extra request field", { ...proofRequest(), extra: true }],
    ["string degree", { ...proofRequest(), degree: "2" }],
    ["string schema version", { ...proofRequest(), schemaVersion: "1" }],
    [
      "dependent row width",
      {
        ...proofRequest(),
        coefficientRows: [["0"], ["0"], ["0", "0", "0"]],
      },
    ],
    [
      "inexact coefficient",
      {
        ...proofRequest(),
        coefficientRows: [["0.5"], ["0", "0"], ["0", "0", "0"]],
      },
    ],
    [
      "numeric coefficient",
      {
        ...proofRequest(),
        coefficientRows: [[0], ["0", "0"], ["0", "0", "0"]],
      },
    ],
  ])("rejects %s before invoking the worker", async (_label, payload) => {
    const executor = vi.fn(async () => unknownResponse());
    const server = track(createProofServer({ executor }));

    const response = await server.inject({
      method: "POST",
      url: "/api/prove",
      payload,
    });

    expect(response.statusCode).toBe(400);
    expect(response.json().error.code).toBe("invalid_request");
    expect(executor).not.toHaveBeenCalled();
  });

  it("maps a worker deadline to a transport-level timeout", async () => {
    const server = track(
      createProofServer({
        executor: async () => {
          throw new PythonWorkerTimeoutError();
        },
      }),
    );

    const response = await server.inject({
      method: "POST",
      url: "/api/prove",
      payload: proofRequest(),
    });

    expect(response.statusCode).toBe(504);
    expect(response.json()).toEqual({
      error: {
        code: "proof_timeout",
        message: "The proof backend did not finish within the request time limit.",
      },
    });
  });

  it("rejects a malformed executor result as a backend protocol error", async () => {
    const server = track(
      createProofServer({
        executor: async () => ({ outcome: "PROVED" }) as ProofResponse,
      }),
    );

    const response = await server.inject({
      method: "POST",
      url: "/api/prove",
      payload: proofRequest(),
    });

    expect(response.statusCode).toBe(502);
    expect(response.json().error.code).toBe("backend_protocol_error");
  });

  it("rejects excess work when no queue slots remain", async () => {
    let release!: (response: ProofResponse) => void;
    const running = new Promise<ProofResponse>((resolve) => {
      release = resolve;
    });
    const executor = vi.fn(async () => running);
    const server = track(
      createProofServer({
        executor,
        queue: { concurrency: 1, maximumQueued: 0 },
      }),
    );
    const first = server.inject({
      method: "POST",
      url: "/api/prove",
      payload: proofRequest(),
    });
    await vi.waitFor(() => expect(executor).toHaveBeenCalledOnce());

    const second = await server.inject({
      method: "POST",
      url: "/api/prove",
      payload: proofRequest(),
    });

    expect(second.statusCode).toBe(503);
    expect(second.headers["retry-after"]).toBe("1");
    expect(second.json().error.code).toBe("proof_queue_full");
    release(unknownResponse());
    expect((await first).statusCode).toBe(200);
  });

  it("enforces the body limit and JSON content type", async () => {
    const executor = vi.fn(async () => unknownResponse());
    const server = track(createProofServer({ executor, bodyLimitBytes: 128 }));
    const oversized = await server.inject({
      method: "POST",
      url: "/api/prove",
      headers: { "content-type": "application/json" },
      payload: JSON.stringify({ padding: "x".repeat(512) }),
    });
    const wrongType = await server.inject({
      method: "POST",
      url: "/api/prove",
      headers: { "content-type": "text/plain" },
      payload: "plain text",
    });

    expect(oversized.statusCode).toBe(413);
    expect(oversized.json().error.code).toBe("request_too_large");
    expect(wrongType.statusCode).toBe(415);
    expect(wrongType.json().error.code).toBe("unsupported_media_type");
    expect(executor).not.toHaveBeenCalled();
  });

  it("returns a stable not-found error", async () => {
    const server = track(createProofServer({ executor: async () => unknownResponse() }));

    const response = await server.inject({ method: "GET", url: "/missing" });

    expect(response.statusCode).toBe(404);
    expect(response.json()).toEqual({
      error: { code: "not_found", message: "Route not found." },
    });
  });
});
