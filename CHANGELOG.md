# Changelog

## 1.0.0 (2026-11-05)

- JSON Schemas for the QuickBooks Online 3-column and 4-column bank CSV layouts and for the statement header sidecar.
- 15 upload rules with sources and check dates in `rules/upload-rules.csv`.
- 48 fictional sample CSVs (24 statements in both layouts), 24 statement sidecars and 14 invalid files.
- `cli/qbo_csv_check.py`: checker with balance proof, `--fix` and `--json`.
- Tests, manifest, checksums and release zip.
