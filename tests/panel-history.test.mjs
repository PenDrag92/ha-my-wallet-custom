import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";
import { periodMetrics } from "../custom_components/my_wallet/frontend/history-series.mjs";

// Minimal text-only DOM: user-controlled plan names and aliases must never be HTML.
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.textContent = ""; this.className = ""; }
  append(...children) { this.children.push(...children); }
  setAttribute() {}
  set innerHTML(_value) { assert.fail("Dynamic history notices must use text nodes"); }
  get text() { return [this.textContent, ...this.children.map(child => child.text)].join(" "); }
}
let Panel;
const source = fs.readFileSync(new URL("../custom_components/my_wallet/frontend/my-wallet-panel.js", import.meta.url), "utf8");
vm.runInNewContext(source.replace(/^import .*;$/gm, ""), {
  HTMLElement: class { attachShadow() {} }, document: { createElement: tag => new Element(tag), createTextNode: text => ({ text }) },
  customElements: { get() {}, define(_name, component) { Panel = component; } },
  localStorage: { getItem() { return null; } }, Intl, periodMetrics,
});
function fixture(lang = "de") {
  const panel = new Panel();
  panel._lang = lang; panel._selected = "demo";
  panel._hass = { config: { time_zone: "Europe/Berlin" } };
  panel._wallets = [{ entry_id: "demo", currency: "EUR", positions: [{ symbol: "AAA", alias: "World ETF <example>" }],
    plans: [{ id: "plan", name: "Monthly <example>" }] }];
  return panel;
}

test("pending quotes show reason, date and alias without a repair warning", () => {
  const panel = fixture(), root = new Element("main"), wallet = panel._wallet();
  wallet.pending = [{ plan_id: "plan", scheduled_date: "2026-09-21", reason: "historical_price_unavailable", repair_required: false, missing_symbols: ["AAA"] }];
  panel._renderPending(root, wallet);
  assert.match(root.text, /Monthly <example>.*21\.09\.2026.*Wartet auf Daten/);
  assert.match(root.text, /World ETF <example> \(AAA\)/);
  assert.match(root.text, /Schlusskurse/); assert.match(root.text, /keine manuelle Korrektur/);
  assert.equal(root.children[0].children[1].className, "notice");
});

test("repair and unknown reasons never promise automatic recovery", () => {
  for (const reason of ["opening_balance_conflict", "included_units_exceeded", "allocation_too_small", "cash_conflict", "unconfigured_symbol", "new_reason", "constructor"]) {
    const panel = fixture("en"), root = new Element("main"), wallet = panel._wallet();
    wallet.pending = [{ plan_name: "Review plan", reason, repair_required: true, affected_symbols: ["AAA"] }];
    panel._renderPending(root, wallet);
    assert.match(root.text, /Review required/); assert.match(root.text, /Next Savings Plan Execution/);
    assert.match(root.text, /World ETF <example> \(AAA\)/);
    assert.doesNotMatch(root.text, /No manual correction|pending_|function Object/);
    assert.equal(root.children[0].children[1].className, "notice warning");
  }
});

test("mixed pending states keep their own severity and cover retryable FX and config races", () => {
  const panel = fixture("en"), root = new Element("main"), wallet = panel._wallet();
  wallet.pending = ["historical_fx_unavailable", "entry_changed", "historical_price_unavailable"].map((reason, i) => ({
    reason, scheduled_date: "2026-09-21", repair_required: i === 2,
  }));
  panel._renderPending(root, wallet);
  assert.deepEqual(root.children[0].children.slice(1).map(node => node.className), ["notice", "notice", "notice warning"]);
  assert.match(root.text, /exchange rates/); assert.match(root.text, /changed during calculation/);
});

test("shortened component stats show actual dates and mark approximate returns next to their value", () => {
  const panel = fixture(), root = new Element("section");
  const points = [
    { date: "2026-09-01", value: null, invested: 0, dividends: 0 },
    { date: "2026-09-02", value: 100, invested: 100, dividends: 0 },
    { date: "2026-09-03", value: null, invested: 150, dividends: 0 },
    { date: "2026-09-04", value: 160, invested: 150, dividends: 0 },
    { date: "2026-09-05", value: null, invested: 200, dividends: 0 },
  ];
  panel._renderPeriodStats(root, points, null, { compact: true, position: true });
  assert.match(root.text, /Zeitraum verkürzt.*02\.09\.2026.*04\.09\.2026/);
  assert.match(root.text, /Rendite im Zeitraum \(Näherung\)/);
  assert.match(root.text, /Ende des unbeobachteten Intervalls/);
  assert.doesNotMatch(root.text, /01\.09\.2026|05\.09\.2026|bleiben deshalb leer/);
});

test("quote-only gaps no longer produce a missing-performance warning", () => {
  const panel = fixture("en"), root = new Element("section");
  panel._renderPeriodStats(root, [{ value: 100, invested: 100 }, { value: null }, { value: 110, invested: 100 }], null, { position: false });
  assert.match(root.text, /10\.00/); assert.doesNotMatch(root.text, /approximate|unavailable|period_/);
});
