"""Recorder scope, missing data, legacy accounting and immutable snapshots."""

from __future__ import annotations

import copy
import sys
import unittest
from datetime import UTC, date, datetime, timedelta
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from custom_components.my_wallet import const as c
from custom_components.my_wallet import recorded_history as history
from custom_components.my_wallet.contributions import make_contribution
from custom_components.my_wallet.corrections import prepare_correction
from custom_components.my_wallet.yahoo import Quote
from tests.test_panel_regressions import Connection, hass_with, panel
from tests.test_v190_planning import WalletCoordinator, wallet

START = datetime(2026, 9, 2, 10, tzinfo=UTC)
END = START + timedelta(hours=1)


def record(when, value=100, *, capital=100, income=0, currency="EUR", legacy=False):
    attrs = {"unit_of_measurement": currency, c.ATTR_CASH_BALANCE: 0}
    if not legacy:
        attrs[history.SNAPSHOT_ATTRIBUTE] = {
            "capital": capital,
            "income": income,
            "revision": "basis-a",
            "sampled_at": when.isoformat(),
        }
    return {"time": when, "state": str(value), "attributes": attrs}


class RecordedHistoryTests(unittest.TestCase):
    def setUp(self):
        self.local = patch.object(
            history.dt_util, "as_local", lambda when: when, create=True
        )
        self.local.start()
        self.addCleanup(self.local.stop)

    def build(self, records, auxiliary=(), **kwargs):
        live = kwargs.pop("live", {**records[-1], "reported": END} if records else None)
        return history.build_recorded_history(
            records,
            auxiliary,
            start=START,
            end=END,
            currency="EUR",
            live=live,
            **kwargs,
        )

    def test_real_snapshots_preserve_flows_and_do_not_mutate_the_recorder_input(self):
        records = [record(START), record(END - timedelta(minutes=1), 205, capital=200)]
        original = copy.deepcopy(records)
        result = self.build(records)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["points"][-1]["value"], 205)
        self.assertEqual(result["points"][-1]["invested"], 200)
        self.assertTrue(result["points"][-1]["boundary"])
        self.assertEqual(result["last_recorded_at"], records[-1]["time"].isoformat())
        self.assertEqual(records, original)

    def test_an_unavailable_sample_stays_a_gap_not_a_zero_price(self):
        result = self.build(
            [
                record(START),
                record(START + timedelta(minutes=20), "unavailable"),
                record(END - timedelta(minutes=1), 105),
            ]
        )
        self.assertIsNone(result["points"][1]["value"])
        self.assertTrue(result["has_gaps"])

    def test_missing_start_and_stale_tail_are_not_filled_with_current_prices(self):
        rows = [
            record(START + timedelta(minutes=15)),
            record(START + timedelta(minutes=20), 102),
        ]
        result = self.build(rows, live=None, interval=5)
        self.assertTrue(result["partial"])
        self.assertEqual(result["status"], "stale")
        self.assertIsNone(result["points"][0]["value"])
        self.assertIsNone(result["points"][-1]["value"])
        self.assertEqual(
            self.build([], live={**record(END), "reported": END})["status"],
            "no_history",
        )

    def test_missed_heartbeat_creates_a_gap_but_unchanged_legacy_values_do_not(self):
        new = self.build(
            [record(START), record(END - timedelta(minutes=1))], interval=5
        )
        self.assertTrue(new["has_gaps"])
        old = self.build(
            [
                record(START, legacy=True),
                record(END - timedelta(minutes=1), legacy=True),
            ],
            interval=5,
        )
        self.assertFalse(old["has_gaps"])

    def test_old_accounting_is_accepted_only_when_the_valuation_matches(self):
        rows = [record(START, legacy=True), record(END, 110, legacy=True)]
        aux = [record(START), record(END)]
        for row, value in zip(aux, (100, 110), strict=True):
            row["attributes"].update(
                {c.ATTR_TOTAL: value, c.ATTR_INVESTED: 100, c.ATTR_DIVIDEND_TOTAL: 0}
            )
        result = self.build(rows, aux)
        self.assertEqual([p["invested"] for p in result["points"]], [100, 100])
        aux[-1]["attributes"][c.ATTR_TOTAL] = 120
        self.assertIsNone(self.build(rows, aux)["points"][-1]["invested"])

    def test_partial_position_lots_do_not_supply_a_false_complete_cost_basis(self):
        rows = [record(START, legacy=True), record(END, 110, legacy=True)]
        for row in rows:
            row["attributes"].update({c.ATTR_AMOUNT: 10, c.ATTR_DIVIDEND_TOTAL: 0})
        auxiliary = []
        for row in rows:
            auxiliary.append(
                {
                    **record(row["time"]),
                    "attributes": {
                        "unit_of_measurement": "EUR",
                        c.ATTR_TRACKED_VALUE: float(row["state"]),
                        c.ATTR_TRACKED_INVESTED: 100,
                        c.ATTR_LOTS: [{c.LOT_UNITS: 9}],
                    },
                }
            )
        result = self.build(rows, auxiliary, symbol="AAA")
        self.assertTrue(all(p["invested"] is None for p in result["points"]))
        for row in auxiliary:
            row["attributes"][c.ATTR_LOTS][0][c.LOT_UNITS] = 10
        self.assertEqual(
            self.build(rows, auxiliary, symbol="AAA")["points"][-1]["invested"], 100
        )
        rows[-1]["attributes"][c.ATTR_AMOUNT] = 10.0000004
        self.assertEqual(
            self.build(rows, auxiliary, symbol="AAA")["points"][-1]["invested"], 100
        )

    def test_currency_changes_nonfinite_values_and_future_records_are_not_charted(self):
        for value, currency in (
            (100, "USD"),
            ("nan", "EUR"),
            ("inf", "EUR"),
            (-1, "EUR"),
        ):
            result = self.build([record(START), record(END, value, currency=currency)])
            self.assertIsNone(result["points"][-1]["value"])
        result = self.build(
            [record(START), record(END), record(END + timedelta(hours=1), 999)]
        )
        self.assertFalse(any(p.get("value") == 999 for p in result["points"]))

    def test_legacy_corrections_are_flagged_without_rewriting_recordings(self):
        result = self.build(
            [record(START, legacy=True), record(END, legacy=True)],
            corrections=[{"recorded_date": "2026-09-02", "symbol": "AAA"}],
        )
        self.assertTrue(result["accounting_changed"])

    def test_stale_start_snapshot_is_not_relabelled_as_a_fresh_opening_value(self):
        first = record(START)
        first["attributes"][history.SNAPSHOT_ATTRIBUTE]["sampled_at"] = (
            START - timedelta(hours=4)
        ).isoformat()
        result = self.build([first, record(END)])
        self.assertIsNone(result["points"][0]["value"])
        self.assertTrue(result["has_gaps"])

    def test_wrong_currency_also_excludes_cash_and_the_cost_basis(self):
        result = self.build([record(START), record(END, currency="USD")])
        for key in ("value", "cash", "invested", "dividends", "real_cash"):
            self.assertIsNone(result["points"][-1][key], key)

    def test_malformed_legacy_lots_leave_the_basis_unknown(self):
        row = record(START, legacy=True)
        row["attributes"][c.ATTR_AMOUNT] = 10
        auxiliary = record(START)
        auxiliary["attributes"].update(
            {
                c.ATTR_TRACKED_VALUE: 100,
                c.ATTR_TRACKED_INVESTED: 100,
                c.ATTR_LOTS: ["invalid"],
            }
        )
        self.assertIsNone(
            self.build([row], [auxiliary], symbol="AAA")["points"][0]["invested"]
        )

    def test_snapshot_revision_ignores_new_deposits_but_tracks_unit_corrections(self):
        data = wallet()
        before = history.accounting_snapshot(data, today=date(2026, 9, 2), symbol="AAA")
        data[c.CONF_CONTRIBUTIONS].append(make_contribution(50, "2026-09-02"))
        unchanged = history.accounting_snapshot(
            data, today=date(2026, 9, 2), symbol="AAA"
        )
        self.assertEqual(before["revision"], unchanged["revision"])
        choice = data[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS][0]
        corrected, _ = prepare_correction(
            data,
            {
                "symbol": "AAA",
                "mode": "lot",
                "target": choice[c.LOT_ID],
                "units": 11,
                "note": "",
            },
            today=date(2026, 9, 2),
        )
        after = history.accounting_snapshot(
            corrected, today=date(2026, 9, 2), symbol="AAA"
        )
        self.assertNotEqual(before["revision"], after["revision"])
        self.assertEqual(before["capital"], after["capital"])
        self.assertEqual(
            history.accounting_snapshot(data, today=date(2026, 9, 2))["capital"], 150
        )


class RecordedSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_later_ledger_edits_cannot_change_a_cached_valuation_basis(self):
        entry = SimpleNamespace(entry_id="wallet", title="Wallet", data=wallet())
        coordinator = WalletCoordinator(SimpleNamespace(session=object()), entry)
        coordinator._inflation.async_get = AsyncMock(return_value=None)
        coordinator._async_book_due_plans = AsyncMock(return_value=[])
        with patch.dict(
            WalletCoordinator._async_update_data.__globals__,
            {
                "fetch_quotes": AsyncMock(
                    return_value={
                        "AAA": Quote("AAA", 10, "EUR"),
                        "BBB": Quote("BBB", 10, "EUR"),
                    }
                )
            },
        ):
            computed = await coordinator._async_update_data()
        original = copy.deepcopy(computed.history_snapshots)
        self.assertEqual(original[None]["capital"], 100)
        self.assertEqual(original["AAA"]["capital"], 100)
        self.assertEqual(original[None]["sampled_at"], computed.sampled_at)
        entry.data[c.CONF_CONTRIBUTIONS].append(make_contribution(50, "2026-08-31"))
        self.assertEqual(computed.history_snapshots, original)
        self.assertEqual(computed.total, 100)


class RecordedEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_or_starting_recorder_does_not_break_other_views(self):
        entry = SimpleNamespace(entry_id="wallet", data=wallet(), runtime_data=None)
        with patch.object(history, "_recorder_instance", side_effect=KeyError):
            result = await history.async_recorded_history(
                hass_with([entry]), entry, period="day"
            )
        self.assertEqual(result["status"], "recorder_missing")
        with patch.object(
            history,
            "_recorder_instance",
            return_value=SimpleNamespace(is_running=False),
        ):
            result = await history.async_recorded_history(
                hass_with([entry]), entry, period="week"
            )
        self.assertEqual(result["status"], "recorder_unavailable")

    async def test_unknown_wallet_symbol_or_period_never_reads_the_database(self):
        entry = SimpleNamespace(entry_id="wallet", data=wallet(), runtime_data=None)
        with patch.object(
            panel, "async_recorded_history", new_callable=AsyncMock
        ) as read:
            for request in (
                {"entry_id": "someone-else", "period": "day"},
                {"entry_id": "wallet", "period": "month"},
                {"entry_id": "wallet", "period": "day", "symbol": "PRIVATE"},
            ):
                connection = Connection()
                await panel.ws_recorded_history(
                    hass_with([entry]), connection, {"id": 1, **request}
                )
                self.assertTrue(connection.errors)
            read.assert_not_awaited()

    async def test_cache_is_scoped_to_selection_and_invalidated_by_config_changes(self):
        entry = SimpleNamespace(entry_id="wallet", data=wallet(), runtime_data=None)
        hass = hass_with([entry])
        result = {"status": "no_history", "points": []}
        with patch.object(
            panel, "async_recorded_history", new_callable=AsyncMock, return_value=result
        ) as read:
            request = {"id": 1, "entry_id": "wallet", "period": "day"}
            await panel.ws_recorded_history(hass, Connection(), request)
            await panel.ws_recorded_history(hass, Connection(), request)
            self.assertEqual(read.await_count, 1)
            await panel.ws_recorded_history(
                hass, Connection(), {**request, "symbol": "AAA"}
            )
            self.assertEqual(read.await_count, 2)
            entry.data = copy.deepcopy(entry.data)
            await panel.ws_recorded_history(
                hass, Connection(), {**request, "symbol": "AAA"}
            )
            self.assertEqual(read.await_count, 3)

    async def test_config_change_during_read_does_not_return_a_stale_result(self):
        entry = SimpleNamespace(entry_id="wallet", data=wallet(), runtime_data=None)

        async def change(*args, **kwargs):
            entry.data = copy.deepcopy(entry.data)
            return {"points": []}

        connection = Connection()
        with patch.object(panel, "async_recorded_history", side_effect=change):
            await panel.ws_recorded_history(
                hass_with([entry]),
                connection,
                {"id": 1, "entry_id": "wallet", "period": "day"},
            )
        self.assertEqual(connection.errors[0][1], "entry_changed")
        self.assertEqual(connection.results, [])

    async def test_disabled_or_excluded_recorder_returns_an_explanation_without_query(
        self,
    ):
        entry = SimpleNamespace(entry_id="wallet", data=wallet(), runtime_data=None)
        recorder = SimpleNamespace(
            is_running=True,
            async_db_ready=SimpleNamespace(done=lambda: True),
            entity_filter=lambda entity: False,
            async_add_executor_job=AsyncMock(),
        )
        with (
            patch.object(history, "_recorder_instance", return_value=recorder),
            patch.object(
                history,
                "_history_entities",
                return_value=("sensor.renamed", None, None),
            ),
        ):
            result = await history.async_recorded_history(
                hass_with([entry]), entry, period="day"
            )
        self.assertEqual(result["status"], "entity_excluded")
        recorder.async_add_executor_job.assert_not_awaited()

    def test_sensor_lookup_uses_unique_ids_and_rejects_other_config_entries(self):
        registry = SimpleNamespace(
            async_get_entity_id=Mock(side_effect=["sensor.renamed", "sensor.profit"]),
            async_get=Mock(
                side_effect=[SimpleNamespace(config_entry_id="other", disabled_by=None)]
            ),
        )
        module = ModuleType("homeassistant.helpers.entity_registry")
        module.async_get = lambda hass: registry
        with patch.dict(sys.modules, {module.__name__: module}):
            result = history._history_entities(
                SimpleNamespace(), SimpleNamespace(entry_id="wallet"), "AAA"
            )
        self.assertEqual(result[2], "entity_missing")
        registry.async_get_entity_id.assert_any_call(
            "sensor", "my_wallet", "wallet_AAA"
        )
