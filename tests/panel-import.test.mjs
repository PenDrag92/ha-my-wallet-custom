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
