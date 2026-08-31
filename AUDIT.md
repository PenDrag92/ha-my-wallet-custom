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
