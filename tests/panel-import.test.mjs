import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";

const source = fs.readFileSync(new URL("../custom_components/my_wallet/frontend/my-wallet-panel.js", import.meta.url), "utf8");
let Panel;
vm.runInNewContext(source.replace(/^import .*;$/gm, ""), {
  HTMLElement: class { attachShadow() { return {}; } },
  customElements: { get() { return undefined; }, define(_name, component) { Panel = component; } },
  localStorage: { getItem() { return null; }, setItem() {} },
  Intl,
});

function fixture() {
  const panel = new Panel();
  Object.assign(panel, {
    _selected: "A", _importMode: "followup", _importOpen: true,
    _preview: { token: "token-A", entry_id: "A", target_name: "Depot A" },
    _document: { batch_id: "statement" }, _importDecisions: { deposit: "merge" },
    _hass: { user: { id: "admin" } }, _lang: "en",
  });
  panel._render = () => {};
  panel._refresh = async () => {};
  return panel;
}

test("switching wallets discards the former import and its decisions before confirmation", async () => {
  const panel = fixture();
  const calls = [];
  panel._call = async (...args) => { calls.push(args); return {}; };
  panel._selectWallet("B");
  await panel._commitImport();
  assert.equal(panel._selected, "B");
  assert.equal(panel._preview, null);
  assert.equal(panel._document, null);
  assert.equal(Object.keys(panel._importDecisions).length, 0);
  assert.equal(calls.length, 0);
});

test("a stale target is refused even when the selector reset was bypassed", async () => {
  const panel = fixture();
  panel._selected = "B";
  panel._call = async () => assert.fail("A stale preview must not be sent");
  await panel._commitImport();
  assert.equal(panel._preview, null);
  assert.ok(panel._error);
});

test("confirmation sends the same target that was previewed", async () => {
  const panel = fixture();
  const calls = [];
  panel._call = async (type, args) => { calls.push([type, args]); return { entry_id: "A" }; };
  await panel._commitImport();
  assert.equal(calls[0][0], "import_commit");
  assert.equal(calls[0][1].entry_id, "A");
  assert.equal(calls[0][1].token, "token-A");
  assert.equal(calls[0][1].confirm, true);
  assert.equal(panel._preview, null);
});

test("refresh invalidates an import when its wallet is no longer present", async () => {
  const panel = fixture();
  panel._section = "planning";
  panel._call = async type => type === "wallets" ? { wallets: [{ entry_id: "B", inflation: {} }] } : {};
  await Panel.prototype._refresh.call(panel);
  assert.equal(panel._selected, "B");
  assert.equal(panel._preview, null);
  assert.equal(panel._document, null);
});

function historyFixture() {
  const panel = fixture();
  panel._section = "history"; panel._period = "day"; panel._position = "all";
  return panel;
}

test("component requests are deduplicated and stale total responses cannot replace them", async () => {
  const panel = historyFixture(), calls = [], pending = [];
  panel._call = async (type, data) => {
    calls.push([type, data]); return new Promise(resolve => pending.push(resolve));
  };
  const total = panel._loadRecorded();
  panel._historyView = "components";
  const split = panel._loadRecorded();
  await panel._loadRecorded();
  assert.equal(calls.length, 2);
  assert.equal(calls[1][1].components, true); assert.equal(calls[1][1].symbol, undefined);
  pending[1]({ positions: { AAA: { points: [] } } }); await split;
  pending[0]({ points: [{ value: 999 }] }); await total;
  assert.ok(panel._recordedHistory.positions.AAA);
  assert.equal(panel._recordedHistory.points, undefined);
  await panel._loadRecorded(); assert.equal(calls.length, 2);
});

test("wallet and period switches reject pending component results, including old failures", async () => {
  const panel = historyFixture(), pending = [];
  panel._historyView = "components";
  panel._call = (_type, data) => new Promise((resolve, reject) => pending.push({ data, resolve, reject }));
  const old = panel._loadRecorded();
  panel._selectWallet("B"); panel._period = "week";
  const current = panel._loadRecorded();
  pending[0].reject(new Error("old wallet unavailable")); await old;
  pending[1].resolve({ positions: { BBB: { points: [] } } }); await current;
  assert.equal(pending[1].data.entry_id, "B"); assert.equal(pending[1].data.period, "week");
  assert.equal(panel._recordedError, null); assert.ok(panel._recordedHistory.positions.BBB);
});

test("single-position selection uses its own recorder scope after the split view", async () => {
  const panel = historyFixture(), calls = [];
  panel._historyView = "components"; panel._position = "BBB";
  panel._call = async (_type, data) => { calls.push(data); return { points: [] }; };
  await panel._loadRecorded();
  assert.equal(calls[0].symbol, "BBB"); assert.equal(calls[0].components, undefined);
  assert.equal(panel._splitHistory(), false);
});
