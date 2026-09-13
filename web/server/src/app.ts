import Fastify, {
  type FastifyError,
  type FastifyInstance,
  type FastifyServerOptions,
} from "fastify";
import fastifyStatic from "@fastify/static";

import {
  ContractValidationError,
  type ProofRequest,
  type ProofResponse,
  parseProofRequest,
  parseProofResponse,
  proofRequestJsonSchema,
} from "../../contracts/index.js";
import {
  GatewayError,
  PythonWorkerProtocolError,
  RequestAbortedError,
} from "./errors.js";
import { createPythonProofExecutor } from "./python-worker.js";
import {
  type ProofExecutor,
  ProofWorkerQueue,
  type ProofWorkerQueueOptions,
} from "./worker-queue.js";

const DEFAULT_BODY_LIMIT_BYTES = 16 * 1024;

export interface CreateProofServerOptions {
  executor?: ProofExecutor;
  queue?: ProofWorkerQueueOptions;
  bodyLimitBytes?: number;
  logger?: FastifyServerOptions["logger"];
  staticRoot?: string;
}

export interface ErrorPayload {
  error: {
    code: string;
    message: string;
  };
}

const errorJsonSchema = {
  type: "object",
  additionalProperties: false,
  required: ["error"],
  properties: {
    error: {
      type: "object",
      additionalProperties: false,
      required: ["code", "message"],
      properties: {
        code: { type: "string" },
        message: { type: "string" },
      },
    },
  },
} as const;

function positiveInteger(value: number, name: string): number {
  if (!Number.isInteger(value) || value < 1) {
    throw new RangeError(`${name} must be a positive integer`);
  }
  return value;
}

function errorPayload(code: string, message: string): ErrorPayload {
  return { error: { code, message } };
}

function isFastifyValidationError(error: FastifyError): boolean {
  return Array.isArray(error.validation);
}

/** Construct the API server with an injectable executor for isolated route tests. */
export function createProofServer(
  options: CreateProofServerOptions = {},
): FastifyInstance {
  const bodyLimit = positiveInteger(
    options.bodyLimitBytes ?? DEFAULT_BODY_LIMIT_BYTES,
    "bodyLimitBytes",
  );
  const server = Fastify({
    logger: options.logger ?? false,
    bodyLimit,
    ajv: {
      customOptions: {
        coerceTypes: false,
        removeAdditional: false,
        useDefaults: false,
      },
    },
  });
  server.addHook("onSend", async (_request, reply, payload) => {
    reply.headers({
      "content-security-policy": [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "font-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
      ].join("; "),
      "cross-origin-resource-policy": "same-origin",
      "permissions-policy": "camera=(), microphone=(), geolocation=()",
      "referrer-policy": "no-referrer",
      "x-content-type-options": "nosniff",
      "x-frame-options": "DENY",
    });
    return payload;
  });
  const queue = new ProofWorkerQueue(
    options.executor ?? createPythonProofExecutor(),
    options.queue,
  );

  if (options.staticRoot !== undefined) {
    void server.register(fastifyStatic, {
      root: options.staticRoot,
      prefix: "/",
    });
  }

  server.get(
    "/api/health",
    {
      schema: {
        response: {
          200: {
            type: "object",
            additionalProperties: false,
            required: ["status", "activeWorkers", "queuedRequests"],
            properties: {
              status: { const: "ok" },
              activeWorkers: { type: "integer", minimum: 0 },
              queuedRequests: { type: "integer", minimum: 0 },
            },
          },
        },
      },
    },
    async () => ({
      status: "ok" as const,
      activeWorkers: queue.activeCount,
      queuedRequests: queue.queuedCount,
    }),
  );

  server.post<{ Body: ProofRequest }>(
    "/api/prove",
    {
      schema: {
        body: proofRequestJsonSchema,
        response: {
          400: errorJsonSchema,
          413: errorJsonSchema,
          415: errorJsonSchema,
          429: errorJsonSchema,
          499: errorJsonSchema,
          500: errorJsonSchema,
          502: errorJsonSchema,
          503: errorJsonSchema,
          504: errorJsonSchema,
        },
      },
      onRequest: async (request) => {
        const contentType = request.headers["content-type"]
          ?.split(";", 1)[0]
          .trim()
          .toLowerCase();
        if (contentType !== "application/json") {
          throw new GatewayError(
            "unsupported_media_type",
            "Requests must use application/json.",
            415,
          );
        }
      },
    },
    async (request, reply) => {
      const parsedRequest = parseProofRequest(request.body);
      const cancellation = new AbortController();
      const abort = () => cancellation.abort();
      const abortOnClosedSocket = () => {
        if (!reply.raw.writableEnded) {
          cancellation.abort();
        }
      };
      request.raw.once("aborted", abort);
      reply.raw.once("close", abortOnClosedSocket);

      try {
        const workerResponse = await queue.submit(
          parsedRequest,
          cancellation.signal,
        );
        if (cancellation.signal.aborted) {
          throw new RequestAbortedError();
        }
        // Revalidate injected executors as well as the production subprocess adapter.
        let response: ProofResponse;
        try {
          response = parseProofResponse(workerResponse);
        } catch (error) {
          throw new PythonWorkerProtocolError(
            "executor response failed contract validation",
            error,
          );
        }
        return await reply.code(200).send(response);
      } finally {
        request.raw.removeListener("aborted", abort);
        reply.raw.removeListener("close", abortOnClosedSocket);
      }
    },
  );

  server.setNotFoundHandler(async (_request, reply) =>
    reply.code(404).send(errorPayload("not_found", "Route not found.")),
  );

  server.setErrorHandler(async (rawError, request, reply) => {
    const error = rawError as FastifyError;
    if (request.raw.aborted || reply.raw.destroyed) {
      return;
    }

    if (error instanceof ContractValidationError || isFastifyValidationError(error)) {
      return await reply
        .code(400)
        .send(errorPayload("invalid_request", error.message));
    }
    if (error.code === "FST_ERR_CTP_BODY_TOO_LARGE") {
      return await reply
        .code(413)
        .send(errorPayload("request_too_large", "The request body is too large."));
    }
    if (error.code === "FST_ERR_CTP_INVALID_MEDIA_TYPE") {
      return await reply.code(415).send(
        errorPayload(
          "unsupported_media_type",
          "Requests must use application/json.",
        ),
      );
    }
    if (error.statusCode === 400) {
      return await reply
        .code(400)
        .send(errorPayload("invalid_request", "The request body is invalid."));
    }
    if (error instanceof GatewayError) {
      if (error.statusCode === 503 && error.code === "proof_queue_full") {
        reply.header("retry-after", "1");
      }
      if (error.statusCode >= 500) {
        request.log.error({ err: error }, "proof gateway failure");
      }
      return await reply
        .code(error.statusCode)
        .send(errorPayload(error.code, error.message));
    }

    request.log.error({ err: error }, "unexpected proof server failure");
    return await reply.code(500).send(
      errorPayload(
        "internal_error",
        "The proof service encountered an unexpected error.",
      ),
    );
  });

  server.addHook("onClose", async () => {
    queue.close();
  });

  return server;
}
