# Changelog

## 1.11.2

- Use the shared ledger's financial revision and opening holdings for new
  Recorder snapshots. Notes, aliases and ordinary purchases attached to edited
  deposits no longer suppress day/week metrics as false accounting corrections.
- Show the observable reason and first affected recording time for accounting
  discrepancies, with expandable additional entries and Home Assistant time-zone
  formatting. Distinguish decreases in recorded capital/dividends, unit changes
  without purchases, financial revisions and uncertain legacy comparisons.
- Preserve the original revision marker for comparisons across the update.
  Older recordings may still flag metadata changes; show that uncertainty and
  date-only correction evidence without inventing edit times or rewriting data.
- Add regression coverage for metadata edits, normal cash flows, real corrections,
  reversals, position scope, mixed snapshot versions and recording gaps.

## 1.11.1

- Match prepared statement records to their source IDs instead of their list
  positions. Preserve deposit, purchase and dividend links after chronological
  normalization, including latest-first and same-day statements. Prevent valid
  follow-up imports from failing or silently omitting new dividends.
- Preserve low-order cash remainders across event dates so small credits can fund
  a later purchase without a spurious historical deficit. Keep the existing
  deficit tolerance and the single chronological pass.
- Add six regression tests covering import ordering, overlapping confirmations,
  dividend totals and fully funded purchases at large cash balances.

## 1.11.0

- Introduce a shared ledger for purchase bookings, deposit/lot corrections and
  dividend/deposit deletion. Keep manual-correction and skipped-plan-period
  bookkeeping alongside the corresponding transaction.
- Route all ordinary existing-wallet writes through one Home Assistant store
  boundary, including options, dashboard actions and automatic executions.
  Reject stale snapshots, duplicate identifiers, new dangling references,
  future bookings, increased opening conflicts and worsening historical cash.
- Reuse record validation for statement imports and backup restoration. Keep the
  explicit historical-purchase cash exception restricted to added purchases.
  Preserve recoverable historical deficits during backup restore.
- Calculate cash events once and walk their timeline for funding and reinvestment
  checks instead of repeatedly rebuilding the entire history at each event date.
- Share full-precision wallet, position and lot valuations between the dashboard
  and sensors, including dividend attribution, XIRR and inflation adjustment.
  Keep unknown opening costs, missing quotes and missing inflation data explicit.
- Separate shared input schemas from flow controllers and remove their circular
  imports. Remove obsolete sensor-side arithmetic helpers.
- Make accounting revisions stable between transaction preview and commit, retain
  prior revisions on metadata edits, and distinguish a later reversal.
- Add complete transaction/restore regressions and a separate real Home Assistant
  sensor/dashboard comparison in CI. Preserve config-entry version 7, backup
  version 1 and existing sensor identifiers.

## 1.10.2

- Preserve distinct same-symbol purchases during overlapping statement imports.
  Reserve stable purchase IDs, require a choice for ambiguous matches and count
  added purchases correctly. Confirmed quantity changes now require a visible
  keep/replace decision even when dates and payment amounts are unchanged.
- Validate follow-up funding against the combined chronological ledger, including
  existing settlement cash. Check purchase edits and dividend edits/deletions for
  newly unfunded purchases before saving.
- Invalidate import previews and decisions on wallet changes. Display the
  preview's target and verify that target again on the server before committing.
- Keep assets referenced by historical or retired savings plans. Stop automatic
  bookings when a historical rule refers to an unconfigured asset, with a
  translated repair message instead of creating an unvalued holding.
- Mark revisions of existing financial events, including imported estimates and
  recalculated plan purchases. Withhold period returns across those revisions;
  ordinary new cash flows retain their existing return treatment. Preserve the
  revision metadata in backups.
- Reject future dividend booking/value dates when entered or edited, matching
  restore validation. Validate historical plan references during restore and
  support backup round trips for empty or cash-only wallets.
- Stabilize XIRR over long histories and very small/large cash-flow magnitudes.
- Add regression coverage for all nine review findings, including import target
  checks in the frontend and at the WebSocket boundary.

## 1.10.1

- Fit the day and week chart axes to the visible wallet or position values,
  with padding and readable currency steps so small changes remain visible.
  Apply the same behavior to the independent settlement-cash chart.
- Identify the automatic scale beside the legend. Keep missing samples as
  gaps, handle constant values and retain distinct labels for small changes
  in large portfolios. Month and longer ranges keep their zero-based scales.
- Leave recorded history, balances and performance calculations unchanged.

## 1.10.0

- Add 1-day (last 24 hours) and 1-week (last 7 days) history from Home
  Assistant Recorder, using the wallet or selected position's recorded values
  and holdings. These views do not request extra Yahoo prices. Add a calendar
  1-month range to the existing daily-close history.
- Show opening and closing value, deposits or purchases, dividends, gain and
  flow-adjusted interval return for the displayed historical period. Support
  nominal values and today's purchasing power; do not count deposits as gains
  or portfolio dividends twice.
- Store a small accounting snapshot and poll timestamp alongside existing
  value sensors. Keep old recordings unchanged, accept matching legacy cost
  data where available and withhold returns when the basis is incomplete or a
  holding correction is detected.
- Preserve unavailable values, stale tails and missing recordings as gaps.
  Explain disabled or excluded sensors, paused/missing Recorder and incomplete
  retention. Show the last recorded refresh and local timestamps.
- Restrict Recorder reads to the selected wallet's own sensors, with bounded
  periods, an administrator-only endpoint and short-lived request caching.
  Existing Recorder settings and retention remain unchanged.
- Place "too much", "too little" and "on target" on a smaller second line in
  current and forecast allocation tables. Preserve percentages, neutral colors,
  calculations and explicit zero targets.
- Add flow/gap/correction regression coverage, responsive dashboard checks and
  an integration check against the real Home Assistant 2026.8.3 Recorder.

## 1.9.2

- Simplify allocation differences in the current and forecast views: use
  "Difference from target" with a signed percentage and "too much", "too little"
  or "on target" in one line, retaining neutral colors.
- Explain that the difference is the displayed share minus target share,
  expressed as a percentage of the total portfolio value. Calculations, zero
  targets, stored holdings and sensor units remain unchanged.

## 1.9.1

- Make current unit counts clickable in the allocation overview, positions,
  position metrics, purchase details and transaction ledger. Open a focused
  correction dialog with the selected position or purchase already filled in.
- Accept decimal commas and points without rounding the entered units. Reject
  blank, negative, non-finite, out-of-range and ambiguous input. Keep drafts
  stable during background refresh and allow cancellation with Escape.
- Retain the existing preview and explicit save step. Show the affected purchase
  for total-position corrections, prefer estimated purchases when available,
  invalidate previews when input changes and retain errors without losing edits.
  Recorded payment amounts, purchase dates, cash and deposits stay unchanged.
- Revalue saved holdings with the last available quotes immediately after an
  edit, without waiting for the integration reload or changing cached sensor
  state. Keep known unit counts visible when quotes are unavailable.
- Display allocation deviations with neutral overweight/underweight labels and
  a clear percentage-points heading, including positions with a zero target.

## 1.9.0

- Preserve explicit zero allocation targets in configuration, computed state,
  deviation sensors and dashboard tables. Keep zero-value positions in the
  allocation table and label deviations in percentage points.
- Add a Planning dashboard tab to create, edit and cancel future one-off
  deposits, with the expected cash-reinvesting plan and schedule date. Show
  whether each savings plan reinvests settlement cash.
- Accept future standalone deposits in integration options and add a dedicated
  planning form. Keep purchases and dividend bookings restricted to past dates.
- Exclude future deposits from current capital, cash, performance, contribution
  counts, calendar summaries and transaction exports. Apply them automatically
  on their date and retain them in complete JSON backups.
- Simulate cash reinvestment in allocation forecasts, including one-off deposits
  on the plan date, multiple plans, pauses, skips and end dates. Reuse the same
  proportional cent-rounding rules as actual plan executions without counting
  reinvested cash as an additional deposit.
- Protect past bookings from the planning editor and reject deposit corrections
  or deletions that would leave existing purchases unfunded.

## 1.8.0

- Add a persistent nominal/purchasing-power switch to the administrator
  dashboard. Apply it to wallet and position performance, purchase lots,
  history, monthly/yearly summaries, transaction amounts and forecast
  allocations.
- Fetch Germany's official monthly all-items HICP from Eurostat at most once per
  day. Validate and cache the series locally, show its latest month and continue
  with a visibly stale cache when a refresh is temporarily unavailable.
- Recalculate historical invested capital, dividends, profit, simple return and
  money-weighted return in today's purchasing power. Leave an adjusted result
  unavailable when any required date falls outside the official series instead
  of combining partial nominal and real data.
- Add a configurable expected annual inflation assumption, defaulting to 2%,
  and use its geometric factor for 1–50 year purchasing-power forecasts. Show
  real target value, contributions, growth, allocation and inflation effect
  alongside the existing nominal scenario.
- Expose inflation-adjusted wallet and tracked-position metrics plus their data
  source, latest month and cache status as sensor attributes. Preserve the new
  settings in schema-7 migrations, complete backups and imported wallets.
- Use optional position display names consistently throughout savings-plan,
  investment, dividend, correction and configuration flows and in entity names,
  while keeping raw symbols stable for storage, Yahoo requests, unique IDs and
  CSV exports.

## 1.7.0

- Split the administrator dashboard into Overview, Positions, History and
  Transactions & data tabs while keeping the wallet and position selection
  consistent across them.
- Add a 30-year forecast preset and a custom horizon from 1 to 50 years. Apply
  the selected horizon to the target composition, portfolio forecast,
  allocation and projected position values.
- Keep real history at daily precision while sampling long future curves by
  month and on scheduled plan dates. This keeps custom multi-decade forecasts
  responsive without changing their end values or contribution totals.
- Document future savings-rate increases as a separate plan with its own start
  date, so the existing plan and historical bookings remain unchanged while the
  forecast combines both rates from the intended month.

## 1.6.1

- Break down every compound target into the contributions included through the
  selected date and the expected growth generated by the configured return.
- For future horizons, show how much of those contributions is still planned
  from today onward. Keep the current absolute and percentage deviation
  together in the today view.
- Apply the selected horizon to the allocation donut and table. Project today's
  position values with the configured return and route future plan payments to
  their configured assets; expose the same projected value and share in the
  positions table without pretending to know future units or market prices.
- Continue the chart with a separately labelled dashed portfolio forecast and
  planned contribution values, so future tooltips no longer contain empty
  actual-value placeholders.
- Expose today's target contributions and target growth as attributes of the
  compound-target sensor. Keep the target comparison in a stable three-column
  layout and prevent the eighth overview metric from wrapping onto a row alone.

## 1.6.0

- Add a configurable expected annual return per wallet, defaulting to 7% and
  editable in the normal wallet settings without changing transactions,
  holdings or savings plans.
- Calculate a compound-return target from the documented wallet start. The
  target uses one-off deposits and the historically applicable planned savings
  rates, includes due plan payments, combines multiple plans and respects rate
  changes, pauses, end dates and explicitly skipped months without double
  counting booked executions.
- Add a monetary compound-target sensor with the geometrically derived monthly
  return, wallet start, actual wallet value and absolute/percentage deviation
  as attributes. The actual comparison includes settlement cash.
- Show a dismissible dashed target curve and a target-comparison card in the
  administrator dashboard. Forecast the same curve 1, 3, 5, 10 or 20 years
  ahead; open-ended active plans continue while ended plans stop on schedule.
- Keep dividends out of target cash flows because the configured expected
  return is treated as a total-return assumption. Leave the target unavailable
  when a legacy opening balance or wallet start cannot be documented instead
  of inventing a starting value.
- Preserve the expected return in complete JSON backups and add calculation,
  plan-history, forecast, dashboard and options regressions.

## 1.5.0

- Add a portfolio-allocation card with a current-value donut, actual shares,
  optional targets and deviations. Settlement cash is included in the same
  wallet denominator used by the total and sensor allocation.
- Show the documented wallet start date in the overview and the documented
  start date for a selected position. Leave either date unavailable for legacy
  opening holdings whose actual acquisition date is unknown.
- Add per-position purchase-lot details with dates, units, entry prices,
  current values, attributed dividends, profit, simple performance and
  annualized return.
- Add a complete versioned JSON backup alongside the transaction CSV export.
  Backups are validated, previewed and restored as a separate wallet without
  changing existing entries.
- Align dashboard summary values across one-line and wrapped labels, use a
  neutral position-name example, and keep wide detail tables contained on
  smaller screens.
- Document the bundled local Home Assistant brand assets. Home Assistant can
  use them on integration pages; HACS update cards still depend on an upstream
  HACS fix before they can replace their current placeholder.

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
