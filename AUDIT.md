# My Wallet 1.3.1 audit

## Result

The 1.3.0 customization was reviewed across the ledger, scheduling, market-data,
performance, Home Assistant lifecycle, localization, and release packaging. The
1.3.1 changes address every confirmed high-impact defect found in that review.

## Correctness controls added

- Aggregate value is unavailable unless every configured security has a quote
  and FX rate; individual healthy positions remain available.
- Monthly executions use `(plan_id, calendar month)` identity and are
  idempotent across execution-day edits.
- Deleted automatic executions create a restorable skipped-month marker.
- Automatic config persistence no longer reloads the integration mid-refresh.
- An optimistic concurrency check prevents Yahoo waits from overwriting a
  simultaneous user edit.
- Settlement cash is capped both at the historical execution date and at the
  current uncommitted balance, then reserved across executions in close-date
  order.
- Future contributions and lots are retained but excluded from as-of totals,
  holdings, cashflows, and XIRR until their date.
- Historical lots can link to an existing funding contribution instead of
  duplicating invested capital.
- Included historical lots cannot exceed configured opening units.
- Dividend income is attributed only to eligible tracked units and leaves the
  untracked opening-position share unattributed.
- Yahoo intraday daily bars are excluded until the exchange-local close.
- Yahoo minor-unit currencies such as GBp are converted to major ISO units.
- Non-finite monetary, unit, allocation, price, FX, and XIRR values are rejected.

## Verification

- 18 deterministic regression tests
- Ruff lint and formatting checks
- Bandit static security scan
- JSON and YAML parsing
- Python bytecode compilation
- Import smoke test against Home Assistant 2024.11.3
- CI definitions for tests, Ruff, HACS validation, and Hassfest

## Explicit approximation

The broker data shown for dividends contains booking and value dates but no
ex-dividend/entitlement date. Lot eligibility therefore uses the value date (or
booking date when no value date exists). Cash availability also uses the value
date. This is documented rather than presenting the result as exact entitlement
data that the integration does not possess.

## Publication metadata

The manifest still points to the original upstream repository because the fork
URL and GitHub username are not present in the source archive. Before publishing
the fork through HACS, update `codeowners`, `documentation`, and `issue_tracker`
in `custom_components/my_wallet/manifest.json` to the fork owner and URL.
