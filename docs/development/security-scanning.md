# Dependency security gate

`scripts/security-scan` audits the complete pnpm dependency graph, including
development dependencies, with `pnpm audit --audit-level low`. It also exports
all workspace/group dependencies from the frozen uv lock and audits that
inventory with pinned pip-audit 2.10.1. Workspace source packages are excluded
from the public package inventory, not their dependencies. Python environment
markers are evaluated for the running platform: local macOS plus Linux CI do
not constitute a Windows dependency audit.

The Python export is temporary and deleted after the check. `--disable-pip` and
`--require-hashes` audit the fully pinned export without resolving/installing packages; bootstrap
already installs the locked tools. Both ecosystems are attempted even if one
audit fails. Findings at any reported severity, unavailable services, timeouts,
invalid exports, or tool failures make the command fail. There is no automatic
fix, advisory ignore list, or pass-on-network-error mode. Unit tests use fake
process runners to verify failure propagation without network calls.

Unlike unit tests, a current advisory scan requires public network access to
npm's advisory service and PyPI. It sends package names/versions, not application
source or provider payloads. Registry credentials are not required for this
public dependency graph. No provider/AWS credentials, paid provider calls, or
deployed environment are needed. Results are time-sensitive and are not Turbo
cached; rerun them before review. This gate is included in `scripts/validate`
and therefore CI.

This is dependency vulnerability scanning, not SAST, secret scanning, container
OS scanning, license certification, or penetration testing. No scanner proves
the absence of vulnerabilities. New findings must be reviewed and fixed; any
proposed exception needs explicit human approval and a bounded rationale.
The initial resolved findings and patch removal gates are in
[dependency fixes](../../patches/README.md).

Tool references: [pnpm audit](https://pnpm.io/cli/audit) and
[PyPA pip-audit](https://github.com/pypa/pip-audit).
