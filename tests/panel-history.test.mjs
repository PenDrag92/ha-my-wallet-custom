import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";
import { historyGapIds, periodMetrics } from "../custom_components/my_wallet/frontend/history-series.mjs";

// Minimal text-only DOM: user-controlled plan names and aliases must never be HTML.
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.textContent = ""; this.className = ""; }
  append(...children) {
    for (const child of children) { child.parentElement = this; this.children.push(child); }
  }
  replaceWith(replacement) {
    const parent = this.parentElement;
    parent.children[parent.children.indexOf(this)] = replacement;
    replacement.parentElement = parent;
    this.parentElement = null;
  }
  remove() { this.parentElement.children.splice(this.parentElement.children.indexOf(this), 1); }
  addEventListener(name, callback) { this[name] = callback; }
  focus() {}
  setAttribute() {}
  set innerHTML(_value) { assert.fail("Dynamic history notices must use text nodes"); }
  get text() { return [this.textContent, ...this.children.map(child => child.text)].join(" "); }
}
let Panel;
const storage = new Map();
const source = fs.readFileSync(new URL("../custom_components/my_wallet/frontend/my-wallet-panel.js", import.meta.url), "utf8");
vm.runInNewContext(source.replace(/^import .*;$/gm, ""), {
  HTMLElement: class { attachShadow() {} }, document: { createElement: tag => new Element(tag), createTextNode: text => ({ text }) },
  customElements: { get() {}, define(_name, component) { Panel = component; } },
  localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
  Intl, periodMetrics, historyGapIds,
});
function fixture(lang = "de") {
  const panel = new Panel();
  panel._lang = lang; panel._selected = "demo";
  panel._hass = { config: { time_zone: "Europe/Berlin" } };
  panel._wallets = [{ entry_id: "demo", currency: "EUR", positions: [{ symbol: "AAA", alias: "World ETF <example>" }],
    plans: [{ id: "plan", name: "Monthly <example>" }] }];
  return panel;
}

test("changing history sources refreshes the data even with a cached view", async () => {
  const panel = fixture();
  const calls = [];
  panel._section = "history";
  panel._period = "month";
  panel._history = { points: [{ date: "2026-11-21" }] };
  panel._render = () => {};
  panel._call = async (type, args) => {
    calls.push([type, args?.period]);
    if (type === "wallets") return { wallets: panel._wallets };
    if (type === "history") return { points: [{ date: "2026-11-22" }] };
    return { period: args.period };
  };

  await panel._setPeriod("day");
  await panel._setPeriod("month");
  assert.equal(panel._history.points[0].date, "2026-11-22");
  await panel._setPeriod("day");
  await panel._setPeriod("day");
  await panel._setPeriod("week");
  await panel._setPeriod("all");
  assert.deepEqual(calls, [
    ["recorded_history", "day"], ["wallets", undefined], ["history", undefined],
    ["recorded_history", "day"], ["recorded_history", "week"], ["wallets", undefined], ["history", undefined],
  ]);
});

test("acknowledged gaps stay collapsed after reload but a new gap is shown", () => {
  storage.clear();
  const panel = fixture(), root = new Element("section");
  panel._period = "week";
  const points = [
    { timestamp: "2026-11-20T10:00:00Z", value: 10 },
    { timestamp: "2026-11-20T10:30:00Z", value: null },
    { timestamp: "2026-11-20T11:00:00Z", value: 11 },
  ];
  const recording = { status: "ok", points, has_gaps: true };
  panel._recordedWarnings(root, recording, "all");
  root.children[0].children[0].click();
  assert.equal(root.children[0].tag, "details");
  assert.match(root.text, /Ausgeblendeten Hinweis anzeigen/);
  const reloaded = fixture(), same = new Element("section");
  reloaded._period = "week";
  reloaded._recordedWarnings(same, recording, "all");
  assert.equal(same.children[0].tag, "details");
  const fresh = new Element("section");
  reloaded._recordedWarnings(fresh, { ...recording, points: [...points,
    { timestamp: "2026-11-20T12:00:00Z", value: null },
    { timestamp: "2026-11-20T12:30:00Z", value: 12 },
  ] }, "all");
  assert.equal(fresh.children[0].tag, "div");
  assert.match(fresh.text, /Zur Kenntnis genommen/);
  const other = new Element("section");
  reloaded._selected = "another-wallet";
  reloaded._recordedWarnings(other, recording, "all");
  assert.equal(other.children[0].tag, "div");
});

test("collapsed accounting notice leaves the gain and its scope visible", () => {
  storage.clear();
  const panel = fixture(), root = new Element("section");
  const points = [750.66, 750.66, 753.13, 753.13].map((value, index) => ({
    timestamp: `2026-11-22T12:${30 + index}:00Z`, value, invested: 750, dividends: 0,
    financial_revision: index < 2 ? "original" : "corrected",
  }));
  panel._renderPeriodStats(root, points, {});
  const warning = root.children.find(node => node.className === "notice warning");
  warning.children.at(-1).click();
  assert.match(root.text, /vergleichbaren Abschnitte/);
  assert.match(root.text, /Gewinn \/ Verlust\s+0,00/);
  assert.match(root.text, /Wertänderung inkl\. Korrekturen\s+2,47/);
  assert.equal(root.children.find(node => node.tag === "details")?.children[1], warning);
});

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
