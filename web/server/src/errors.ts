/** Typed gateway failures with stable public codes and HTTP status mappings. */

export class GatewayError extends Error {
  readonly code: string;
  readonly statusCode: number;
  readonly expose: boolean;

  constructor(
    code: string,
    message: string,
    statusCode: number,
    options: { cause?: unknown; expose?: boolean } = {},
  ) {
    super(message, options.cause === undefined ? undefined : { cause: options.cause });
    this.name = new.target.name;
    this.code = code;
    this.statusCode = statusCode;
    this.expose = options.expose ?? true;
  }
}

export class QueueFullError extends GatewayError {
  constructor() {
    super(
      "proof_queue_full",
      "The proof service is busy. Please try again shortly.",
      503,
    );
  }
}

export class QueueClosedError extends GatewayError {
  constructor() {
    super("proof_service_stopping", "The proof service is stopping.", 503);
  }
}

export class RequestAbortedError extends GatewayError {
  constructor() {
    super("request_aborted", "The request was cancelled.", 499);
  }
}

export class PythonWorkerTimeoutError extends GatewayError {
  constructor() {
    super(
      "proof_timeout",
      "The proof backend did not finish within the request time limit.",
      504,
    );
  }
}

export class PythonWorkerOutputLimitError extends GatewayError {
  constructor(stream: "stdout" | "stderr") {
    super(
      "backend_output_limit",
      "The proof backend produced an invalid oversized response.",
      502,
      { cause: new Error(`${stream} exceeded its configured byte limit`) },
    );
  }
}

export class PythonWorkerUnavailableError extends GatewayError {
  constructor(cause: unknown) {
    super(
      "backend_unavailable",
      "The proof backend could not be started.",
      503,
      { cause },
    );
  }
}

export class PythonWorkerProtocolError extends GatewayError {
  constructor(detail: string, cause?: unknown) {
    super(
      "backend_protocol_error",
      "The proof backend returned an invalid response.",
      502,
      { cause: cause ?? new Error(detail) },
    );
  }
}

export class PythonWorkerExitError extends GatewayError {
  readonly exitCode: number | null;
  readonly stderr: string;

  constructor(exitCode: number | null, stderr: string) {
    super(
      "backend_failed",
      "The proof backend could not complete this request.",
      502,
      {
        cause: new Error(
          `Python worker exited with ${exitCode ?? "no status"}: ${stderr || "no error output"}`,
        ),
      },
    );
    this.exitCode = exitCode;
    this.stderr = stderr;
  }
}
