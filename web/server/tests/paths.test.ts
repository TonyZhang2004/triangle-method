// @vitest-environment node

import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { compiledClientRoot, locateProjectRoot } from "../src/paths.js";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);

describe("production path resolution", () => {
  it("finds the repository from the source module directory", () => {
    const sourceModuleDirectory = path.join(repositoryRoot, "web", "server", "src");

    expect(locateProjectRoot([sourceModuleDirectory])).toBe(repositoryRoot);
  });

  it("finds the repository from the deeper compiled server directory", () => {
    const compiledModuleDirectory = path.join(
      repositoryRoot,
      "web",
      "dist",
      "server",
      "server",
      "src",
    );

    expect(locateProjectRoot([compiledModuleDirectory])).toBe(repositoryRoot);
  });

  it("targets the Vite client build beside the compiled server tree", () => {
    expect(compiledClientRoot(repositoryRoot)).toBe(
      path.join(repositoryRoot, "web", "dist", "client"),
    );
  });

  it("fails clearly when no supplied path belongs to the repository", () => {
    expect(() => locateProjectRoot([path.parse(repositoryRoot).root])).toThrow(
      "Could not locate",
    );
  });
});
