import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { parse } from "yaml";

test("foundation CI uses pinned actions and the credential-free root workflow", () => {
  const source = readFileSync(".github/workflows/validate.yml", "utf8");
  const workflow = parse(source);
  assert.deepEqual(Object.keys(workflow.on).sort(), [
    "pull_request",
    "push",
    "workflow_dispatch",
  ]);
  assert.deepEqual(workflow.permissions, { contents: "read" });
  assert.equal(workflow.concurrency["cancel-in-progress"], true);
  const job = workflow.jobs.validate;
  assert.equal(job["runs-on"], "ubuntu-24.04");
  assert.equal(job["timeout-minutes"], 30);
  assert.equal(job.env.AWS_EC2_METADATA_DISABLED, "true");
  assert.equal(job.services, undefined);
  for (const step of job.steps) {
    if (step.uses) assert.match(step.uses, /^[\w-]+\/[\w-]+@[0-9a-f]{40}$/);
  }
  assert.equal(job.steps[0].with["persist-credentials"], false);
  const commands = job.steps.map((step) => step.run);
  assert.ok(
    commands.indexOf("scripts/bootstrap") <
      commands.indexOf("scripts/validate"),
  );
  assert.ok(commands.includes("git diff --exit-code"));
  assert.deepEqual(job.steps.at(-1), {
    name: "Stop local services without deleting volumes",
    if: "always()",
    run: "scripts/local-down",
  });
  assert.doesNotMatch(
    source,
    /secrets\.|id-token|pull_request_target|cdk deploy/,
  );
});
