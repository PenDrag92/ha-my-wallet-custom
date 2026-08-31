# My Wallet for Home Assistant

[![Validate](https://github.com/no-time-for-good-name/ha-my-wallet/actions/workflows/validate.yml/badge.svg)](https://github.com/no-time-for-good-name/ha-my-wallet/actions/workflows/validate.yml)

A [HACS](https://hacs.xyz) custom integration that tracks investment wallets in
Home Assistant. Each wallet is a config entry that holds a list of **valors**
(market instruments) with configurable amounts, valued live via
**Yahoo Finance**.

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
  execution date. Their sum drives the *Invested*, *Profit*, and *Profit %*
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
  manually entered effective price when Yahoo has no history,
- add, edit, or remove dividend credits,
- add monthly savings plans with percentage or fixed-amount allocations,
- edit, pause or remove savings plans without deleting past executions,
- correct the deposit date or external amount of an individual historical
  execution while retaining its purchase lots,
- correct the date, invested amount or purchased units of an automatically
  generated lot,
- add a valor,
- remove a valor,
- edit a valor (amount and target share; clearing the target share removes it).

The sum of target shares may not exceed 100% (a sum below 100% is fine —
the remainder can be assets held outside this integration).

Changes take effect immediately (the wallet reloads automatically).

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
| `sensor.<wallet>_next_execution` | next scheduled or still-pending execution date | plans, allocations and pending executions |

The wallet total is the market value of all available securities plus the
settlement cash balance. Every contribution is entered in the wallet's base currency and is **not**
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

If the configured opening units already contain past plan purchases, keep the
suggested **opening-balance cutoff date**. Lots through that date are retained
for performance analysis but their units are not added a second time. Clear the
date when rebuilding the complete unit balance from zero.

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
from the first confirmed close observed while Home Assistant is running.

Generated prices and fractional units are estimates. Open **Configure → Correct
a purchase lot** to replace them with the broker's actual amount or units; the
effective purchase price and every performance sensor update automatically.

Plans can start in the past. Home Assistant creates a separate monthly execution
and a separate lot per valor for every due month through today. For an existing
portfolio, use **Configure → Import a historical purchase lot** and leave
*already included in the opening balance* enabled; this adds its cost and
performance history without counting its units twice.

### Dividends and settlement cash

Open **Configure → Add a dividend credit** and enter the net amount shown by the
broker, the booking date, the optional value date, and the paying valor. The
value date determines when the money becomes available to a savings plan. The
credit is return, not new invested capital, and is included in the paying
valor's profit and annualized performance. For tracked purchase lots, each
dividend is assigned in proportion to the units already held on its value date;
later lots therefore do not receive earlier distributions.

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

Shares are calculated against the currently available securities plus the cash
balance. If one symbol temporarily fails to update, the remaining shares are
relative to that available total.

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
  updates; the affected sensor becomes unavailable and is listed in the
  total sensor's `unavailable_valors` attribute.

## License

MIT
