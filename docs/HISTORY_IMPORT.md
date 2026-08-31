# Statement history import

Open **My Wallet → Import history**, choose a JSON file, review the totals and
both plan date ranges, check the confirmation box and import. A **new wallet**
is created. Existing wallets and holdings are not merged or overwritten.
After comparing the new wallet against the broker, decide which wallet your
dashboards should use. Do not add the old and imported wallets together.

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
IDs must be unique within the file. Preserve `batch_id`: it prevents the same
statement from creating multiple wallets. A preview expires after ten minutes.

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

The importer starts opening units at zero and derives holdings from the imported
purchases. Import a complete transaction history for the intended wallet. It is
not an incremental bank-sync or an append operation into an existing wallet.

## Data and accuracy

Files stay in the browser/Home Assistant installation. Only symbols, dates and
market-price requests are sent to Yahoo, not transaction amounts or the file.
The panel and WebSocket endpoints are administrator-only. Static JavaScript
contains no financial records and uses no external chart CDN.

Daily history is an approximation based on recorded trades and closing prices.
It cannot reproduce broker execution prices, fees or corporate actions that
were not recorded. Historical graphs do not create native recorder statistics.
