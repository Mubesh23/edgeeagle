# Authored Football-Data-shaped results fixture

`results.csv` is wholly synthetic, authored for EdgeEagle tests on 2026-09-23.
No rows were downloaded or copied from Football-Data.co.uk. SX, teams, scores,
dates, and notes are fabricated; do not use them for research. The fixture uses
the documented column vocabulary, not a claimed provider capture or license.
It exercises the ADR-028 subset with source `synthetic-fixtures`; per-row offsets
and canonical mappings are explicitly supplied by tests. `UnusedNote` proves
extra named columns remain raw-only. Tests never fetch the provider.
