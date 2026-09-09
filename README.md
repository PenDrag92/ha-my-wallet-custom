# My Wallet for Home Assistant

A [HACS](https://hacs.xyz) custom integration that tracks investment wallets in
Home Assistant. Each wallet is a config entry that holds a list of **valors**
(market instruments) with configurable amounts, valued live via
**Yahoo Finance**.

Version 1.11.3 requires **Home Assistant 2026.8 or newer**.

Project home: <https://github.com/PenDrag92/ha-my-wallet-custom>. Report bugs
or feature requests through the [issue tracker](https://github.com/PenDrag92/ha-my-wallet-custom/issues).

## 1.11.3: fitted axes for every period

Every history period, including full history and forecasts, now fits its axes to
the visible curves. All displayed portfolio, contribution and target values stay
within the scale, with rounded currency ticks and padding. Zero remains visible
when it occurs in the data, but is no longer forced for an existing portfolio.
Settlement cash keeps its separate fitted axis.

## 1.11.2: clearer recording diagnostics

Day/week metrics now use financial revisions from the shared ledger. Editing
notes or aliases, or attaching an ordinary new purchase to an edited deposit,
does not count as a correction in new recordings. Actual financial edits still
invalidate comparisons across the affected samples.

Warnings show the observable reason and first affected recording time in the
Home Assistant time zone. Older snapshots retain their original comparison;
they may still flag metadata changes and cannot reveal the exact historical
cause. A date-only correction record is never displayed with an invented time.
No recorded history or wallet bookings are rewritten.

## 1.11.1: fixes from the refactor review

Statement source links now follow stable record IDs when normalization sorts
bookings and dividends. Latest-first statements and several bookings on the same
day keep their correct identity during initial and overlapping imports.
Chronological cash checks retain small credits across dates, including when a
later purchase offsets a much larger balance.

See [REVIEW-1.11.1.md](REVIEW-1.11.1.md) for the findings and verification.

## 1.11.0: shared booking and valuation core

Options, dashboard actions, statement reconciliation and automatic savings-plan
bookings now share a validated transaction boundary. Purchases, deposit edits,
dividend edits and deletions use common ledger operations. Every commit checks
references, dates, opening quantities and intermediate cash balances against the
snapshot that was used to prepare it.

Sensors and the dashboard use the same full-precision profit, return and
inflation calculations. Whole-position and tracked-purchase results retain their
explicitly different scopes when opening costs are incomplete. Shared form
schemas no longer depend on the configuration-flow controller.

The stored config-entry version, backup format and existing entity identifiers
remain unchanged. Existing historical cash deficits and opening discrepancies
can still be repaired incrementally; confirmed historical purchases keep their
separate confirmation workflow. Cash balances are calculated from a common event
stream, with one chronological pass for funding checks.

See [ARCHITECTURE.md](ARCHITECTURE.md) for module boundaries and validation commands.

## 1.10.2: reliable reconciliation and accounting corrections

Overlapping statement imports keep distinct purchases and ask before changing
confirmed quantities. Existing settlement cash is included when checking a new
statement. Changing the selected wallet clears the import preview; confirmation
is checked against the preview's original target on the server.

Changes to purchases and dividends cannot silently leave recorded purchases
unfunded. Historical savings-plan references protect their instruments from
removal. Corrections to existing holdings, including confirmed estimates and
recalculations, are identified as accounting changes in day/week returns.

Dividend booking and value dates must not be in the future. Backups retain the
accounting revision and support empty or cash-only wallets. XIRR supports long
investment histories without a numerical division-by-zero error.

## 1.10.1: readable day and week charts

The **1 day** and **1 week** views fit their vertical scale to the visible
values, with a little space above and below and rounded currency steps. Small
price changes remain visible without forcing the axis to start at zero. A
note beside the legend identifies the automatic scale. Selecting a different
position or period adjusts it again; settlement cash keeps its own scale.
Missing samples remain gaps and do not pull the scale toward zero.

The month range and longer views keep their existing zero-based scales.
This changes only the chart display, not stored values or performance.

## 1.10.0: shorter history ranges and period performance

Under **My Wallet → History**, choose **1 day**, **1 week** or **1 month**.
The first two show the last 24 hours or 7 days of recorded HA sensor states,
including the holdings that existed at each update. They work for the whole
wallet and for the position selected above the chart. The month range and
longer historical ranges continue to use reconstructed daily closing prices.
Historical range metrics exclude any future forecast points.

The period cards show opening/closing value, deposits (or position purchases),
dividends, gain and return. Gain excludes external deposits; position gain
includes attributed dividends, while wallet gain already includes dividends
in settlement cash. Return links the valuation intervals and treats cash flows
as occurring at the end of their interval. It is an approximation from the
available samples, not an annualized return or a substitute for broker trade
timestamps. Recorded flows use the time their updated sensor state was saved;
late entries do not rewrite old intraday recordings. The purchasing-power
switch also adjusts these period values and flows to today's money, leaving
uncovered results unavailable.

Day/week history needs the corresponding value sensor enabled and included in
[Home Assistant Recorder](https://www.home-assistant.io/integrations/recorder/).
Recorder normally retains detailed states for 10 days, but your exclusions and
retention settings take precedence. My Wallet does not enable Recorder, change
its filters, increase retention or restore purged data. Renaming entities does
not break the lookup. Opening these ranges reads only the selected wallet's
sensors; it does not make additional Yahoo requests or change the normal poll
interval. The display is a sequence of saved values, **not a real-time trading
feed**. Timestamps use Home Assistant's configured time zone.

Existing compatible recordings can be used immediately. From 1.10.0 onward,
each successful refresh also saves the accounting basis and refresh timestamp
on the existing value sensors, including updates with unchanged prices. This
adds a small amount of Recorder data. Older records need a matching recorded
profit sensor for their cost basis; value history can still be displayed when
that basis is unavailable. Missing prices, missed new refreshes and stale ends
remain gaps. Gain and return stay blank for incomplete periods or detected
corrections rather than classifying edited holdings as investment performance.
The view explains missing or excluded sensors and paused/unavailable Recorder.
Stored history remains untouched; use the daily history for reconstruction
from the currently corrected ledger.

After updating through HACS, restart Home Assistant and reload the dashboard.
No reconfiguration or deletion of the existing wallet is needed.

## Allocation differences

The current and forecast allocation tables show **Difference from target** as
`+15.00 %`, `-15.00 %` or `0.00 %`, with **too much**, **too little** or
**on target** on a smaller, muted second line.
The percentage refers to the entire portfolio value: a 25% actual share with a
10% target means 15% of the portfolio value too much in that position. A note
below the table explains this basis. This is the difference between the two
shares, not a relative change from the target; zero targets work as before.
Colors remain neutral. Stored data, calculations and sensor units are unchanged.

## 1.9.1: edit units directly in the dashboard

Click an underlined unit count in the allocation overview, positions table,
position metrics, purchase details or transaction ledger. A focused dialog opens
with that position or purchase already selected. Enter the actual units with a
decimal comma or point, preview the change, then save. Blank, negative and
ambiguous inputs are rejected; Escape or Cancel discards the unsaved edit.

A total-position correction still updates one explicitly identified purchase
or opening holding, not an invented trade. The dialog prefers an estimated
purchase when available and lets you change that assignment. The preview shows
both the position total and the affected holding. Purchase dates, recorded
payments, deposits and cash stay unchanged. Use a per-purchase edit only when
you know that purchase's actual units. This does not add a PDF import feature.

## 1.9.0: future deposits and zero allocation targets

Use **My Wallet → Planning → Plan a deposit** to enter a future one-off amount,
date and optional note. Pending deposits can be edited or cancelled there.
Alternatively use **Configure → Plan a future deposit**; the regular deposit
form also accepts future cash deposits, without immediate purchases.

A planned deposit is excluded from today's capital, cash, performance, booked
transactions and CSV until its date. On that date it enters the cash ledger
automatically, once, using its original ID. It is not a separate recurring
payment. My Wallet records this schedule; it does not transfer money or send
broker orders. Change or cancel the plan before the date if the payment will
not happen. Due deposits can be corrected through the existing options, with
checks that prevent recorded purchases from losing their funding.

Enable **Reinvest available settlement cash** on the savings plan that should
invest the additional money. Its next eligible execution invests the one-off
deposit plus the normal monthly rate using its allocation, retaining any
rounding remainder in cash. The Planning tab shows the currently expected plan
and schedule date. If no eligible plan uses cash, the amount stays on the cash
account. With multiple eligible plans, the first execution consumes available
cash; plans on the same day use a stable order. Actual purchases still wait for
confirmed market closes and may occur later than the calendar schedule.

The target curve includes the deposit from its chosen date. Forecast allocation
now also simulates cash reinvestment in chronological order, including current
cash, same-day deposits, pauses, skipped months and plan end dates. Transfers
from cash into securities never count as a second external contribution. The
existing uniform expected-return assumption still applies to the projected
portfolio, including cash. Complete JSON backups retain planned deposits.

An explicit **0% allocation target** is now distinct from an empty target.
Dashboard tables and deviation sensors report the difference from zero.
Zero-value positions remain visible in the allocation table. Targets discarded
by older versions cannot be distinguished from intentionally empty targets and
must be entered again once after updating.

## 1.8.0: purchasing power and consistent position names

The administrator dashboard can switch between nominal values and a
**purchasing-power-adjusted** view. Historical amounts use Germany's official
monthly all-items HICP from Eurostat. My Wallet refreshes that public series at
most once per day, keeps a validated local cache and visibly identifies the
latest available month. If Eurostat is temporarily unavailable, the last cache
remains usable and is marked as stored data.

The purchasing-power view applies consistently to wallet and position
performance, purchase lots, value charts, monthly/yearly summaries,
transactions and forecast allocations. Current market values remain today's
values; past deposits, purchase costs, dividends and historical values are
converted to today's purchasing power before profit and return are calculated.
When the official series does not cover every required dated amount, My Wallet
leaves the affected real result unavailable instead of mixing adjusted and
unadjusted figures.

Future values use a separate **expected annual inflation** assumption, set to
2% by default and editable under **Configure → Edit wallet settings**. The
selected 1–50 year forecast then exposes its value, contributions, growth,
allocation and inflation effect both nominally and in today's purchasing power.
The expected return and expected inflation remain independent scenario inputs;
neither changes transactions, holdings or live prices.

Position display names now appear together with their stable technical symbol
throughout savings-plan, investment, dividend, correction and configuration
flows as well as the dashboard and entity names. Stored symbols, entity unique
IDs, Yahoo requests and CSV identifiers remain unchanged.

## 1.7.0: flexible forecasts and a shorter dashboard

The administrator dashboard is divided into **Overview**, **Positions**,
**History** and **Transactions & data** tabs. The selected wallet and position
stay active when moving between tabs, and the last tab is remembered in the
current browser.

Forecasts now include a 30-year preset and a **Custom** option for any whole
number from 1 to 50 years. The chosen date drives the target breakdown,
portfolio continuation, allocation and projected position values together.
Historical values remain daily. Long future curves use exact monthly samples
and savings-plan execution dates so a 50-year view stays compact and responsive.

For a planned increase such as an additional EUR 300 per month, add a second
monthly savings plan and set its first execution to the month in which the
increase starts. Keep the existing plan unchanged. The forecast automatically
combines both plans from that date; each plan can keep its own allocation and
can later be paused or ended independently.

## 1.6.1: target composition

The target-comparison card now explains how its result is composed. For the
selected date it shows the contributions included in the target and the
expected growth generated by the configured return. A future horizon also
shows the portion of contributions still planned from today onward. Booked
one-off deposits and the historically applicable planned savings rates use the
same rules as the target curve, so the displayed contributions plus expected
growth equal the displayed target value.

Selecting a future horizon also changes the allocation card and adds projected
value/share columns to the positions table. The projection starts with today's
real position values, applies the wallet's expected return uniformly and routes
each future savings-plan payment through its configured allocation. Current
units, prices and performance remain visibly current because My Wallet does not
invent individual future security prices.

The value chart keeps the real line ending today and continues with a separately
labelled dashed portfolio forecast. Future tooltips show that forecast, planned
contributions and the ideal compound target instead of empty real-value fields.
The overview metrics use balanced responsive rows so the dividend metric no
longer wraps onto a line by itself on wide dashboards.

Today's target sensor exposes the same breakdown as `target_contributions` and
`target_growth` attributes.

## 1.6.0: compound target and future forecast

Each wallet now has an **expected annual return**, set to 7% by default and
editable under **Configure → Edit wallet settings**. My Wallet derives the
geometric monthly and daily rates and builds an ideal compound-return target
from the documented wallet start. Changing the expected return recalculates
only the target; it never changes transactions, units, plans or market values.

The target uses the historically applicable savings-plan amount for each month,
including a payment that is already due but not yet booked. Multiple plans are
added together. Historical rate changes, pauses, end dates and explicitly
skipped months are respected, and an existing automatic execution is not
counted twice. Manual one-off deposits enter on their actual dates. Dividends
are not added separately because the expected return is treated as a total
return assumption.

The administrator dashboard compares today's target with the real wallet total,
including settlement cash. Its dashed target curve can be hidden. A forecast
selector continues that same curve for 1, 3, 5, 10 or 20 years; active plans
without an end date continue through the selected horizon. The new compound
target sensor exposes the expected annual and derived monthly return, documented
start date, actual value and absolute/percentage deviation.

My Wallet leaves the target unavailable when an old opening holding or wallet
start is not documented reliably. It does not guess a starting date or value.
The target and forecast are mathematical scenarios, not guaranteed returns or
investment advice.

## 1.5.0: allocation, purchase details and complete backups

The administrator dashboard now shows the current allocation as a donut and a
table with actual shares, optional targets and deviations. Settlement cash is
part of the same total used throughout My Wallet. Select a position to inspect
its individual purchase lots, including dates, exact units, entry prices,
current values, attributed dividends, profit and simple or annualized returns.

The overview shows the earliest documented **wallet start**, and a selected
position shows its earliest documented **position start**. My Wallet does not
guess dates for old opening holdings: when their acquisition history is
incomplete, the corresponding start date remains unavailable.

The new **Data export** section offers the transaction CSV and a complete,
versioned JSON backup. Importing such a backup validates and previews it, then
restores it as a separate wallet so an existing entry is never overwritten.
The JSON backup contains financial configuration data and should be stored as
carefully as a broker statement.

Summary cards keep their values aligned even when labels wrap, wide detail
tables stay inside the dashboard on small screens, and the display-name editor
uses a neutral example. Local icon and logo files follow Home Assistant's current
brand format. Home Assistant can use them on integration pages; HACS currently
shows a placeholder on update cards because its frontend does not yet read local
custom-integration brand assets.

## 1.4.1: clearer position selection and display names

The position selector now sits directly above the metrics it controls. The
same selection filters the value curve, monthly/yearly summaries and transaction
history, while the selected row is highlighted in the position table.

Use **Edit names** in the position table to add optional, persistent display
names such as `World ETF`. The dashboard shows that name together with the original
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
- **Compound target and forecast** — configure an expected annual return per
  wallet, compare the actual total with an ideal target and extend the same curve
  up to 50 years using the applicable savings-plan history.
- **Inflation and purchasing power** — compare nominal results with historical
  figures adjusted using official monthly Eurostat HICP data for Germany, and
  deflate future scenarios with a configurable expected inflation rate.
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
  inspect performance, start dates, allocation and individual purchase lots,
  compare monthly/yearly results, reconcile follow-up JSON statements, correct
  exact units with a review step, export CSV or a complete restorable JSON
  backup, and assign readable position display names without changing their
  Yahoo symbols.
- **Target allocation** — optionally set a target share (in %) for each valor
  to see how far its actual share deviates from the target, plus a rebalancing
  hint in the base currency.
- **Sensors** — value and performance sensors per valor plus wallet totals,
  profit, XIRR, compound target and the next savings-plan execution, grouped
  under one device.
- **`my_wallet.refresh` service** — force an immediate update of selected
  wallets without waiting for the schedule.
- **Translations** — English, German, Polish, and Czech.

No external Python dependencies — prices are fetched directly from Yahoo
Finance's chart API and official German all-items HICP data from Eurostat's
public dissemination API using Home Assistant's bundled `aiohttp` client.

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
7 preserves the ledger, position names and inflation settings. Do not downgrade
to a release that cannot read schema-7 data; restore the backup as well.
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

My Wallet includes local Home Assistant brand assets. If HACS itself still shows
**Icon not available** in its update list, this is a known HACS frontend
limitation and does not mean that the integration files are incomplete.

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
   - **Expected annual return** — target/forecast assumption in percent
   - **Official inflation data** — Eurostat HICP for Germany, or disabled
   - **Expected annual inflation** — future purchasing-power assumption in
     percent
3. Add valors: enter the **Yahoo Finance symbol** and the **opening amount** of
   units you already hold. Tracked savings-plan purchases are added to this
   opening balance automatically. Optionally enter a **target share (%)** — the percent of the
   wallet this valor should hold — to enable the deviation sensor.
   Tick *Add another valor* to keep adding, or submit to finish.

### Managing a wallet

Open the config entry and click **Configure** to:

- edit wallet settings (name, base currency, update interval, expected return,
  official inflation source and expected future inflation),
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
| `sensor.<wallet>_target_value` | today's compound target in the base currency | `expected_annual_return`, `monthly_return`, `wallet_start_date`, `actual_value`, `absolute_deviation`, `percentage_deviation`, `target_contributions`, `target_growth`, `calculation_basis` |
| `sensor.<wallet>_next_execution` | next scheduled date on or after today | plans, allocations, `pending_count`, pending reasons and last processing result |

When official inflation data are enabled and cover all required dates, the
relevant wallet and tracked-position sensors also expose
`inflation_adjusted_invested`, `inflation_adjusted_profit`,
`inflation_adjusted_performance_pct` and
`inflation_adjusted_annualized_performance_pct`. The accompanying
`inflation_source`, `inflation_data_month`, `inflation_data_stale` and
`expected_annual_inflation` attributes document the data and assumption used.

The wallet total is the market value of all securities plus the settlement
cash balance. If any configured quote or FX rate is unavailable, the aggregate
total, profit and XIRR become unavailable rather than reporting a misleading
partial loss. Every contribution is entered in the wallet's base currency and is **not**
re-converted automatically. The base currency is therefore locked while
contributions, dividends, or plans exist. *Profit %* remains the simple return
`(total − invested) / invested`; the separate *Money-weighted return* sensor
uses all execution dates and the current wallet value to calculate XIRR.

Historical purchasing-power calculations use the official
[Eurostat monthly HICP dataset](https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_minr/default/table?lang=en)
for Germany, all items, beginning in January 1996. The series is monthly and
official publication naturally lags the current date. A transaction before the
available series, an unknown transaction date or missing official data leaves
the dependent adjusted result unavailable. Future purchasing power is a
mathematical scenario based on the configured expected inflation, not an
official inflation forecast or investment advice.

When upgrading from version 1.2, an existing single invested amount is retained
as a legacy contribution with an unknown date. Open **Configure → Edit a
contribution** once to supply its actual execution date.

### Monthly savings plans

Open **Configure → Add a monthly savings plan** and enter:

1. a name and the first scheduled execution date,
2. either a total monthly amount with percentage allocations summing to 100%,
   or fixed base-currency amounts per valor,
3. one or more Yahoo symbols already configured in the wallet.

To schedule a future increase without rewriting the existing plan, create a
second plan for the additional amount and use the intended month as its first
execution date. For example, keep the current plan and add another EUR 300 plan
starting on the planned change date. The forecast combines both plans from then
on, while their allocations, pauses and end dates remain independent.

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
