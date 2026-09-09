# My Wallet architecture

The 1.11 refactor keeps the existing integration and persisted data. It establishes
shared transaction and valuation boundaries so new features can reuse the same
financial rules.

## Responsibilities

| Layer | Modules | Responsibility |
| --- | --- | --- |
| Financial records | `contributions.py`, `dividends.py`, `plans.py` | Normalize records, define cash events, plan schedules and cash-flow mathematics. No Home Assistant dependency. |
| Transactions | `ledger.py`, `accounting.py` | Prepare detached candidates, validate cross-record invariants, apply correction/skip metadata and accounting revisions. No Home Assistant dependency. |
| Persistence | `store.py` | Check the expected config-entry snapshot, validate, write once and schedule the required reload. |
| Valuation | `valuation.py`, `models.py`, `inflation.py` | Return full-precision nominal/real results for wallets, whole positions and tracked lots. No Home Assistant dependency. |
| Input adapters | `config_flow.py`, `investment_options.py`, `plan_options.py`, `flow_schemas.py` | Collect input, resolve quotes, present previews and map transaction errors to forms. |
| Other booking sources | `executions.py`, `history_import.py`, `followup_import.py`, `corrections.py` | Prepare source-specific candidates using the common transaction rules. |
| Output adapters | `panel.py`, `sensor.py` | Authenticate panel requests, serialize valuations and expose Home Assistant entities. |

The low-level financial modules do not import flows, the panel or sensors. Shared
form schemas do not import their controllers. Network quote retrieval remains in
`yahoo.py`; the ledger and valuation core operate on supplied data.

## Transaction contract

For existing wallets, capture `snapshot = entry.data` before asynchronous work.
Prepare a candidate without mutating that snapshot. Use `commit_wallet_change`
with the same snapshot. Validation and `async_update_entry` run synchronously on
Home Assistant's event loop, with no `await` between the identity check and write.
A concurrent change requires a fresh preview instead of overwriting newer data.

`prepare_change` applies common validation and accounting revisions. Dedicated
operations such as `book_purchase`, `edit_lot`, `edit_contribution`, `put_dividend`,
`delete_dividend` and `delete_contribution` also own their record relationships and
side effects. Deleting a scheduled execution records the skipped period so the
next refresh cannot silently recreate it.

Every ordinary commit checks numeric records, identifiers, symbol/plan references,
future financial events, included opening quantities and historical cash funding.
The funding check considers every cash-effective date in both versions, not just
the latest balance. Bookings on the same date share that date's closing balance.

Existing cash deficits and opening discrepancies may stay unchanged or improve.
The historical purchase form can explicitly confirm newly added purchases with
incomplete funding history. Its `CONFIRMED_PURCHASE` policy cannot change or delete
existing lots, move them between funding groups, reduce funding, or alter dividends
and plans. Ordinary edits and automatic bookings use the default policy.

`validate_records` is also used for imports and backups. A standalone statement
must pass the funding check against an empty account; a follow-up statement is
checked after reconciliation with the existing wallet. A backup is an existing
account snapshot and preserves historical cash/opening discrepancies for repair.
Config-entry migrations and initial creation of a validated wallet remain separate
lifecycle operations, rather than pretending to be ordinary financial edits.

Accounting revisions identify corrections to existing events. Preparing and
committing the same correction yields the same revision; reversing it later yields
a new one. Metadata edits and newly added cash flows preserve existing revisions.
Previously stored 32-character revisions remain valid.

## Valuation contract

`wallet_valuation` includes settlement cash in the terminal value and treats only
external deposits as investor cash flows. Dividends are internal wallet income.

`position_valuation` exposes two scopes:

- **Whole position:** all held units and symbol dividends. Cost and profit are
  unavailable when the opening cost is not fully documented.
- **Tracked purchases:** only recorded lots and the dividends attributed to them.
  Existing tracked-performance sensors retain this scope and their identifiers.

Nominal and inflation-adjusted results share `Performance` objects. Adapters round
for their output contract; they do not calculate returns from rounded display rows.
Missing quotes cannot produce a partial wallet total. Missing inflation coverage
remains unavailable without suppressing otherwise valid nominal results.

## Recorded accounting revisions

`recorded_history.accounting_snapshot` retains the legacy `revision` marker for
old/new snapshot comparisons and adds `financial_revision` for new recordings.
The latter combines the ledger revision (wallet or position scope) with opening
units; it excludes descriptions, aliases and correction-log metadata. New flows
retain the revision while edits to existing financial events change it.

The frontend prefers the financial marker only when both recordings carry it;
otherwise it falls back to the original marker and labels discrepancies as
uncertain legacy comparisons. Observable capital, dividend and unit changes
remain independent safeguards. Diagnostic timestamps identify the first affected
recording, not the exact edit time. Recorder rows are never rewritten.

## Compatibility and verification

Config-entry version **7**, backup format version **1**, contribution/lot nesting,
entity unique IDs and the dashboard response fields are retained. No conversion
of existing positions or Recorder rows is required by this refactor.

Run the normal unit suite and the separate checks against real Home Assistant:

```sh
python -m unittest discover
python -m tests.schema_defaults
python -m tests.valuation_smoke
python -m tests.recorder_smoke
node --test tests/*.test.mjs
ruff check .
ruff format --check .
bandit -q -r custom_components/my_wallet
```

`test_wallet_transactions.py` exercises deposit → purchase → dividend → reinvestment
→ correction → backup → restore, concurrent writes, invalid direct commits,
historical recovery and deletion/re-execution of savings plans.
`valuation_smoke.py` imports real Home Assistant sensor classes and compares their
values and identifiers with the dashboard, using known balances, FX conversion,
incomplete opening costs, missing quotes and missing inflation coverage.
