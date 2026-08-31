# Changelog

## 1.3.1

- Require complete quote and FX coverage for aggregate wallet values.
- Make recurring executions idempotent by plan and calendar month.
- Preserve deleted automatic executions as restorable skipped months.
- Exclude future contributions and lots from as-of investment and XIRR metrics.
- Attribute dividends conservatively when opening units are only partly tracked.
- Accept only confirmed Yahoo daily closes and normalize minor-unit currencies.
- Prevent concurrent config writes, reload races, and repeated cash allocation.
- Add a funding-contribution choice when importing historical purchase lots.
- Replace bilingual hard-coded labels with localized selector options.
- Add regression tests, linting, HACS validation, and Hassfest CI.
