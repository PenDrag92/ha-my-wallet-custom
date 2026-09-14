# Reviewed CSV and PDF statements

The assistant's document import adds explicitly recorded deposits, purchases and
net dividends to an **existing** wallet. It uses the same ledger validation and
atomic commit boundary as manual bookings. A purchase uses existing cash; it
never creates an external deposit. Missing units are not estimated from prices.
The existing JSON history and backup imports remain available.

Choose a stable **source label**, for example `Broker depot A`, for each distinct
broker account. It need not contain an account number. Reuse that label and the
source transaction IDs for later statements from the same account. Identical IDs
from different labels cannot silently overwrite or suppress each other. Exact
matches without a known source identity require a visible duplicate decision.
Two real identical transactions in one file remain separate events. An event can
match only one existing booking. The preview preserves the source filename and
CSV line or PDF page/quotation for each row.

## CSV version 1

This is a broker-neutral, documented exchange format, not a claim to parse every
broker's CSV export. Use UTF-8, comma-separated columns, ISO dates and a decimal
point without thousands separators. The header is:

```csv
type,id,date,amount,currency,symbol,units,value_date,note
```

The first seven columns are required; `value_date` and `note` are optional columns.
Every row has a unique, nonempty `id` (maximum 100 characters), stable within the
chosen source label. Quoted CSV fields and multiline notes are supported.

| Type | Meaning | Required fields beyond ID |
| --- | --- | --- |
| `deposit` | Actual external cash funding | `date`, positive `amount`, `currency`; leave symbol/units empty |
| `purchase` | Actual buy using wallet cash | `date`, positive `amount`, `currency`, known wallet `symbol`, actual positive `units` |
| `dividend` | Actual net credited dividend | `date`, positive `amount`, `currency`; optional known `symbol` and explicit `value_date` |

All amounts must be in the wallet's base currency. For purchases, use the actual
settlement cash amount including charges. Its amount divided by actual units is
the effective cost per unit, not a claim about the broker's execution quote.
Dividend `date` is the booking date; only an explicitly supplied `value_date`
changes cash availability. Do not invent a value date. Add a security to the
wallet before importing it, or correct an extracted symbol to its existing Yahoo
symbol. There is no automatic ISIN-to-symbol inference.

[The example](../examples/statement-v1.csv) is wholly synthetic. Never commit real
account statements or personal data to the repository.

## Text PDFs and the selected AI Task provider

PDF support initially covers PDFs with an extractable text layer. The bundled
`pypdf` dependency extracts page text locally in Home Assistant's executor. A scan,
an encrypted PDF or a document with a page containing no extractable text is
rejected. OCR and provider attachment uploads are not implemented in this version.
OCR can be performed separately before uploading a text-layer PDF.

PDF extraction requires an explicitly selected `ai_task.*` entity and a separate
consent checkbox. Home Assistant sends the extracted text to that entity's
configured provider, which may be a cloud service. The integration does not send
the rest of the wallet or give the extraction task wallet tools. Document text is
treated as untrusted data. The returned structure is validated locally, and each
quotation must exist on its stated page. Generated amounts, units, dates and
currencies must occur in that quotation, or be corrected explicitly by the user.

This does not certify a broker layout or guarantee that a model has understood
every transaction. Check the entire statement and every proposed row. Provider
warnings and incomplete extraction block the whole candidate. Sales, withdrawals,
standalone taxes/fees, security transfers and corporate actions are unsupported;
they must not be turned into deposits or purchases. Unsupported or ambiguous
documents should be entered using supported manual workflows or a corrected CSV.

## Review, corrections and commit

Rows show `add`, `duplicate`, `review`, `invalid` or `skipped`. A possible duplicate
offers a choice between an existing record, adding a distinct event and skipping.
Changed content under a known source ID cannot silently replace a confirmed
booking: skip it and use the existing correction dialog if the wallet needs a
correction. A skipped row remains available on a later import of the same file.
All-or-nothing ledger validation checks cash at every historical event date.

User corrections preserve the original source and identify the edited fields.
They are revalidated locally, without another model call. Each review invalidates
the earlier commit token. Final confirmation commits only the prepared candidate,
bound to the requesting administrator, selected wallet and unchanged wallet
snapshot. Drafts expire after ten minutes; editing does not extend their expiry.
Changes to the wallet require a new preview.

Limits: 2 MiB per input, 500 CSV/extracted rows, 20 PDF pages and 80,000 PDF text
characters. Raw PDF bytes, full page text and drafts are held transiently; they
are not saved in the wallet. Committed records retain bounded source quotations,
source IDs and hashes in existing import metadata, which survives backup/restore.
An extraction provider can retain the text according to its own configuration.

## WebSocket adapter contract

All three endpoints require an authenticated administrator.

- `my_wallet/document_prepare`: `entry_id`, `source_id`, `format` (`csv` or `pdf`),
  `filename`, `content` (UTF-8 text or bare PDF base64). PDF additionally requires
  `ai_task_entity_id` and `allow_external: true`.
- `my_wallet/document_review`: `entry_id`, `draft_id`, optional `decisions` and
  `corrections`. Decisions map preview row IDs to `add`, `skip` or an existing
  record ID. Corrections map preview row IDs to explicit `type`, `date`, `amount`,
  `currency`, `symbol`, `units`, `value_date` and/or `note` values.
- `my_wallet/document_commit`: `entry_id`, `token`, `confirm: true`.

Prepare/review return `draft_id`, a nullable `token`, `rows`, `issues`,
`requires_ai_review` and `summary` (`added`, `duplicates`, `cash_change`, `currency`).
Only a non-null token is committable. The UI must invalidate its local token when
editing any input and discard stale asynchronous responses. Commit returns
`entry_id` and consumes the token exactly once.
