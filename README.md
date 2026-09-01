# My Wallet for Home Assistant

A [HACS](https://hacs.xyz) custom integration that tracks investment wallets in
Home Assistant. Each wallet is a config entry that holds a list of **valors**
(market instruments) with configurable amounts, valued live via
**Yahoo Finance**.

Version 1.4.1 requires **Home Assistant 2026.8 or newer**.

Project home: <https://github.com/PenDrag92/ha-my-wallet-custom>. Report bugs
or feature requests through the [issue tracker](https://github.com/PenDrag92/ha-my-wallet-custom/issues).

## 1.4.1: clearer position selection and display names

The position selector now sits directly above the metrics it controls. The
same selection filters the value curve, monthly/yearly summaries and transaction
history, while the selected row is highlighted in the position table.

Use **Edit names** in the position table to add optional, persistent display
names such as `Amundi`. The dashboard shows that name together with the original
Yahoo symbol, which remains the stable identifier for quotes, imports and CSV
exports. Changing a display name does not alter units, payments or history.

## 1.4.0: dashboard, reconciliation and exact-unit corrections

The administrator sidebar now includes wallet and position performance,
selectable per-position curves and bookings, and monthly/yearly summaries.
Settlement cash uses a separate rounded currency scale. A complete history with
no opening holding starts at zero on the day before its first deposit.

**Import history** can still create a separate wallet or reconcile another
My-Wallet JSON statement with the selected wallet. The preview distinguishes new,
updated and existing records. Stable IDs and scheduled plan months prevent
duplicate bookings; confirmed or manually corrected differences need an explicit
choice. This is a local statement import, not a bank connection or PDF parser.

**Correct units** in the dashboard accepts an exact total or exact units for one
chosen purchase/opening holding. Its before/after preview keeps every deposit,
purchase amount and cash movement unchanged. Corrections are recorded and block
later automatic recalculation of the corrected purchase.

The explanation for estimated units is dismissible per wallet and browser. The
wallet selector follows later Home Assistant config-entry renames. Config-entry
schema remains version 6; existing entity IDs are unchanged.

Release tags now create the GitHub release automatically, including the matching
changelog section, an installation ZIP and its SHA-256 checksum.

## 1.3.4: keep legacy wallets recoverable

A legacy wallet can contain purchase lots marked as already included in
opening holdings whose combined units exceed the configured opening units.
This disagreement no longer prevents migration or access to the options.
All recorded quantities, lots and payments are preserved. Automatic plan
bookings pause and historical portfolio values remain unavailable until
the discrepancy is reconciled against the user's statements. The panel,
options menu and next-execution sensor identify the affected holdings.

Correct the opening units or purchase lots through the existing options.
Several corrections may be needed; each step may preserve or reduce an
existing discrepancy, but cannot increase it. A complete statement import
can alternatively create a separate wallet without changing the old one.
Do not increase holdings merely to dismiss a warning. Back up Home Assistant
before upgrading. Config-entry schema remains version 6.

Documentation and setup examples are generic. Private statements and
prepared import files are never part of the public source package.

## Features

- **Multiple wallets** — each wallet is created separately via
  *Settings → Devices & Services → Add Integration → My Wallet*.
- **Valors with amounts** — any Yahoo Finance symbol works: stocks
  (`AAPL`, `VWAGY`), ETFs (`VWCE.DE`, `SPY`), crypto (`BTC-USD`),
  indices (^DJI), funds, etc.
- **Per-wallet update schedule** — configurable update interval
  (5–1440 minutes) for each wallet independently.
- **Currency conversion** — each wallet has a base currency; valors quoted in
  a foreign currency are converted using live Yahoo FX rates
  (e.g. `USDPLN=X`).
- **Dated contributions & profit** — keep a ledger of deposits with amount and
  execution date. Their sum drives the *Deposited capital*, *Profit*, and *Profit %*
  sensors alongside the total.
- **Recurring monthly savings plans** — choose the first execution date and
  split each monthly rate either by percentages or fixed amounts. Due purchases
  are booked automatically using the first confirmed Yahoo daily close on or
  after the scheduled date.
- **Dividends and settlement cash** — record the net dividend actually credited
  by the broker, including booking and optional value date. Savings plans can
  include this cash automatically; cent-rounding remainders
  remain visible on the settlement account.
- **Purchase-lot performance** — every automatic execution creates one lot per
  valor with invested amount, price and units. The integration reports profit,
  simple performance and annualized performance per valor and per lot, plus a
  money-weighted return (XIRR) for the whole wallet.
- **Administrator dashboard** — select the complete wallet or one position,
  inspect performance and allocation, compare monthly/yearly results, reconcile
  follow-up JSON statements, correct exact units with a review step, and assign
  readable position display names without changing their Yahoo symbols.
- **Target allocation** — optionally set a target share (in %) for each valor
  to see how far its actual share deviates from the target, plus a rebalancing
  hint in the base currency.
- **Sensors** — value and performance sensors per valor plus wallet totals,
  profit, XIRR and the next savings-plan execution, grouped under one device.
- **`my_wallet.refresh` service** — force an immediate update of selected
  wallets without waiting for the schedule.
- **Translations** — English, German, Polish, and Czech.

No external Python dependencies — prices are fetched directly from Yahoo
Finance's chart API using `aiohttp`.

## New in 1.3.3

- An automatically registered **My Wallet** sidebar panel shows a daily value
  curve, deposited capital, optional cash, a filterable ledger and savings plans.
  It requires no Lovelace YAML or external chart plugin and is administrator-only.
- The plan wizard selects assets before allocation, shows a final review and
  reports created, recalculated, retained and pending executions with reasons.
  Editing a fixed total actually scales its individual currency amounts.
- Plan edits can apply only in the future or recalculate eligible automatic
  history. Known manual corrections are never overwritten. Older unclassified
  bookings need explicit approval before recalculation.
- A deposit can be allocated immediately, using per-asset purchase dates,
  historical quotes or manual prices/units. Purchases do not add another deposit.
- Statement JSON imports are previewed and create a **separate new wallet**.
  Existing wallets are untouched; a stable import batch ID prevents duplicates.
  Two simple plans with different date ranges share the same history view.

### Automatic history

After upgrading, restart Home Assistant fully, then open **My Wallet** in the
sidebar. It appears for administrators. Select a wallet; the view reconstructs
historical daily values from dated purchases and confirmed Yahoo closes,
including historical FX. The panel refreshes automatically while visible and
caches historical requests for five minutes. It does not manufacture or insert
old Home Assistant recorder statistics.

Deposits, purchases and dividends have separate cash dates. Dividends increase
cash and returns but never deposited capital. Unknown opening holdings leave
historical portfolio values empty until their dated lots have been recorded.
Missing or more than seven-day-old prices leave gaps instead of fabricated
values. The chart covers up to ten years; the ledger contains all saved entries.

Estimated units make portfolio values approximate. The current-value card uses
the latest coordinator result; the curve uses confirmed daily closes. The panel
is in English/German; configuration dialogs retain all four supported languages.

For statement import instructions and the public JSON schema, see
[History import](docs/HISTORY_IMPORT.md). No bank credentials are used. Savings
plans simulate purchases under their configured rules and do not connect to a
broker, place orders or download bank statements.

### Upgrade safety

Back up Home Assistant before replacing integration files. Config-entry schema
6 preserves the ledger and labels existing correction status conservatively.
Do not downgrade to 1.3.2 against schema-6 data; restore the backup as well.
Existing entity unique IDs are unchanged. The invested-capital sensor display
name is now **Deposited capital** (German: **Eingezahltes Kapital**).

For a manual upgrade, copy the **entire** `custom_components/my_wallet` folder,
including `frontend`, translations and the new Python modules. Updating only
README/changelog/version files does not update the integration.

## Installation

### HACS (recommended)

1. In HACS, go to **⋯ → Custom repositories**.
2. Add this repository with category **Integration**.
3. Find **My Wallet** in HACS and download it.
4. Restart Home Assistant.

### Manual

Copy `custom_components/my_wallet` into the `custom_components` directory of
your Home Assistant configuration and restart.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration** and search for
   **My Wallet**.
2. Fill in the wallet settings:
   - **Wallet name**
   - **Base currency** — currency the wallet total is displayed in
   - **Update interval** — minutes between Yahoo Finance updates
3. Add valors: enter the **Yahoo Finance symbol** and the **opening amount** of
   units you already hold. Tracked savings-plan purchases are added to this
   opening balance automatically. Optionally enter a **target share (%)** — the percent of the
   wallet this valor should hold — to enable the deviation sensor.
   Tick *Add another valor* to keep adding, or submit to finish.

### Managing a wallet

Open the config entry and click **Configure** to:

- edit wallet settings (name, base currency, update interval),
- add, edit, or remove dated contributions in the wallet's base currency,
- import historical purchases one tranche at a time, using a Yahoo close or a
  manually entered effective price when Yahoo has no history; select an
  existing contribution when the deposit was already recorded, so invested
  capital is not counted twice,
- add, edit, or remove dividend credits,
- add monthly savings plans with percentage or fixed-amount allocations,
- edit, pause or remove savings plans without deleting past executions; a
  deleted automatic execution remains skipped and can be restored explicitly,
- correct the deposit date or external amount of an individual historical
  execution while retaining its purchase lots,
- correct the date, invested amount or purchased units of an automatically
  generated lot,
- add a valor,
- remove a valor,
- edit a valor (amount and target share; clearing the target share removes it).

The sum of target shares may not exceed 100% (a sum below 100% is fine —
the remainder can be assets held outside this integration).

Changes take effect immediately (the wallet reloads automatically). After an
integration upgrade, restart Home Assistant completely and reload the browser;
otherwise Home Assistant can keep the previous translation bundle in memory.

For funds, use the exact Yahoo identifier for the intended share class.
Check its quote currency and available daily history before reconstructing
older purchases. A secondary exchange listing may provide a current price
without enough historical data. The integration converts foreign quotes
to the wallet base currency when an exchange rate is available.

## Entities

| Entity | State | Useful attributes |
|---|---|---|
| `sensor.<wallet>_<symbol>` | valor value in base currency | `amount`, `unit_price`, `quote_currency`, `fx_rate`, `day_change`, `day_change_pct`, `short_name`, `share`, `target_share`, `share_deviation`, `rebalance_amount` |
| `sensor.<wallet>_<symbol>_deviation` | actual share − target share, in percent points (unavailable when no target is set) | `target_share`, `share`, `value`, `rebalance_amount` |
| `sensor.<wallet>_<symbol>_profit` | current value of tracked lots + attributed dividends − their cost | `tracked_invested`, `tracked_value`, `dividend_total`, `lots` |
| `sensor.<wallet>_<symbol>_performance` | simple return of tracked lots including attributed dividends | per-lot date, dividend income, value, profit, simple and annualized performance in `lots` |
| `sensor.<wallet>_<symbol>_annualized_performance` | money-weighted annual return of this valor's tracked lots | tracked-lot summary |
| `sensor.<wallet>_total` | wallet total in base currency | `valors` (per-valor breakdown incl. `share`, `target_share`), `unavailable_valors` |
| `sensor.<wallet>_cash_balance` | deposits + net dividends − purchase amounts | contribution and dividend totals |
| `sensor.<wallet>_dividends` | cumulative net dividend income | booking date, value date, source valor and note per dividend |
| `sensor.<wallet>_invested` | sum of all contributions (unavailable when the ledger is empty) | `contributions`, `contribution_count`, `first_contribution_date`, `last_contribution_date` |
| `sensor.<wallet>_profit` | `total − invested` | `invested`, `total`, contribution attributes |
| `sensor.<wallet>_profit_pct` | profit as % of the invested amount | `invested`, `total`, contribution attributes |
| `sensor.<wallet>_money_weighted_return` | annual money-weighted wallet return (XIRR) | `invested`, `total`, `method` |
| `sensor.<wallet>_next_execution` | next scheduled date on or after today | plans, allocations, `pending_count`, pending reasons and last processing result |

The wallet total is the market value of all securities plus the settlement
cash balance. If any configured quote or FX rate is unavailable, the aggregate
total, profit and XIRR become unavailable rather than reporting a misleading
partial loss. Every contribution is entered in the wallet's base currency and is **not**
re-converted automatically. The base currency is therefore locked while
contributions, dividends, or plans exist. *Profit %* remains the simple return
`(total − invested) / invested`; the separate *Money-weighted return* sensor
uses all execution dates and the current wallet value to calculate XIRR.

When upgrading from version 1.2, an existing single invested amount is retained
as a legacy contribution with an unknown date. Open **Configure → Edit a
contribution** once to supply its actual execution date.

### Monthly savings plans

Open **Configure → Add a monthly savings plan** and enter:

1. a name and the first scheduled execution date,
2. either a total monthly amount with percentage allocations summing to 100%,
   or fixed base-currency amounts per valor,
3. one or more Yahoo symbols already configured in the wallet.

If the configured opening units already contain past plan purchases, enable
**Earlier plan purchases are already included in the opening balance** and
choose the required cutoff date in the next step. Lots through that date are
retained for performance analysis without adding their units again. Leave this
option off when rebuilding the complete unit balance from zero.

**Include available cash and dividends** can be enabled or disabled per plan.
When enabled, the external monthly contribution remains unchanged for
invested-capital and XIRR calculations, while available settlement cash is
spread pro rata across that month's orders. With fixed allocations, the fixed
amounts are the base and only the extra cash is distributed by their relative
weights. Extra cash is truncated to cents per order and any remainder stays on
the cash account.

An execution remains pending until every allocated symbol has a confirmed
Yahoo close. Weekends and market holidays therefore move the purchase to the
first later trading day with a price. Home Assistant catches up missed dates
from Yahoo history where available. Listings with no Yahoo history are booked
from a confirmed close observed while Home Assistant is running, provided it
falls before the following monthly occurrence. A missing old price is never
replaced with a price several months later.

Generated prices and fractional units are estimates. Open **Configure → Correct
a purchase lot** to replace them with the broker's actual amount or units; the
effective purchase price and every performance sensor update automatically.

Plans can start in the past. Home Assistant creates a separate monthly execution
and a separate lot per valor for every due month through today. For an existing
portfolio, use **Configure → Import a historical purchase lot** and leave
*already included in the opening balance* enabled; this adds its cost and
performance history without counting its units twice. If the corresponding
deposit already exists, select it in the purchase form. A standalone purchase
uses existing cash and **never creates another deposit**. If the funding is
missing, record it separately; the confirmation warns about a negative cash
history. A deposit can also be invested directly in the combined workflow.

Monthly occurrences are identified by plan and calendar month. Changing the
execution day therefore does not duplicate older months. Removing an automatic
execution records that month as skipped; use **Configure → Restore a skipped
execution** if it should be generated again. Removing a plan retains an inert
identity record: if the same schedule and allocation are later re-created, its
old execution identity and skipped months are reused instead of backfilling
those months a second time.

### Ledger safeguards

When a historical purchase is linked to a contribution, the contribution date
must be on or before the purchase date. The legacy opening-balance contribution
created during upgrades represents already-held units: it can only contain
lots marked *already included in the opening balance* and those lots do not
reduce settlement cash. This prevents an opening balance from being used as
funding for a new purchase.

Lots marked as already included in an opening balance cannot exceed the
configured opening units for a symbol. If an automatic execution would exceed
that amount, it remains pending and is marked as requiring repair instead of
being booked. When available cash is reused by automatic plans, the integration
limits it to the lowest ledger balance between the execution date and today, so
a later deposit cannot mask an earlier cash shortfall.

On upgrade to 1.3.2, a legacy percentage plan too small to allocate one cent to
each position is retained but disabled. A saved opening-balance cutoff in the
future is clamped to the migration date. Review any disabled plan before
enabling it again.

Version 1.3.2 also validates all existing purchase lots while migrating. If a
briefly installed 1.3.1 entry contains a legacy lot that is no longer marked as
part of the opening balance, a lot dated before its funding contribution, or
included lots exceeding the configured opening units, the migration stops
instead of guessing how to rewrite financial history. Correct that
inconsistency in 1.3.1 first, then retry the update.

### Dividends and settlement cash

Open **Configure → Add a dividend credit** and enter the net amount shown by the
broker, the booking date, the optional value date, and the paying valor. The
value date determines when the money becomes available to a savings plan. The
credit is return, not new invested capital, and is included in the paying
valor's profit and annualized performance. For tracked purchase lots, each
dividend is assigned in proportion to the units already held on its value date;
later lots therefore do not receive earlier distributions.
When no separate entitlement/ex-dividend date is entered by the broker, this is
necessarily an approximation based on the available value or booking date.

For example, a fictitious 100.00 EUR contribution plus a prior 1.00 EUR dividend
creates 101.00 EUR available cash. Two equal 50.00 EUR base orders receive
0.50 EUR extra each. Both 50.50 EUR purchases use the available cash while
deposited capital increases by only the external contribution of 100.00 EUR.
Any cent-rounding remainder stays in `cash_balance` as part of the wallet total.

### Target allocation

For each valor you can optionally define a **target share** — the percentage
of the wallet it should represent. The integration then computes:

- `share` — the actual share, `valor value / wallet total × 100` (cash is part
  of the denominator),
- `share_deviation` — `share − target_share` in percent points;
  **positive means the valor is overweight** (consider selling),
- `rebalance_amount` — `wallet total × target% − valor value` in the base
  currency; **positive is the amount to buy** to reach the target, negative
  the amount to sell.

Shares are calculated against the complete securities value plus the cash
balance. If one symbol temporarily fails to update, aggregate shares and totals
stay unavailable until the complete portfolio can be valued; healthy individual
position sensors continue to update.

## Service

```yaml
service: my_wallet.refresh
target:
  entity_id: sensor.my_wallet_total
```

Refreshes the whole wallet that owns the targeted entity, immediately.

## Notes

- Update interval is per wallet; Yahoo may rate-limit very aggressive
  polling, so the minimum interval is 5 minutes.
- If a single symbol fails (delisted, typo), the rest of the wallet still
  updates; the affected sensor becomes unavailable and is listed in the total
  sensor's `unavailable_valors` attribute. Aggregate value and performance
  remain unavailable until all symbols have a valid quote and FX rate.

## License

MIT
