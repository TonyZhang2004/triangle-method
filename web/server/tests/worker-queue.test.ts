// @vitest-environment node

import { describe, expect, it, vi } from "vitest";

import { QueueClosedError, QueueFullError, RequestAbortedError } from "../src/errors.js";
import { ProofWorkerQueue } from "../src/worker-queue.js";
import { proofRequest, provedResponse } from "./test-helpers.js";

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("ProofWorkerQueue", () => {
  it("honors concurrency and rejects work beyond the queue bound", async () => {
    const first = deferred<ReturnType<typeof provedResponse>>();
    const second = deferred<ReturnType<typeof provedResponse>>();
    let call = 0;
    let active = 0;
    let maximumActive = 0;
    const executor = vi.fn(async () => {
      call += 1;
      active += 1;
      maximumActive = Math.max(maximumActive, active);
      try {
        return await (call === 1 ? first.promise : second.promise);
      } finally {
        active -= 1;
      }
    });
    const queue = new ProofWorkerQueue(executor, {
      concurrency: 1,
      maximumQueued: 1,
    });

    const firstResult = queue.submit(proofRequest());
    const secondResult = queue.submit(proofRequest());
    const rejectedResult = queue.submit(proofRequest());

    await expect(rejectedResult).rejects.toBeInstanceOf(QueueFullError);
    expect(executor).toHaveBeenCalledTimes(1);
    expect(queue.activeCount).toBe(1);
    expect(queue.queuedCount).toBe(1);

    first.resolve(provedResponse());
    await expect(firstResult).resolves.toEqual(provedResponse());
    await vi.waitFor(() => expect(executor).toHaveBeenCalledTimes(2));
    second.resolve(provedResponse());
    await expect(secondResult).resolves.toEqual(provedResponse());
    expect(maximumActive).toBe(1);
  });

  it("removes an aborted request while it is waiting", async () => {
    const first = deferred<ReturnType<typeof provedResponse>>();
    const executor = vi.fn(async () => first.promise);
    const queue = new ProofWorkerQueue(executor, {
      concurrency: 1,
      maximumQueued: 1,
    });
    const active = queue.submit(proofRequest());
    const controller = new AbortController();
    const waiting = queue.submit(proofRequest(), controller.signal);

    expect(queue.queuedCount).toBe(1);
    controller.abort();

    await expect(waiting).rejects.toBeInstanceOf(RequestAbortedError);
    expect(queue.queuedCount).toBe(0);
    first.resolve(provedResponse());
    await active;
  });

  it("forwards cancellation to an active executor", async () => {
    const executor = vi.fn(
      async (_request: unknown, signal: AbortSignal) =>
        new Promise<ReturnType<typeof provedResponse>>((_resolve, reject) => {
          signal.addEventListener(
            "abort",
            () => reject(new RequestAbortedError()),
            { once: true },
          );
        }),
    );
    const queue = new ProofWorkerQueue(executor);
    const controller = new AbortController();
    const result = queue.submit(proofRequest(), controller.signal);

    controller.abort();

    await expect(result).rejects.toBeInstanceOf(RequestAbortedError);
    await vi.waitFor(() => expect(queue.activeCount).toBe(0));
  });

  it("rejects waiting work and aborts active work when closed", async () => {
    const executor = vi.fn(
      async (_request: unknown, signal: AbortSignal) =>
        new Promise<ReturnType<typeof provedResponse>>((_resolve, reject) => {
          signal.addEventListener(
            "abort",
            () => reject(new RequestAbortedError()),
            { once: true },
          );
        }),
    );
    const queue = new ProofWorkerQueue(executor, {
      concurrency: 1,
      maximumQueued: 1,
    });
    const active = queue.submit(proofRequest());
    const waiting = queue.submit(proofRequest());

    queue.close();

    await expect(waiting).rejects.toBeInstanceOf(QueueClosedError);
    await expect(active).rejects.toBeInstanceOf(RequestAbortedError);
    await expect(queue.submit(proofRequest())).rejects.toBeInstanceOf(
      QueueClosedError,
    );
  });

  it("rejects malformed capacity options", () => {
    const executor = async () => provedResponse();

    expect(
      () => new ProofWorkerQueue(executor, { concurrency: 0 }),
    ).toThrow(RangeError);
    expect(
      () => new ProofWorkerQueue(executor, { maximumQueued: -1 }),
    ).toThrow(RangeError);
  });
});
