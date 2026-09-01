# Statement history import

Open **My Wallet → Import history**, choose the import target and a JSON file,
then review the complete preview before confirming. **Create new wallet** keeps
the original isolated-import behavior. **Reconcile existing wallet** compares the
file with the wallet currently selected in the dashboard and appends only records
that are not already represented.

Use the same stable plan, deposit, purchase and dividend IDs again when a later
file overlaps an earlier statement. The importer also recognizes plan calendar
months and exact date/amount/asset combinations. Ambiguous matches stop at the
preview. If confirmed broker data or a manual correction differs, choose whether
to keep it or explicitly apply the incoming details; no protected value is
silently overwritten. A changed wallet invalidates an outstanding preview.

The supplied private import file must not be committed to the public repository.
Do not include account numbers, credentials or personal names in reusable samples.

## Format 1

The example is synthetic. Replace the asset symbol and data before actual use.

```json
{
  "format": "my_wallet_history",
  "version": 1,
  "batch_id": "example-2026-01",
  "wallet_name": "Example only",
  "base_currency": "EUR",
  "assets": [{"symbol": "AAA"}],
  "plans": [{
    "id": "first-plan",
    "name": "Earlier plan",
    "first_date": "2026-01-20",
    "end_date": "2026-01-31",
    "allocation_mode": "fixed",
    "allocations": [{"symbol": "AAA", "value": 30}],
    "enabled": true,
    "use_cash_balance": true
  }],
  "deposits": [{
    "id": "deposit-one",
    "date": "2026-01-15",
    "amount": 30,
    "plan_id": "first-plan",
    "scheduled_date": "2026-01-20",
    "note": "Example deposit",
    "purchases": [{
      "id": "purchase-one",
      "date": "2026-01-21",
      "symbol": "AAA",
      "amount": 30,
      "units": 3
    }]
  }],
  "dividends": []
}
```

All amounts are in the wallet base currency. A purchase can supply `units` or
an effective `unit_price` in that currency, never both. Without either field,
the importer estimates units from the latest confirmed Yahoo close on or before
the actual purchase date (at most seven calendar days old), with historical FX.
The actual statement cash date stays unchanged and the pricing date is retained.

Missing quotes/FX leave the entire import uncommitted. The preview lets you
enter actual units for those purchases and try again. Supplied units/prices are
treated as manual broker data; do not enter estimates there without accounting
for that distinction. An existing wallet's **Correct a purchase lot** dialog
can later replace estimates with actual contract-note units.

Every purchase date must be on or after its deposit date, every manual booking
must be on or before today, and cash must remain funded on every event date.
IDs must be unique within the file and should remain stable in later overlapping
files. Give every exported file a new `batch_id`; reusing one prevents that batch
from being processed again. Repeating the same content under another batch ID is
also detected. A preview expires after ten minutes.

Dividends accept `id`, `booking_date`, `amount`, optional `symbol`, optional
`value_date` and optional `note`. If a value date exists it determines cash
availability; otherwise the booking date is used. Do not invent value dates.

Plans use `first_date`, optional `end_date`, `allocation_mode` (`fixed` or
`percentage`), `allocations` and (for percentage mode) `amount`. Separate a change
in allocation into two plans with their own date ranges. Each deposit can link
to one `plan_id` and its original `scheduled_date`. Imported plan months count
as booked. Past plan periods missing from the statement are marked skipped so
startup cannot silently invent additional deposits. Future periods still run
automatically under the configured rules.

For a new wallet, the importer starts opening units at zero and derives holdings
from the imported purchases. A follow-up import keeps existing opening holdings,
target allocations and unmatched lots. New assets start with zero opening units;
new plan definitions cannot backfill unlisted past periods. This is a reviewed
JSON statement workflow, not automatic bank sync. Arbitrary broker PDFs and CSVs
are not parsed by the integration.

## Data and accuracy

Files stay in the browser/Home Assistant installation. Only symbols, dates and
market-price requests are sent to Yahoo, not transaction amounts or the file.
The panel and WebSocket endpoints are administrator-only. Static JavaScript
contains no financial records and uses no external chart CDN.

Daily history is an approximation based on recorded trades and closing prices.
It cannot reproduce broker execution prices, fees or corporate actions that
were not recorded. Historical graphs do not create native recorder statistics.
