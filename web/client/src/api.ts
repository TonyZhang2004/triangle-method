import { parseProofResponse } from "../../contracts/index.js";
import type { ProofRequest, ProofResponse } from "./types";

/** Error raised when the proof service fails or returns an invalid response. */
export class ProofServiceError extends Error {}

async function responseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as Record<string, unknown>;
    if (typeof payload.message === "string") return payload.message;
    if (
      typeof payload.error === "object" &&
      payload.error !== null &&
      typeof (payload.error as Record<string, unknown>).message === "string"
    ) {
      return (payload.error as Record<string, string>).message;
    }
  } catch {
    // Fall through to the status-based message when an error body is not JSON.
  }
  return `The proof service returned ${response.status}.`;
}

/** Submit exact coefficient rows and validate the proof service's JSON response. */
export async function requestProof(
  request: ProofRequest,
  signal?: AbortSignal,
): Promise<ProofResponse> {
  let response: Response;
  try {
    response = await fetch("/api/prove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ProofServiceError("The proof service could not be reached.");
  }
  if (!response.ok) {
    throw new ProofServiceError(await responseError(response));
  }
  try {
    return parseProofResponse(await response.json());
  } catch {
    throw new ProofServiceError("The proof service returned an invalid response.");
  }
}

