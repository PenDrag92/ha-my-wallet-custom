# To do

## Done

- [x] Make history warnings dismissible with an acknowledgement control. Keep
  acknowledgements per user and wallet across refreshes. Bring back a notice
  when a new gap or accounting change is detected, and keep the reason available
  on demand when a metric cannot be calculated.

- [x] Expose My Wallet's existing read-only reports, scenarios and deposit
  allocation through the Home Assistant MCP connection. Keep the dashboard
  conversation agent optional.

- [x] Refresh the appropriate history when switching between Recorder and
  longer daily ranges. Explain the difference in valuation bases.
- [x] Preserve period metrics before and after an accounting correction.
  Show the overall value change separately from comparable investment results.

- [x] Prepare local day boundaries for 1.13 day/week charts, including individual
  positions and settlement cash. Use HA's time zone, handle DST and retain all
  grid lines when date labels are thinned on narrow screens. Included in 1.13.

- [x] Keep useful period metrics despite missing intermediate quotes in 1.12.1.
  Trim to valid in-range endpoints and show actual evaluation dates. Preserve
  reliable monetary gain, label returns with flows across gaps as approximations,
  and keep unknown correction effects or incomplete flows unavailable. Preserve
  chart gaps and Recorder data; cover nominal/real metrics, corrections inside
  gaps, missing boundaries and individual-position cards in regression tests.
- [x] Explain pending savings-plan bookings directly in the dashboard in 1.12.1:
  show plan/date/reason and instrument aliases, distinguish missing market data
  from repair-required cases, and use the correct next-execution sensor name.
- [x] Make the allocation-difference column less crowded in 1.10.0:
  keep the signed percentage on the first line and move "too much", "too little"
  or "on target" to a smaller, muted second line, without the inline separator.
  Apply this to current and forecast allocation tables. Keep the short heading,
  neutral colors, calculation and zero-target handling. Bundle with the next
  push; included with the shorter history ranges and period metrics.
- [x] Add 1-day and 1-week Recorder history, a 1-month daily-close range and
  flow-adjusted period metrics for the wallet and individual positions in
  1.10.0. Keep unknown/stale samples visible as gaps and explain missing
  recordings without changing Recorder settings or adding Yahoo requests.
- [x] Make allocation-target deviations easier to understand. Label positive
  and negative differences as overweight and underweight instead of using
  gain/loss colors that make an overweight position look beneficial. Include
  positions with a 0% target; keep the calculation unchanged. Included in
  1.9.1 with direct unit editing. Refined in 1.9.2 with a percentage of the
  whole portfolio and plain "too much" / "too little" wording in one line.
- [x] Track support for local brand assets in HACS. My Wallet ships
  `brand/icon.png` and `brand/logo.png`. HACS closed
  [issue #5223](https://github.com/hacs/integration/issues/5223) after confirming
  support in Marketplace, shipped with Home Assistant 2026.11. The old HACS UI
  may still show a placeholder.
- [x] Use position aliases consistently in every user-facing integration view,
  followed by the stable technical symbol, for example
  `World ETF (ABC.DE)`. Cover savings-plan selection, allocation,
  confirmation and result views; direct-investment allocation; manual purchase
  lots and contribution summaries; dividend sources; position edit/remove
  dialogs; opening-balance warnings; and position sensor display names. Keep the
  raw symbol for stored references, Yahoo requests, entity/unique IDs, logs,
  structured sensor attributes and the CSV `symbol` column; continue exporting
  the alias separately.
- [x] Align dashboard summary cards across one-line and wrapped labels,
  including responsive layouts.
- [x] Replace the repeated issuer-specific alias example with the neutral
  `e.g. World ETF` / `z. B. Welt-ETF` placeholder.
