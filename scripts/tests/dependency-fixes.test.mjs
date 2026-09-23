import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test from "node:test";

const mobileRequire = createRequire(
  fileURLToPath(new URL("../../apps/mobile/package.json", import.meta.url)),
);
const routerRequire = createRequire(
  mobileRequire.resolve("expo-router/package.json"),
);
const query = routerRequire("query-string");

test("patched Expo query parser preserves values, repeated keys, and encoding", () => {
  assert.deepEqual(
    { ...query.parse("name=hello+world&tag=a&tag=b&emoji=%F0%9F%A6%85") },
    {
      emoji: "🦅",
      name: "hello world",
      tag: ["a", "b"],
    },
  );
  assert.equal(
    query.stringify({ name: "hello world", flag: null }),
    "flag&name=hello%20world",
  );
});

test("patched decoder handles a long malformed percent sequence", () => {
  execFileSync(
    process.execPath,
    [
      "-e",
      `
    const assert = require('node:assert/strict');
    const query = require(process.argv[1]);
    assert.equal(typeof query.parse('value=' + '%C0'.repeat(10_000)).value, 'string');
  `,
      routerRequire.resolve("query-string"),
    ],
    { timeout: 5000 },
  );
});

test("Xcode's UUID consumer retains its 24-character uppercase ID API", () => {
  const expoRequire = createRequire(mobileRequire.resolve("expo/package.json"));
  const pluginsRequire = createRequire(
    expoRequire.resolve("@expo/config-plugins"),
  );
  const xcode = pluginsRequire("xcode");
  const project = xcode.project("unused.pbxproj");
  project.hash = { project: { objects: {} } };
  assert.match(project.generateUuid(), /^[0-9A-F]{24}$/);
});
