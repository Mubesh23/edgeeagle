import { readdirSync, readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";

process.chdir(fileURLToPath(new URL("..", import.meta.url)));

function filesUnder(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = `${directory}/${entry.name}`;
    return entry.isDirectory() ? filesUnder(path) : [path];
  });
}

const manifest = JSON.parse(readFileSync("package.json", "utf8"));
assert.equal(manifest.private, true, "Root workspace must not be published");
assert.match(manifest.packageManager, /^pnpm@\d+\.\d+\.\d+$/);
assert.equal(readFileSync("CLAUDE.md", "utf8").trim(), "@AGENTS.md");

let links = 0;
for (const file of ["README.md", "AGENTS.md", ...filesUnder("docs")]) {
  if (!file.endsWith(".md")) continue;
  for (const match of readFileSync(file, "utf8").matchAll(/\]\(([^)]+)\)/g)) {
    const target = match[1];
    if (/^(https?:|#)/.test(target)) continue;
    assert.ok(
      existsSync(resolve(dirname(file), target.split("#")[0])),
      `Broken documentation link in ${file}: ${target}`,
    );
    links++;
  }
}
console.log(
  `Workspace invariants and ${links} local documentation links passed.`,
);
