# My Wallet assistant

The **Assistant / Assistent** tab combines portfolio reports, monthly attribution,
data-quality findings, savings scenarios, deposit allocation and reviewed statement
imports. Financial results come from My Wallet's calculation and transaction modules.
An optional Home Assistant conversation agent explains those results and calls the
same read-only calculation functions.

## Start with the built-in calculations

Open **My Wallet → Assistant** as a Home Assistant administrator. Reports, scenarios,
allocation and CSV preparation work without configuring an AI provider. Market
valuation and historical prices still use the integration's normal quote sources.

- **Portfolio report:** current wallet and position values, cash, documented capital,
  profit, saved targets and rules that identify records worth checking.
- **Monthly report:** choose a calendar month. Attribution uses reconstructed daily
  closing prices and the current ledger, including external deposits, purchases and
  dividends. It is a different source from intraday Home Assistant Recorder charts.
  Missing prices, incomplete opening quantities or an unreconciled result leave the
  affected attribution unavailable. A current month runs only through available dates.
- **Scenario:** compare the current plan with an explicit return assumption, extra
  monthly funding, a one-off deposit, a selected plan's new rate or a plan pause.
- **Deposit allocation:** calculate how new money can approach saved target weights.
  Existing settlement cash is included only when the checkbox is selected.

These views are available even if an AI provider is unavailable. Missing values are
shown as unavailable; missing market inputs are not treated as zero.

## Connect an existing Home Assistant conversation agent

1. Use a configured conversation agent from **OpenAI Conversation**, **Anthropic**,
   **Google Generative AI Conversation** or **Ollama** in Home Assistant.
2. In that agent's configuration, select only the API named **My Wallet: <wallet
   name>**. The Assistant tab also shows its exact ID, `my_wallet_<entry_id>`.
   Remove Assist and other APIs from this dedicated agent's API selection. Multiple
   wallets can use separate agent configurations.
3. Refresh the Assistant tab's agent list, select the agent and enable the checkbox
   that permits sending the question and required wallet data to that provider.
4. Ask a question such as “Welche Positionen haben im August zum Gewinn beigetragen?”
   or “Was ändert sich bei zusätzlich 100 Euro pro Monat ab Januar?”

My Wallet reuses Home Assistant's provider integrations and credential storage. It
does not create provider accounts, add API keys or change an agent's configuration.
The selected API is checked against both the saved conversation subentry and the
running entity before each request. Agents with another API selected, an unknown
provider implementation or an incomplete reload are excluded.

The named wallet API contains only `WalletReport`, `WalletScenario` and
`WalletAllocation`. It does not expose a booking, import, plan-edit or trading tool.
It is not added to the general Assist API. The same administrator check applies
when the selected API is used outside the panel; calls without an authenticated
active administrator context are refused. Voice devices that do not supply such a
user context therefore cannot read this API.

The connection uses Home Assistant's [conversation interface](https://developers.home-assistant.io/docs/intent_conversation_api/)
and [registered LLM APIs](https://developers.home-assistant.io/docs/core/llm/).
The implementation is tested against Home Assistant **2026.8.3** and uses that version's
explicit API registration contract. The automatic tool-discovery hook in newer Home
Assistant versions deliberately contributes no tools to any API.

## Understand the calculation boundaries

**Scenarios** start with today's actual securities value and settlement cash. Existing
future deposits and plan schedules form the baseline. A selected plan rate override
or pause applies from the requested start date; a pause without a selected plan
affects all future plan funding. Additional monthly funding is independent of those
pauses and begins on the requested start date, including that date. The calculation
applies a constant annual return with daily compounding, including to cash. It does
not separately model taxes, fees, inflation or an additional dividend yield. The
horizon is bounded to 1–50 years. No saved plan is changed.

**Allocation** is a buy-only, cent-based allocation of a proposed deposit according
to existing target percentages. It does not choose securities or forecast returns.
Unspecified target weight and funds beyond target deficits remain as cash. The
result preserves the budget and does not sell overweight positions. Complete current
prices and usable targets are required. No trade or booking is submitted.

**Findings** use transparent rules, not a trained fraud or price-prediction model.
They cover missing valuations or opening costs, historical funding deficits,
estimated purchases, possible duplicate purchases, unassigned dividends, pending
plan executions and missing or partial targets. A target deviation of at least five
percentage points and a price change of at least 20% against the previous close are
highlighted. Such findings are evidence to inspect, not proof of a mistake.

**Generated explanations** are displayed as plain text alongside computed results.
The application does not execute model prose or parse it into financial writes.
Figures should be checked in the result tables. No news retrieval is supplied, so
the assistant has no sourced basis for claiming a particular economic cause of a
price movement.

## Import a statement through review

The document workflow targets an existing wallet and separates extraction, review
and commit. It supports actual external deposits, purchases and credited dividends.
Sales, withdrawals, standalone fees or taxes, transfers and corporate actions are
not supported by this adapter and must not be silently converted into purchases.
A purchase never implies that an external deposit occurred.

Provide a stable **source ID** for the broker account before preparing a file, for
example `broker-account-1`. Reuse that ID for later statements from the same account
and choose a different one for another account. It scopes printed transaction
references so equal reference strings from separate accounts cannot be mistaken
for the same booking.

**CSV** uses a documented event format, not arbitrary broker exports. Use comma
separators and these required headers:

```csv
type,id,date,amount,currency,symbol,units
deposit,deposit-001,2026-08-03,100,EUR,,
purchase,purchase-001,2026-08-03,80,EUR,AAA,8
dividend,dividend-001,2026-08-20,2.50,EUR,AAA,
```

`id` must be a unique source reference within the file. Dates are ISO dates. Amounts
and purchase units must be positive, currency must match the wallet, and security
symbols must already exist in it. Optional columns are `value_date` and `note`.
The example symbol `AAA` must be replaced by an actual configured wallet symbol.

**PDF** requires an explicitly selected Home Assistant `ai_task.*` entity and the
separate document-data checkbox. Text is extracted in Home Assistant and passed to
that entity using [AI Task structured data generation](https://developers.home-assistant.io/docs/core/entity/ai-task/).
The provider receives the document text and extraction instructions; it receives no
wallet tools. Each row must retain an existing source quotation and page reference.
Unsupported or incomplete extraction blocks a commit rather than silently omitting
records. The current adapter handles PDFs with a text layer; encrypted PDFs and
image-only pages require a different source or an OCR adapter. OCR is not included.

Uploads are bounded to 2 MB in the panel, with at most 500 rows, 20 PDF pages and
80,000 extracted PDF characters. Correct recognized fields, review possible matches,
and confirm the final candidate. Commit uses the ordinary ledger validation and
funding checks. Changing wallets or modifying the saved wallet invalidates the
preview. A preview belongs to its administrator and expires after ten minutes.
The reviewed document fingerprint and source evidence remain in import metadata
to support reconciliation and repeated-import detection.

## Data handling and lifetime

The panel's chat authorization is scoped to the administrator, selected wallet and
selected agent. It retains a private Home Assistant conversation ID on the server;
the browser receives an unrelated session token. Requests within a conversation are
serialized, and concurrent wallet edits require fresh results. Sessions expire after
30 minutes and are removed when the wallet unloads. Starting a new conversation
starts a new provider context; it does not delete the provider's history.

The transfer checkbox applies to the selected provider, including Ollama: its
configured server may also be remote. Home Assistant and provider integrations
control their own conversation traces, logging and retention. My Wallet does not
persist a separate chat transcript in its ledger. Uploaded source files are not
saved as files by My Wallet; draft text and candidate records are held temporarily,
and confirmed import source evidence is persisted with the import metadata.

## Verification

Run `python -m unittest discover`, `node --test tests/*.test.mjs` and the normal
lint/security checks. Run `python -m tests.assistant_smoke` separately: the ordinary
unit suite installs Home Assistant test doubles, while this smoke test verifies the
real LLM registry, contexts, schemas, tools and unload behavior. No model credentials,
provider requests or live financial data are required for these tests.
