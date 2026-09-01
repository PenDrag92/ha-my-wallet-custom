# Changelog

## 1.4.1

- Move the position selector directly above the metrics it controls and make
  the active table row visible. Position selection continues to filter value
  history, monthly/yearly summaries and transactions together.
- Add optional, persistent display names for positions. Edit them in the
  administrator dashboard and show the friendly name alongside the unchanged
  technical symbol in tables, selectors, charts, plans and corrections.

## 1.4.0

- Expand the administrator dashboard with wallet profit, simple performance,
  money-weighted return, position values, exact units, cost basis, allocation
  and selectable per-position history and ledger views.
- Add monthly and yearly tables that keep deposits and purchases separate from
  market gain and dividends. Leave returns unavailable when a boundary value or
  required historical quote is unknown.
- Add previewed follow-up imports into an existing wallet. Reuse stable source
  IDs, plan months and exact financial matches, append only new records, and
  require a visible decision before confirmed or manually corrected data can be
  replaced. Preview commits reject concurrent wallet changes.
- Add a dashboard unit-correction workflow with an explicit source lot/opening
  holding, before/after preview and audit record. It does not alter deposits,
  purchase amounts or cash history.
- Give settlement cash its own compact chart and rounded currency scale, share
  the date cursor between both charts, and start complete zero-opening histories
  one day before the first deposit.
- Make the estimated-unit explanation dismissible per browser and wallet, and
  show a config entry's current Home Assistant title after it is renamed.
- Require Home Assistant 2026.8 or newer, validate against Home Assistant
  2026.8.3 and add chart-scale boundary tests.
- Add a tag-driven GitHub release workflow that publishes the matching changelog
  section, an installation ZIP and its SHA-256 checksum.

## 1.3.4

- Let legacy wallets with conflicting opening quantities migrate without
  changing holdings, payment amounts or purchase lots. Keep structural
  validation for malformed data and missing asset references.
- Surface the discrepancy in the panel, options and sensor attributes.
  Pause automatic plan bookings and suppress the historical value curve
  until reconciliation; retain deposits, cash and the transaction ledger.
- Allow incremental manual corrections without worsening a discrepancy;
  resume normal operation automatically after the quantities agree.
- Replace portfolio-specific public examples with generic guidance.
- Add migration, persistence, recalculation and recovery regressions.

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
