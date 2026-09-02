# To do

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
- [ ] Monitor the HACS frontend fix for local custom-integration brand assets
  ([issue #5223](https://github.com/hacs/integration/issues/5223),
  [PR #937](https://github.com/hacs/frontend/pull/937)). My Wallet already ships
  the current Home Assistant `brand/icon.png` and `brand/logo.png`; no further
  repository-side change can replace the placeholder in HACS update cards yet.
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
