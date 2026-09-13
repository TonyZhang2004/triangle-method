import type { ProofRequest, ProofResponse } from "../../contracts/index.js";
import {
  QueueClosedError,
  QueueFullError,
  RequestAbortedError,
} from "./errors.js";

export type ProofExecutor = (
  request: ProofRequest,
  signal: AbortSignal,
) => Promise<ProofResponse>;

export interface ProofWorkerQueueOptions {
  concurrency?: number;
  maximumQueued?: number;
}

interface PendingJob {
  request: ProofRequest;
  signal: AbortSignal | undefined;
  resolve: (response: ProofResponse) => void;
  reject: (error: unknown) => void;
  onAbort: (() => void) | undefined;
}

const DEFAULT_CONCURRENCY = 2;
const DEFAULT_MAXIMUM_QUEUED = 16;

function requirePositiveInteger(value: number, name: string): void {
  if (!Number.isInteger(value) || value < 1) {
    throw new RangeError(`${name} must be a positive integer`);
  }
}

function requireNonnegativeInteger(value: number, name: string): void {
  if (!Number.isInteger(value) || value < 0) {
    throw new RangeError(`${name} must be a nonnegative integer`);
  }
}

/** Bound proof-process concurrency, queue depth, cancellation, and shutdown. */
export class ProofWorkerQueue {
  readonly concurrency: number;
  readonly maximumQueued: number;

  #activeCount = 0;
  #closed = false;
  #executor: ProofExecutor;
  #pending: PendingJob[] = [];
  #activeControllers = new Set<AbortController>();

  constructor(executor: ProofExecutor, options: ProofWorkerQueueOptions = {}) {
    this.concurrency = options.concurrency ?? DEFAULT_CONCURRENCY;
    this.maximumQueued = options.maximumQueued ?? DEFAULT_MAXIMUM_QUEUED;
    requirePositiveInteger(this.concurrency, "concurrency");
    requireNonnegativeInteger(this.maximumQueued, "maximumQueued");
    this.#executor = executor;
  }

  get activeCount(): number {
    return this.#activeCount;
  }

  get queuedCount(): number {
    return this.#pending.length;
  }

  get closed(): boolean {
    return this.#closed;
  }

  /** Enqueue one validated request or reject immediately when capacity is spent. */
  submit(request: ProofRequest, signal?: AbortSignal): Promise<ProofResponse> {
    if (this.#closed) {
      return Promise.reject(new QueueClosedError());
    }
    if (signal?.aborted) {
      return Promise.reject(new RequestAbortedError());
    }
    if (
      this.#activeCount >= this.concurrency &&
      this.#pending.length >= this.maximumQueued
    ) {
      return Promise.reject(new QueueFullError());
    }

    return new Promise<ProofResponse>((resolve, reject) => {
      const job: PendingJob = {
        request,
        signal,
        resolve,
        reject,
        onAbort: undefined,
      };
      if (signal !== undefined) {
        job.onAbort = () => {
          const index = this.#pending.indexOf(job);
          if (index !== -1) {
            this.#pending.splice(index, 1);
            reject(new RequestAbortedError());
          }
        };
        signal.addEventListener("abort", job.onAbort, { once: true });
      }
      this.#pending.push(job);
      this.#drain();
    });
  }

  /** Reject queued work and abort active workers during Fastify shutdown. */
  close(): void {
    if (this.#closed) {
      return;
    }
    this.#closed = true;
    for (const job of this.#pending.splice(0)) {
      if (job.onAbort !== undefined && job.signal !== undefined) {
        job.signal.removeEventListener("abort", job.onAbort);
      }
      job.reject(new QueueClosedError());
    }
    for (const controller of this.#activeControllers) {
      controller.abort();
    }
  }

  #drain(): void {
    while (
      !this.#closed &&
      this.#activeCount < this.concurrency &&
      this.#pending.length > 0
    ) {
      const job = this.#pending.shift();
      if (job === undefined) {
        return;
      }
      if (job.onAbort !== undefined && job.signal !== undefined) {
        job.signal.removeEventListener("abort", job.onAbort);
      }
      if (job.signal?.aborted) {
        job.reject(new RequestAbortedError());
        continue;
      }
      this.#start(job);
    }
  }

  #start(job: PendingJob): void {
    this.#activeCount += 1;
    const controller = new AbortController();
    this.#activeControllers.add(controller);
    const onAbort = () => controller.abort();
    job.signal?.addEventListener("abort", onAbort, { once: true });

    void this.#executor(job.request, controller.signal)
      .then(job.resolve, job.reject)
      .finally(() => {
        job.signal?.removeEventListener("abort", onAbort);
        this.#activeControllers.delete(controller);
        this.#activeCount -= 1;
        this.#drain();
      });
  }
}
