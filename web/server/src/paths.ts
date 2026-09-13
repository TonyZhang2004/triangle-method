import { existsSync } from "node:fs";
import path from "node:path";

function isRepositoryRoot(candidate: string): boolean {
  return (
    existsSync(path.join(candidate, "pyproject.toml")) &&
    existsSync(path.join(candidate, "src", "triangle_method"))
  );
}

/** Walk upward from runtime locations until the Python repository markers are found. */
export function locateProjectRoot(startingDirectories: readonly string[]): string {
  for (const startingDirectory of startingDirectories) {
    let candidate = path.resolve(startingDirectory);
    while (true) {
      if (isRepositoryRoot(candidate)) {
        return candidate;
      }
      const parent = path.dirname(candidate);
      if (parent === candidate) {
        break;
      }
      candidate = parent;
    }
  }
  throw new Error("Could not locate the Triangle Method repository root.");
}

/** Return the Vite build directory served by the compiled Node application. */
export function compiledClientRoot(projectRoot: string): string {
  return path.join(path.resolve(projectRoot), "web", "dist", "client");
}
