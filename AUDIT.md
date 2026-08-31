# My Wallet 1.3.3 verification note

This is a local code-review and regression-test note, not an independent
security certification. It does not certify broker or market-data accuracy.

## Scope

- Recalculation is prepared before a single config-entry write. Missing prices
  or a worsened cash history roll the booking changes back; the result dialog
  explains that the new plan settings may be saved while old bookings remain.
- Explicit manual corrections are protected. Old records without reliable
  correction metadata need the user's per-record approval for recalculation.
- Imported statement records do not become eligible for automatic recalculation.
  Removing any linked execution also records its skipped plan month.
- Purchase-only groups carry zero external funding. Deposited capital and XIRR
  external flows therefore cannot count a purchase as another deposit.
- Financial WebSocket endpoints check administrator status. Import previews
  are short-lived, bound to the initiating user and consumed once. Imports
  always create a separate wallet instead of replacing existing financial data.
- The frontend renders imported names/notes as text, loads no third-party
  JavaScript and neutralizes spreadsheet formula prefixes in exported text.
- History uses only past confirmed closes and FX; unknown opening holdings or
  missing prices do not produce invented historical portfolio values.

## Local verification

The release workflow covers unit tests, Ruff lint/format, Bandit, JSON/YAML,
compilation, date defaults with real Voluptuous, JavaScript syntax and imports
against the minimum Home Assistant version. The unit suite uses dependency
stubs; it is not a running Home Assistant instance. Browser checks exercise the
actual panel module in a loopback test harness, including responsive layout,
range/type filters, file preview and confirmation. Home Assistant public API
signatures were checked against core sources. A remote CI run and an upgrade
inside the user's live Home Assistant have not been performed here.

For one private statement, all purchase/FX lookups and daily reconstruction
were additionally exercised against real Yahoo responses. Its transactions and
results are deliberately excluded from this public package.

## Limits

There is no broker connection. Estimated units are not contract-note units;
fees, actual execution prices and FX may differ. Future plan entries follow
configured rules and may need broker corrections. Sales, stock splits and other
corporate actions are not reconstructed automatically. Dividend entitlement
still uses booking/value dates rather than unavailable ex-dividend dates.
History is reconstructed on demand and does not backfill recorder statistics.

---

# My Wallet 1.3.2 audit note

## Result

This is a maintainer code-review and regression-test note, not an independent
security certification. The 1.3.2 release hardens the cash ledger, migration
boundaries, input handling, and Yahoo response handling. It does not make
broker data or Yahoo data authoritative.

## Ledger safeguards in 1.3.2

- A legacy opening-balance contribution accepts only opening-balance lots; such
  lots are cash-neutral, so an already-held position cannot fund a later buy.
- A linked funding contribution must be dated on or before its purchase lot.
  The invariant is enforced both when a lot is imported and when an existing
  lot or its parent contribution is corrected.
- Reinvestable cash is bounded by the lowest ledger balance at every event from
  an execution date through today, with same-refresh reservations deducted.
  A later deposit therefore cannot finance an earlier cash deficit.
- Automatic execution is held pending for repair when proposed opening-balance
  lots would exceed the configured opening units for a symbol.
- Migration to config-entry version 5 preserves an otherwise valid legacy plan
  that is too small to allocate one cent per percentage position, but disables
  it. Future opening-balance cutoffs are clamped to the migration date.
- Removed plans retain an inert identity record. Re-creating the same schedule
  and allocation reuses its original ID and skipped months, so past executions
  cannot silently become due again.

## Other defensive changes

- Wallet input defaults reject non-finite and out-of-range numeric values.
- Multi-step option forms verify that their base currency, selected IDs, and
  configured symbols still exist before saving, avoiding stale-form writes.
- Extreme short-lived gains return an unavailable annualized lot metric rather
  than overflowing and taking down the performance entity.
- Yahoo payload decoding, timestamps, and background fetch boundaries handle
  malformed provider data as unavailable data rather than uncaught failures.
- The validation workflow checks tests, Ruff lint and formatting, Bandit, JSON
  and YAML parsing, compilation, and imports against Home Assistant 2024.11.3,
  alongside HACS and Hassfest validation.

## Verification

- Regression coverage includes the legacy-opening, funding-date, cash-interval,
  opening-unit, and migration cases listed above.
- The local release check and the repository workflow are intended to run the
  static checks listed above. Results are release-environment dependent; this
  document does not claim that a remote CI run has completed.

## Explicit approximation

The broker data shown for dividends contains booking and value dates but no
ex-dividend/entitlement date. Lot eligibility therefore uses the value date (or
booking date when no value date exists). Cash availability also uses the value
date. This is documented rather than presenting the result as exact entitlement
data that the integration does not possess.

## Publication metadata

The manifest identifies `@PenDrag92` as code owner and points documentation and
issue reporting to the `PenDrag92/ha-my-wallet-custom` fork. GitHub Issues
enablement and repository topics are repository settings; they cannot be
declared or verified from this integration package.
