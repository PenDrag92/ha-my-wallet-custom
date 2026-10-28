"""Statement evidence, money flow, overlap and user-bound review regressions."""

from __future__ import annotations

import base64
import inspect
import io
import unittest
from copy import deepcopy
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from custom_components.my_wallet import const as c
from custom_components.my_wallet import document_api
from custom_components.my_wallet.backup import create_backup, prepare_backup
from custom_components.my_wallet.contributions import (
    all_lots,
    invested_total,
    make_contribution,
)
from custom_components.my_wallet.dividends import cash_balance, dividend_total
from custom_components.my_wallet.followup_import import IMPORT_LINKS, IMPORT_RECORDS
from custom_components.my_wallet.statement_documents import (
    ai_document_draft,
    correct_document,
    extract_pdf_pages,
    parse_csv_document,
    prepare_document,
)
from tests.test_panel_regressions import Connection, hass_with
from tests.test_v140_features import wallet

_prepare_document = inspect.unwrap(document_api.ws_document_prepare)
_review_document = inspect.unwrap(document_api.ws_document_review)
_commit_document = inspect.unwrap(document_api.ws_document_commit)


TODAY = date(2026, 9, 14)
HEADER = "type,id,date,amount,currency,symbol,units,value_date,note\n"
CSV = HEADER + (
    "purchase,broker:buy1,2026-01-03,50,EUR,AAA,5,,Purchase\n"
    "dividend,broker:div1,2026-01-05,3,EUR,AAA,,2026-01-04,Net credit\n"
    "deposit,broker:deposit1,2026-01-02,100,EUR,,,,Cash transfer\n"
)


def draft(content=CSV):
    return parse_csv_document(
        content, filename="synthetic.csv", source_id="Brokerdepot"
    )


def pdf_result(**changes):
    row = {
        "id": "BUY-1",
        "type": "purchase",
        "date": "2026-01-03",
        "amount": "50",
        "currency": "EUR",
        "symbol": "AAA",
        "units": "5",
        "value_date": "",
        "note": "",
        "page": 1,
        "quote": "BUY-1 Purchase AAA 03.01.2026 5 units EUR 50",
    }
    row.update(changes)
    return {"complete": True, "warnings": [], "rows": [row]}


class StatementDocumentTests(unittest.TestCase):
    def test_events_are_atomic_and_purchases_never_create_external_funding(self):
        before = wallet()
        preserved = deepcopy(before)
        result, preview = prepare_document(draft(), before, today=TODAY)
        self.assertEqual(before, preserved)
        self.assertEqual(
            (invested_total(result), cash_balance(result), dividend_total(result)),
            (100, 53, 3),
        )
        self.assertEqual(all_lots(result)[0][c.LOT_UNITS], 5)
        self.assertFalse(all_lots(result)[0][c.LOT_ESTIMATED])
        self.assertEqual(preview["summary"]["added"], 3)
        purchase = next(
            row
            for row in result[c.CONF_CONTRIBUTIONS]
            if row[c.CONTRIBUTION_SOURCE] == c.CONTRIBUTION_SOURCE_PURCHASE
        )
        self.assertEqual(purchase[c.CONTRIBUTION_AMOUNT], 0)
        self.assertEqual(preview["rows"][0]["source"]["row"], 2)

    def test_purchase_only_uses_existing_cash_and_never_later_funding(self):
        document = draft(HEADER + "purchase,buy,2026-01-03,50,EUR,AAA,5,,\n")
        for funding_date, allowed in (("2026-01-02", True), ("2026-01-04", False)):
            before = wallet([make_contribution(100, funding_date)])
            result, preview = prepare_document(document, before, today=TODAY)
            if allowed:
                self.assertEqual(invested_total(result), 100)
                self.assertEqual(cash_balance(result), 50)
            else:
                self.assertIsNone(result)
                self.assertIn("cash_conflict", preview["issues"])

    def test_dividend_only_import_and_earlier_dividend_have_stable_links(self):
        document = draft(
            HEADER
            + "dividend,div-late,2026-02-03,2,EUR,AAA,,,\n"
            + "dividend,div-early,2026-01-03,1,EUR,AAA,,,\n"
        )
        result, preview = prepare_document(document, wallet(), today=TODAY)
        self.assertEqual(dividend_total(result), 3)
        self.assertEqual(preview["summary"]["added"], 2)
        links = result[IMPORT_LINKS]["dividends"]
        self.assertEqual(
            set(links.values()),
            {row[c.DIVIDEND_ID] for row in result[c.CONF_DIVIDENDS]},
        )
        replay, summary = prepare_document(document, result, today=TODAY)
        self.assertEqual(dividend_total(replay), 3)
        self.assertEqual(summary["summary"]["duplicates"], 2)

    def test_reimport_and_reordered_overlap_are_idempotent_and_backups_keep_provenance(
        self,
    ):
        result, _ = prepare_document(draft(), wallet(), today=TODAY)
        repeated, preview = prepare_document(draft(), result, today=TODAY)
        self.assertEqual(repeated, result)
        self.assertEqual(preview["summary"]["duplicates"], 3)
        reordered = HEADER + "\n".join(reversed(CSV.splitlines()[1:])) + "\n"
        overlap, preview = prepare_document(draft(reordered), result, today=TODAY)
        self.assertEqual(preview["summary"]["added"], 0)
        self.assertEqual(cash_balance(overlap), 53)
        restored, _ = prepare_backup(
            create_backup(overlap, title="Synthetic", created_at=datetime(2026, 9, 14)),
            today=TODAY,
        )
        self.assertEqual(restored[IMPORT_RECORDS], overlap[IMPORT_RECORDS])
        self.assertEqual(restored[IMPORT_LINKS], overlap[IMPORT_LINKS])

    def test_two_identical_new_events_remain_distinct(self):
        document = draft(
            HEADER
            + "deposit,a,2026-01-03,50,EUR,,,,\n"
            + "deposit,b,2026-01-03,50,EUR,,,,\n"
        )
        result, preview = prepare_document(document, wallet(), today=TODAY)
        self.assertEqual(invested_total(result), 100)
        self.assertEqual(preview["summary"]["added"], 2)

    def test_source_namespace_prevents_foreign_broker_id_collisions(self):
        content = HEADER + "deposit,1,2026-01-03,50,EUR,,,,\n"
        first = parse_csv_document(content, filename="a.csv", source_id="Broker A")
        second = parse_csv_document(content, filename="b.csv", source_id="Broker B")
        before, _ = prepare_document(first, wallet(), today=TODAY)
        pending, preview = prepare_document(second, before, today=TODAY)
        self.assertIsNone(pending)
        self.assertEqual(preview["rows"][0]["status"], "review")
        candidate, _ = prepare_document(
            second, before, today=TODAY, decisions={"row-2": "add"}
        )
        self.assertEqual(invested_total(candidate), 100)

    def test_skipped_rows_can_be_imported_later_from_the_same_file(self):
        document = draft(
            HEADER
            + "deposit,a,2026-01-03,50,EUR,,,,\n"
            + "deposit,b,2026-01-04,25,EUR,,,,\n"
        )
        first, _ = prepare_document(
            document, wallet(), today=TODAY, decisions={"row-3": "skip"}
        )
        self.assertEqual(invested_total(first), 50)
        second, preview = prepare_document(document, first, today=TODAY)
        self.assertEqual(invested_total(second), 75)
        self.assertEqual(preview["summary"]["added"], 1)
        self.assertEqual(len(second[IMPORT_RECORDS]), 1)
        self.assertEqual(len(second[IMPORT_RECORDS][0]["sources"]), 2)

    def test_semantic_overlap_requires_review_and_one_to_one_matching(self):
        before = wallet([make_contribution(50, "2026-01-03", contribution_id="manual")])
        document = draft(
            HEADER
            + "deposit,a,2026-01-03,50,EUR,,,,\n"
            + "deposit,b,2026-01-03,50,EUR,,,,\n"
        )
        result, preview = prepare_document(document, before, today=TODAY)
        self.assertIsNone(result)
        self.assertEqual(
            [row["status"] for row in preview["rows"]], ["review", "review"]
        )
        reused, _ = prepare_document(
            document,
            before,
            today=TODAY,
            decisions={"row-2": "manual", "row-3": "manual"},
        )
        self.assertIsNone(reused)
        result, preview = prepare_document(
            document, before, today=TODAY, decisions={"row-2": "manual", "row-3": "add"}
        )
        self.assertEqual(invested_total(result), 100)
        self.assertEqual(preview["summary"]["added"], 1)

    def test_stable_source_conflict_never_silently_overwrites_or_duplicates(self):
        first = HEADER + "deposit,a,2026-01-03,50,EUR,,,,\n"
        result, _ = prepare_document(draft(first), wallet(), today=TODAY)
        changed = draft(first.replace(",50,", ",51,"))
        for decisions in ({}, {"row-2": "add"}):
            pending, preview = prepare_document(
                changed, result, today=TODAY, decisions=decisions
            )
            self.assertIsNone(pending)
            self.assertIn(
                "source_record_conflicts_with_wallet", preview["rows"][0]["issues"]
            )
        kept, _ = prepare_document(
            changed, result, today=TODAY, decisions={"row-2": "skip"}
        )
        self.assertEqual(invested_total(kept), 50)

    def test_missing_units_bad_currency_unknown_symbol_and_unsupported_types_block(
        self,
    ):
        for line in (
            "purchase,p,2026-01-03,50,EUR,AAA,,,",
            "purchase,p,2026-01-03,50,USD,AAA,5,,",
            "purchase,p,2026-01-03,50,EUR,UNKNOWN,5,,",
            "sale,p,2026-01-03,50,EUR,AAA,5,,",
            "deposit,p,2026-01-03,nan,EUR,,,,",
            "deposit,p,2027-01-03,50,EUR,,,,",
        ):
            with self.subTest(line=line):
                pending, preview = prepare_document(
                    draft(HEADER + line + "\n"), wallet(), today=TODAY
                )
                self.assertIsNone(pending)
                self.assertEqual(preview["rows"][0]["status"], "invalid")

    def test_explicit_corrections_keep_original_source_and_are_revalidated(self):
        original = draft(HEADER + "purchase,p,2026-01-03,50,EUR,AAA,,,\n")
        changed = correct_document(original, {"row-2": {"units": "5"}})
        self.assertEqual(changed["rows"][0]["source"], original["rows"][0]["source"])
        self.assertEqual(changed["rows"][0]["edited_fields"], ["units"])
        self.assertEqual(original["rows"][0]["units"], "")
        result, _ = prepare_document(
            changed, wallet([make_contribution(100, "2026-01-01")]), today=TODAY
        )
        self.assertEqual(all_lots(result)[0][c.LOT_UNITS], 5)
        for corrections in (
            {"row-2": {"source": {}}},
            {"missing": {"units": 5}},
            {"row-2": {"units": True}},
        ):
            with self.assertRaises(ValueError):
                correct_document(original, corrections)

    def test_csv_limits_strict_columns_ids_and_physical_multiline_sources(self):
        for content in (
            "type,id\ndeposit,a\n",
            HEADER + "deposit,a,2026-01-03,50,EUR,,,,,EXTRA\n",
            HEADER + "deposit,a,2026-01-03,50,EUR,,,,\n" * 2,
        ):
            with self.assertRaises(ValueError):
                draft(content)
        content = HEADER + 'deposit,a,2026-01-03,50,EUR,,,,"first\nsecond"\n'
        row = draft(content)["rows"][0]
        self.assertEqual(row["source"]["row"], 2)
        self.assertIn('"first\nsecond"', row["source"]["quote"])

    def test_ai_quotes_must_exist_and_financial_values_need_source_evidence(self):
        extracted = pdf_result()
        pages = [extracted["rows"][0]["quote"]]
        document = ai_document_draft(
            extracted,
            pages=pages,
            content=b"synthetic",
            filename="synthetic.pdf",
            source_id="Brokerdepot",
        )
        before = wallet([make_contribution(100, "2026-01-01")])
        candidate, _ = prepare_document(document, before, today=TODAY)
        self.assertEqual(all_lots(candidate)[0][c.LOT_UNITS], 5)
        for changes in ({"quote": "fabricated"}, {"page": 2}, {"id": "invented-id"}):
            with self.assertRaisesRegex(ValueError, "document_source_not_found"):
                ai_document_draft(
                    pdf_result(**changes),
                    pages=pages,
                    content=b"synthetic",
                    filename="synthetic.pdf",
                    source_id="Brokerdepot",
                )
        hallucinated = ai_document_draft(
            pdf_result(amount="99"),
            pages=pages,
            content=b"synthetic",
            filename="synthetic.pdf",
            source_id="Brokerdepot",
        )
        candidate, preview = prepare_document(hallucinated, before, today=TODAY)
        self.assertIsNone(candidate)
        self.assertIn("amount: value_not_in_source", preview["rows"][0]["issues"])

    def test_incomplete_ai_extraction_never_partially_imports(self):
        extracted = pdf_result()
        extracted["complete"] = False
        extracted["warnings"] = ["Unsupported sale on page 2"]
        document = ai_document_draft(
            extracted,
            pages=[extracted["rows"][0]["quote"]],
            content=b"synthetic",
            filename="synthetic.pdf",
            source_id="Brokerdepot",
        )
        candidate, preview = prepare_document(document, wallet(), today=TODAY)
        self.assertIsNone(candidate)
        self.assertIn("incomplete_extraction", preview["issues"])

    def test_actual_pdf_parser_extracts_text_and_rejects_scans_and_encryption(self):
        try:
            from pypdf import PdfWriter
            from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        except ImportError:
            self.skipTest("PDF dependency unavailable")
        writer = PdfWriter()
        page = writer.add_blank_page(width=600, height=800)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 50 750 Td (Synthetic EUR 50) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
        buffer = io.BytesIO()
        writer.write(buffer)
        self.assertIn("Synthetic EUR 50", extract_pdf_pages(buffer.getvalue())[0])
        writer.add_blank_page(width=600, height=800)
        buffer = io.BytesIO()
        writer.write(buffer)
        with self.assertRaisesRegex(ValueError, "document_ocr_required"):
            extract_pdf_pages(buffer.getvalue())
        writer.encrypt("synthetic-password")
        buffer = io.BytesIO()
        writer.write(buffer)
        with self.assertRaisesRegex(ValueError, "encrypted_document_pdf"):
            extract_pdf_pages(buffer.getvalue())


class DocumentBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entry = SimpleNamespace(entry_id="wallet-a", title="Wallet", data=wallet())
        self.hass = hass_with([self.entry])
        self.hass.async_add_executor_job = AsyncMock(return_value=["text"])
        self.connection = Connection()

    async def prepare(self, **kwargs):
        await _prepare_document(
            self.hass,
            self.connection,
            {
                "id": 1,
                "entry_id": "wallet-a",
                "source_id": "Brokerdepot",
                "format": "csv",
                "filename": "synthetic.csv",
                "content": CSV,
                **kwargs,
            },
        )
        self.assertEqual(self.connection.errors, [])
        return self.connection.results[-1][1]

    async def test_all_endpoints_are_admin_only_before_state_or_provider_access(self):
        for handler in (
            _prepare_document,
            _review_document,
            _commit_document,
        ):
            connection = Connection(admin=False)
            result = handler(self.hass, connection, {"id": 1})
            if inspect.isawaitable(result):
                await result
            self.assertEqual(connection.errors[0][1], "unauthorized")
        self.assertEqual(self.hass.data, {})

    async def test_commit_requires_confirmation_user_target_snapshot_and_single_use(
        self,
    ):
        prepared = await self.prepare()
        token = prepared["token"]
        self.assertIsNotNone(token)
        self.hass.config_entries.async_update_entry.assert_not_called()
        for connection, fields, error in (
            (Connection(), {"confirm": False}, "confirmation_required"),
            (Connection(user_id="other"), {}, "document_expired"),
            (Connection(), {"entry_id": "other"}, "entry_changed"),
        ):
            _commit_document(
                self.hass,
                connection,
                {
                    "id": 2,
                    "entry_id": "wallet-a",
                    "token": token,
                    "confirm": True,
                    **fields,
                },
            )
            self.assertEqual(connection.errors[-1][1], error)
        _commit_document(
            self.hass,
            self.connection,
            {"id": 2, "entry_id": "wallet-a", "token": token, "confirm": True},
        )
        self.hass.config_entries.async_update_entry.assert_called_once()
        _commit_document(
            self.hass,
            self.connection,
            {"id": 3, "entry_id": "wallet-a", "token": token, "confirm": True},
        )
        self.assertEqual(self.connection.errors[-1][1], "document_expired")

    async def test_changed_wallet_and_expired_draft_require_new_preview(self):
        prepared = await self.prepare()
        self.entry.data = deepcopy(self.entry.data)
        _commit_document(
            self.hass,
            self.connection,
            {
                "id": 2,
                "entry_id": "wallet-a",
                "token": prepared["token"],
                "confirm": True,
            },
        )
        self.assertEqual(self.connection.errors[-1][1], "entry_changed")
        self.connection = Connection()
        prepared = await self.prepare()
        document_api._state(self.hass)["drafts"][prepared["draft_id"]]["expires"] = 0
        _review_document(
            self.hass,
            self.connection,
            {"id": 3, "entry_id": "wallet-a", "draft_id": prepared["draft_id"]},
        )
        self.assertEqual(self.connection.errors[-1][1], "document_expired")
        self.hass.config_entries.async_update_entry.assert_not_called()

    async def test_correction_invalidates_old_preview_and_does_not_rerun_provider(self):
        prepared = await self.prepare()
        with patch.object(
            document_api, "_extract_with_ai", new=AsyncMock()
        ) as provider:
            _review_document(
                self.hass,
                self.connection,
                {
                    "id": 2,
                    "entry_id": "wallet-a",
                    "draft_id": prepared["draft_id"],
                    "corrections": {"row-2": {"units": "4"}},
                },
            )
            reviewed = self.connection.results[-1][1]
            provider.assert_not_awaited()
        self.assertNotEqual(reviewed["token"], prepared["token"])
        _commit_document(
            self.hass,
            self.connection,
            {
                "id": 3,
                "entry_id": "wallet-a",
                "token": prepared["token"],
                "confirm": True,
            },
        )
        self.assertEqual(self.connection.errors[-1][1], "document_expired")

    async def test_pdf_provider_requires_explicit_consent_and_selected_entity(self):
        with patch.object(
            document_api, "_extract_with_ai", new=AsyncMock()
        ) as provider:
            for fields, error in (
                ({}, "document_ai_consent_required"),
                ({"allow_external": True}, "document_ai_task_required"),
            ):
                connection = Connection()
                await _prepare_document(
                    self.hass,
                    connection,
                    {
                        "id": 1,
                        "entry_id": "wallet-a",
                        "source_id": "Brokerdepot",
                        "format": "pdf",
                        "filename": "synthetic.pdf",
                        "content": base64.b64encode(b"%PDF-synthetic").decode(),
                        **fields,
                    },
                )
                self.assertEqual(connection.errors[-1][1], error)
            provider.assert_not_awaited()
            self.hass.async_add_executor_job.assert_not_awaited()

    async def test_pdf_result_is_reviewable_and_raw_content_is_not_persisted(self):
        extracted = pdf_result()
        self.entry.data = wallet([make_contribution(100, "2026-01-01")])
        self.hass.async_add_executor_job = AsyncMock(
            return_value=[extracted["rows"][0]["quote"]]
        )
        with patch.object(
            document_api, "_extract_with_ai", new=AsyncMock(return_value=extracted)
        ) as provider:
            prepared = await self.prepare(
                format="pdf",
                filename="synthetic.pdf",
                content=base64.b64encode(b"%PDF-synthetic").decode(),
                allow_external=True,
                ai_task_entity_id="ai_task.selected",
            )
            self.assertTrue(prepared["requires_ai_review"])
            self.assertIsNotNone(prepared["token"])
            self.assertEqual(
                provider.await_args.kwargs["entity_id"], "ai_task.selected"
            )
        _commit_document(
            self.hass,
            self.connection,
            {
                "id": 2,
                "entry_id": "wallet-a",
                "token": prepared["token"],
                "confirm": True,
            },
        )
        saved = self.hass.config_entries.async_update_entry.call_args.kwargs["data"]
        self.assertNotIn("%PDF-synthetic", str(saved))
        self.assertEqual(saved[IMPORT_RECORDS][0]["sources"][0]["source"]["page"], 1)


if __name__ == "__main__":
    unittest.main()
