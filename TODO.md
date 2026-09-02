# To do

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
