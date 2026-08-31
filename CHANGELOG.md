# Changelog

## 1.3.3

- Add an automatically registered, authenticated administrator sidebar panel
  with daily portfolio history, deposited capital, cash, transaction filters,
  CSV export and separate savings-plan summaries. No manual dashboard setup.
- Add a previewed statement JSON import that creates a separate wallet, keeps
  actual funding/purchase dates and blocks duplicate import batches. Missing
  quotes require manual units before any import is saved.
- Fix fixed-currency plan totals and guide asset selection, allocation and
  explicit confirmation. Add progress and concrete pending/correction reasons.
- Support future-only plan edits and atomic recalculation of eligible automatic
  executions. Preserve manual corrections, reviewed legacy safeguards and IDs.
- Add combined deposit/investment entry with per-asset dates, prices or units;
  standalone purchases now use existing cash without another deposit.
- Use real defaults for required dates; reject future manual deposits/purchases;
  add notes, descriptive booking labels and a separate deletion confirmation.
- Keep pending past executions separate from the next scheduled date and
  prevent ended plans from using unrelated prices months later.
- Preserve opening-balance safeguards and cash history; migrate to schema 6.
- Extend regression coverage, localization, API-boundary checks and real schema
  validation. Keep private statements out of the public release archive.

## 1.3.2

- Harden the ledger: legacy opening-balance lots are cash-neutral, linked
  funding cannot post after its lot, and reinvestment respects every
  intermediate cash balance.
- Hold automatic executions for repair when included opening lots would exceed
  the configured opening units.
- Preserve the identity and skipped months of a removed plan when an otherwise
  identical plan is later re-created, preventing historical months from being
  booked twice.
- Safely migrate legacy undersized percentage plans by disabling them, and
  clamp future opening-balance cutoffs during migration. Reject contradictory
  version-4 lot funding data instead of loading a misleading cash history.
- Reject non-finite numeric input and tolerate malformed Yahoo response data.
- Revalidate stale option forms, lot corrections, symbols, IDs, and base
  currency before saving; extreme short-term returns no longer overflow a
  performance sensor.
- Point manifest ownership, documentation, and issue reporting to the fork.
- Add release metadata and validation coverage for versions, manifest links,
  dependency pinning, and workflow checks.

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
