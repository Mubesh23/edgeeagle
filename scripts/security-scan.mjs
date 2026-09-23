import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

export function scanDependencies(run = execFileSync) {
  const failures = [];
  try {
    run("corepack", ["pnpm", "audit", "--audit-level", "low"], {
      stdio: "inherit",
      timeout: 180_000,
    });
  } catch {
    failures.push("pnpm audit (finding, timeout, or service/tool failure)");
  }
  const directory = mkdtempSync(join(tmpdir(), "edgeeagle-security-"));
  try {
    const requirements = run(
      "uv",
      [
        "export",
        "--locked",
        "--offline",
        "--all-packages",
        "--all-groups",
        "--no-emit-workspace",
        "--no-annotate",
        "--no-header",
      ],
      { encoding: "utf8", timeout: 30_000 },
    );
    if (
      typeof requirements !== "string" ||
      !/^[A-Za-z0-9][A-Za-z0-9._-]*==/m.test(requirements)
    ) {
      throw new Error("The exported dependency inventory is empty or invalid");
    }
    const path = join(directory, "requirements.txt");
    writeFileSync(path, requirements, { mode: 0o600 });
    run(
      "uv",
      [
        "run",
        "--locked",
        "--offline",
        "--all-packages",
        "pip-audit",
        "--strict",
        "--disable-pip",
        "--require-hashes",
        "--progress-spinner",
        "off",
        "--timeout",
        "20",
        "--requirement",
        path,
      ],
      { stdio: "inherit", timeout: 180_000 },
    );
  } catch {
    failures.push(
      "Python lock export / pip-audit (finding, timeout, or service/tool failure)",
    );
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
  return failures;
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  const failures = scanDependencies();
  if (failures.length) {
    console.error(`Dependency security scan failed:\n${failures.join("\n")}`);
    process.exitCode = 1;
  } else {
    console.log(
      "Dependency security scans passed; no known advisories reported.",
    );
  }
}
