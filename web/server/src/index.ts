import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { createProofServer } from "./app.js";
import { compiledClientRoot, locateProjectRoot } from "./paths.js";

function parsePort(value: string | undefined): number {
  if (value === undefined) {
    return 3000;
  }
  const port = Number(value);
  if (!Number.isInteger(port) || port < 1 || port > 65_535) {
    throw new Error("PORT must be an integer from 1 through 65535");
  }
  return port;
}

/** Start the local Fastify gateway and close it cleanly on process signals. */
async function main(): Promise<void> {
  const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
  const projectRoot = locateProjectRoot([moduleDirectory, process.cwd()]);
  const clientRoot = compiledClientRoot(projectRoot);
  const server = createProofServer({
    logger: true,
    staticRoot: existsSync(clientRoot) ? clientRoot : undefined,
  });
  const close = () => {
    void server.close();
  };
  process.once("SIGINT", close);
  process.once("SIGTERM", close);
  await server.listen({
    host: "127.0.0.1",
    port: parsePort(process.env.PORT),
  });
}

void main();
