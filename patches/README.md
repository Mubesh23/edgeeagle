# Scoped dependency security fixes

Reviewed 2026-09-22. No vulnerability ignore list is used.

- `xcode@3.0.1>uuid` is overridden to 11.1.1 for
  [GHSA-w5hq-g745-h8pq](https://github.com/advisories/GHSA-w5hq-g745-h8pq).
  Xcode's consumer uses `require('uuid').v4()`, preserved by UUID 11's CommonJS
  export. The regression test exercises the actual Xcode ID generator.
- `query-string@7.1.3>decode-uri-component` is overridden to 0.5.0 for
  [GHSA-vcc3-ghjq-m6fr](https://github.com/advisories/GHSA-vcc3-ghjq-m6fr).
  The fixed decoder is ESM; query-string 7 expects a callable CommonJS export.
  `query-string@7.1.3.patch` changes only its import to read `.default`, preserving
  the query-string API expected by Expo Router. No decoder code is forked and
  no advisory is suppressed. query-string's upstream MIT license remains in the
  installed package unchanged.
- Web's Vitest is updated to 4.1.11 for
  [GHSA-82fw-gwwq-j7x9](https://github.com/advisories/GHSA-82fw-gwwq-j7x9).

The patch was generated with `corepack pnpm patch query-string@7.1.3 --edit-dir
node_modules/.patches/query-string`, editing index.js, then `corepack pnpm
patch-commit node_modules/.patches/query-string`. pnpm records its hash in the
lockfile. Keep the patch and override together. To regenerate, use the same
commands and review the generated patch; do not change installed dependencies
without recording their patch and lockfile.

Remove each override/patch when the upstream parent adopts a compatible fixed
dependency. Re-run parser/ID tests, mobile tests, both native bundle exports,
web tests, and the dependency audit. A bundle export is not device-runtime proof;
native device testing remains a release gate.
