import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";
import { format } from "prettier";

const root = fileURLToPath(new URL("..", import.meta.url));
const paths = [
  "contracts/openapi/edgeeagle.json",
  "libs/typescript/api-client/src/generated/schema.ts",
];

export async function generateContracts({
  outputRoot = root,
  check = false,
} = {}) {
  const schema = JSON.parse(
    execFileSync(
      "uv",
      [
        "run",
        "--locked",
        "--offline",
        "--package",
        "edgeeagle-api",
        "python",
        "-m",
        "edgeeagle_api.export_openapi",
      ],
      { cwd: root, encoding: "utf8" },
    ),
  );
  // Keep this generation path local even if a future schema introduces references.
  function rejectExternalReferences(value) {
    if (!value || typeof value !== "object") return;
    for (const [key, child] of Object.entries(value)) {
      if (
        key === "$ref" &&
        (typeof child !== "string" || !child.startsWith("#/"))
      ) {
        throw new Error(
          "Contract generation supports local fragment references only",
        );
      }
      rejectExternalReferences(child);
    }
  }
  rejectExternalReferences(schema);
  const artifacts = [
    await format(JSON.stringify(schema), { parser: "json" }),
    await format(
      "/** Generated from FastAPI via scripts/generate-contracts. Do not edit. */\n" +
        astToString(await openapiTS(schema)),
      { parser: "typescript" },
    ),
  ];
  const stale = [];
  for (const [index, path] of paths.entries()) {
    const target = resolve(outputRoot, path);
    if (check) {
      const existing = await readFile(target, "utf8").catch((error) => {
        if (error.code === "ENOENT") return undefined;
        throw error;
      });
      if (existing !== artifacts[index]) stale.push(path);
    } else {
      await mkdir(dirname(target), { recursive: true });
      await writeFile(target, artifacts[index]);
    }
  }
  if (stale.length) {
    throw new Error(
      `Generated contract drift: ${stale.join(", ")}. Run scripts/generate-contracts.`,
    );
  }
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  const args = process.argv.slice(2);
  if (args.some((arg) => arg !== "--check") || args.length > 1) {
    throw new Error("Usage: node scripts/generate-contracts.mjs [--check]");
  }
  await generateContracts({ check: args.includes("--check") });
  console.log(
    args.includes("--check")
      ? "Generated contracts are current."
      : "Generated OpenAPI and TypeScript types.",
  );
}
