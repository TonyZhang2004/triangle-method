import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

import {
  type ProofRequest,
  type ProofResponse,
  type RationalRecord,
  parseProofResponse,
} from "../../contracts/index.js";
import {
  PythonWorkerExitError,
  PythonWorkerOutputLimitError,
  PythonWorkerProtocolError,
  PythonWorkerTimeoutError,
  PythonWorkerUnavailableError,
  RequestAbortedError,
} from "./errors.js";
import type { ProofExecutor } from "./worker-queue.js";
import { locateProjectRoot } from "./paths.js";

const DEFAULT_TIMEOUT_MILLISECONDS = 12_000;
const DEFAULT_STDOUT_LIMIT_BYTES = 1024 * 1024;
const DEFAULT_STDERR_LIMIT_BYTES = 64 * 1024;

export interface WorkerCommand {
  executable: string;
  arguments: readonly string[];
}

export interface PythonProofExecutorOptions {
  projectRoot?: string;
  timeoutMilliseconds?: number;
  stdoutLimitBytes?: number;
  stderrLimitBytes?: number;
  /** Test seam; production callers omit this fixed-command override. */
  command?: WorkerCommand;
}

function positiveInteger(value: number, name: string): number {
  if (!Number.isInteger(value) || value < 1) {
    throw new RangeError(`${name} must be a positive integer`);
  }
  return value;
}

function defaultProjectRoot(): string {
  const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
  return locateProjectRoot([moduleDirectory, process.cwd()]);
}

function defaultCommand(projectRoot: string): WorkerCommand {
  return {
    executable: path.join(projectRoot, ".venv", "bin", "python"),
    arguments: ["-m", "triangle_method.web_adapter"],
  };
}

function workerEnvironment(projectRoot: string): NodeJS.ProcessEnv {
  const environment: NodeJS.ProcessEnv = {
    PYTHONPATH: path.join(projectRoot, "src"),
    PYTHONDONTWRITEBYTECODE: "1",
    PYTHONUNBUFFERED: "1",
  };
  for (const name of ["PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"] as const) {
    const value = process.env[name];
    if (value !== undefined) {
      environment[name] = value;
    }
  }
  return environment;
}

function requestCoefficientParts(value: string): [bigint, bigint] {
  const [rawNumerator, rawDenominator] = value.split("/");
  return [BigInt(rawNumerator), BigInt(rawDenominator ?? "1")];
}

function equalRationals(left: string, right: RationalRecord): boolean {
  const [leftNumerator, leftDenominator] = requestCoefficientParts(left);
  const rightNumerator = BigInt(right.numerator);
  const rightDenominator = BigInt(right.denominator);
  return leftNumerator * rightDenominator === rightNumerator * leftDenominator;
}

function requireMatchingTarget(
  request: ProofRequest,
  response: ProofResponse,
): void {
  if (response.target.degree !== request.degree) {
    throw new PythonWorkerProtocolError(
      "response target degree does not match the request",
    );
  }
  for (let rowIndex = 0; rowIndex < request.coefficientRows.length; rowIndex += 1) {
    for (
      let columnIndex = 0;
      columnIndex < request.coefficientRows[rowIndex].length;
      columnIndex += 1
    ) {
      if (
        !equalRationals(
          request.coefficientRows[rowIndex][columnIndex],
          response.target.coefficientRows[rowIndex][columnIndex],
        )
      ) {
        throw new PythonWorkerProtocolError(
          `response target differs at row ${rowIndex}, column ${columnIndex}`,
        );
      }
    }
  }
}

/** Create the fixed-command, bounded subprocess executor used by the request queue. */
export function createPythonProofExecutor(
  options: PythonProofExecutorOptions = {},
): ProofExecutor {
  const projectRoot = path.resolve(options.projectRoot ?? defaultProjectRoot());
  const timeoutMilliseconds = positiveInteger(
    options.timeoutMilliseconds ?? DEFAULT_TIMEOUT_MILLISECONDS,
    "timeoutMilliseconds",
  );
  const stdoutLimitBytes = positiveInteger(
    options.stdoutLimitBytes ?? DEFAULT_STDOUT_LIMIT_BYTES,
    "stdoutLimitBytes",
  );
  const stderrLimitBytes = positiveInteger(
    options.stderrLimitBytes ?? DEFAULT_STDERR_LIMIT_BYTES,
    "stderrLimitBytes",
  );
  const command = options.command ?? defaultCommand(projectRoot);

  return (request, abortSignal) =>
    new Promise<ProofResponse>((resolve, reject) => {
      if (abortSignal.aborted) {
        reject(new RequestAbortedError());
        return;
      }

      let child;
      try {
        child = spawn(command.executable, [...command.arguments], {
          cwd: projectRoot,
          env: workerEnvironment(projectRoot),
          shell: false,
          stdio: ["pipe", "pipe", "pipe"],
          windowsHide: true,
        });
      } catch (error) {
        reject(new PythonWorkerUnavailableError(error));
        return;
      }

      const stdoutChunks: Buffer[] = [];
      const stderrChunks: Buffer[] = [];
      let stdoutBytes = 0;
      let stderrBytes = 0;
      let settled = false;

      const cleanup = () => {
        clearTimeout(timeout);
        abortSignal.removeEventListener("abort", abort);
      };
      const rejectAndKill = (error: unknown) => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        child.kill("SIGKILL");
        reject(error);
      };
      const abort = () => rejectAndKill(new RequestAbortedError());
      const timeout = setTimeout(
        () => rejectAndKill(new PythonWorkerTimeoutError()),
        timeoutMilliseconds,
      );
      timeout.unref();
      abortSignal.addEventListener("abort", abort, { once: true });

      child.once("error", (error) => {
        rejectAndKill(new PythonWorkerUnavailableError(error));
      });
      child.stdout.on("data", (chunk: Buffer | string) => {
        const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
        stdoutBytes += buffer.byteLength;
        if (stdoutBytes > stdoutLimitBytes) {
          rejectAndKill(new PythonWorkerOutputLimitError("stdout"));
          return;
        }
        stdoutChunks.push(buffer);
      });
      child.stderr.on("data", (chunk: Buffer | string) => {
        const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
        stderrBytes += buffer.byteLength;
        if (stderrBytes > stderrLimitBytes) {
          rejectAndKill(new PythonWorkerOutputLimitError("stderr"));
          return;
        }
        stderrChunks.push(buffer);
      });
      child.stdin.on("error", () => {
        // A worker that exits before consuming stdin is diagnosed from its exit event.
      });
      child.once("close", (exitCode) => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        const stderr = Buffer.concat(stderrChunks).toString("utf8").trim();
        if (exitCode !== 0) {
          reject(new PythonWorkerExitError(exitCode, stderr));
          return;
        }

        const stdout = Buffer.concat(stdoutChunks).toString("utf8").trim();
        let parsed: unknown;
        try {
          parsed = JSON.parse(stdout) as unknown;
        } catch (error) {
          reject(
            new PythonWorkerProtocolError(
              "worker stdout was not one JSON document",
              error,
            ),
          );
          return;
        }
        try {
          const response = parseProofResponse(parsed);
          requireMatchingTarget(request, response);
          resolve(response);
        } catch (error) {
          if (error instanceof PythonWorkerProtocolError) {
            reject(error);
          } else {
            reject(
              new PythonWorkerProtocolError(
                "worker response failed contract validation",
                error,
              ),
            );
          }
        }
      });

      const payload = `${JSON.stringify(request)}\n`;
      child.stdin.end(payload);
    });
}
