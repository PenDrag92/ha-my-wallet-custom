import assert from "node:assert/strict";
import test from "node:test";

// Small DOM contract for verifying rendered financial results and text-only output.
class Element {
  constructor(tag = "element") { this.tag = tag; this.childNodes = []; this.listeners = {}; this.attributes = {}; this.textContent = ""; }
  append(...children) { this.childNodes.push(...children); }
  replaceChildren(...children) { this.childNodes = children; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  attachShadow() { this.shadowRoot = new Element("shadow"); return this.shadowRoot; }
}
globalThis.Node = Element;
globalThis.HTMLElement = Element;
globalThis.document = { createElement: tag => new Element(tag) };
globalThis.customElements = { get: () => false, define: () => {} };
const { WalletAssistant } = await import("../custom_components/my_wallet/frontend/wallet-assistant.mjs");
function text(node) { return String(node.textContent || "") + " " + node.childNodes.map(item => item instanceof Element ? text(item) : String(item)).join(" "); }
function fixture() {
  const element = new WalletAssistant();
  element.wallet = { entry_id: "a", currency: "EUR", plans: [] }; element.lang = "de";
  element.hass = { callWS: async () => assert.fail("Rendering cannot trigger a write") };
  return element;
}

test("scenario renders authoritative final values and contribution/growth breakdown", () => {
  const view = fixture();
  view.state.results.scenario = { status: "ok", as_of: "2026-09-14", through: "2036-09-14", baseline: { final_value: 1234, future_contributions: 400, growth: 200 }, scenario: { final_value: 2345, future_contributions: 900, growth: 800 }, difference: { final_value: 1111 }, assumptions: [] };
  view.renderScenario();
  const rendered = text(view.shadowRoot);
  for (const amount of ["1.234,00", "2.345,00", "1.111,00", "400,00", "900,00"]) assert.ok(rendered.includes(amount), amount);
});

test("report distinguishes monthly gain from lifetime position profit", () => {
  const view = fixture();
  view.state.results.report = { facts: { total: 4000, profit: 800 }, positions: [{ symbol: "AAA", nominal: { value: 3000, profit: 700 }, target_share: 80 }], findings: [], period: { status: "ok", month: "2026-08", wallet: { gain: 99 }, positions: [{ symbol: "AAA", gain: 88 }] } };
  view.renderReport(); const rendered = text(view.shadowRoot);
  for (const amount of ["99,00", "88,00", "700,00", "800,00", "3.000,00"]) assert.ok(rendered.includes(amount), amount);
});

test("AI output and document quotes are rendered as text with no executable HTML", () => {
  const view = fixture(), malicious = '<img src=x onerror="steal()"> <script>steal()</script>';
  view.state.results.agents = { agents: [{ agent_id: "conversation.test", name: "Test", external: true }] };
  view.state.messages = [{ role: "assistant", text: malicious }]; view.renderChat();
  assert.ok(text(view.shadowRoot).includes(malicious));
  const tags = node => [node.tag, ...node.childNodes.filter(item => item instanceof Element).flatMap(tags)];
  assert.ok(!tags(view.shadowRoot).includes("script")); assert.ok(!tags(view.shadowRoot).includes("img"));
});

test("an incomplete or unconfirmed document preview never sends a commit", async () => {
  const view = fixture();
  view.state.results.document = { token: "review-token" }; view.confirmed = false;
  await view.commitDocument();
  view.confirmed = true; view.state.results.document = { token: null };
  await view.commitDocument();
});

test("document review displays original numeric strings and source currency", () => {
  const view = fixture();
  view.state.results.document = { draft_id: "d", token: null, rows: [{ id: "row-2", type: "purchase", date: "2026-09-01", amount: "123.45", currency: "USD", units: "1.25", symbol: "AAA", status: "invalid", issues: ["currency: wallet_currency_required"], source: { filename: "example.csv", row: 2, quote: "123.45,USD" } }], issues: [] };
  view.renderDocuments();
  assert.ok(text(view.shadowRoot).includes("123.45 USD"));
  assert.ok(text(view.shadowRoot).includes("1.25"));
  assert.ok(text(view.shadowRoot).includes("Die Währung muss mit der Depotwährung übereinstimmen."));
});

test("all document decision and correction controls are locked during review", () => {
  const view = fixture(); view.confirmed = true; view.state.pending.add("document");
  view.state.results.document = { token: "old", rows: [{ id: "row-2", type: "deposit", date: "2026-09-01", amount: "10", currency: "EUR", status: "add", issues: [], source: {} }], issues: [] };
  view.renderDocuments();
  const descendants = node => [node, ...node.childNodes.filter(item => item instanceof Element).flatMap(descendants)];
  for (const control of descendants(view.shadowRoot).filter(node => ["select", "input", "button"].includes(node.tag))) assert.equal(control.disabled, true, control.tag + " " + control.textContent);
});

test("editing a scenario input removes its old numbers without replacing the form", () => {
  const view = fixture();
  view.state.results.scenario = { status: "ok", as_of: "2026-09-14", through: "2027-09-14", baseline: { final_value: 100 }, scenario: { final_value: 200 }, difference: { final_value: 100 }, assumptions: [] };
  view.renderScenario();
  const descendants = node => [node, ...node.childNodes.filter(item => item instanceof Element).flatMap(descendants)];
  const input = descendants(view.shadowRoot).find(node => node.tag === "input");
  input.value = "5"; input.listeners.input();
  assert.equal(view.state.results.scenario, undefined);
  assert.ok(!text(view.shadowRoot).includes("200,00"));
  assert.ok(descendants(view.shadowRoot).includes(input));
});
