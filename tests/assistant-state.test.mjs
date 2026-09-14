import assert from "node:assert/strict";
import test from "node:test";
import { AssistantState, inputNumber } from "../custom_components/my_wallet/frontend/assistant-state.mjs";

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

test("switching user or wallet discards a pending document and its errors", async () => {
  const state = new AssistantState(); state.reset("admin:wallet-a");
  const pending = deferred(), old = state.run("document", () => pending.promise);
  state.reset("admin:wallet-b");
  pending.resolve({ token: "wallet-a-write-token" });
  assert.equal(await old, null);
  assert.equal(state.results.document, undefined);
  assert.equal(state.pending.size, 0);
  const failure = deferred(), request = state.run("report", () => failure.promise);
  state.reset("other-user:wallet-b"); failure.reject(new Error("private wallet name"));
  await request; assert.deepEqual(state.errors, {});
});

test("a newer report owns the result and pending indicator", async () => {
  const state = new AssistantState(), first = deferred(), last = deferred();
  const a = state.run("report", () => first.promise), b = state.run("report", () => last.promise);
  first.resolve({ value: 999 }); await a;
  assert.equal(state.results.report, undefined); assert.ok(state.pending.has("report"));
  last.resolve({ value: 12 }); await b;
  assert.deepEqual(state.results.report, { value: 12 }); assert.equal(state.pending.size, 0);
});

test("changing a document or agent revokes an outstanding response", async () => {
  const state = new AssistantState(), pending = deferred();
  const request = state.run("ask", () => pending.promise);
  state.invalidate("ask"); pending.resolve({ text: "old agent", session_id: "old" });
  assert.equal(await request, null); assert.equal(state.results.ask, undefined);
});

test("independent calculations preserve one another's progress", async () => {
  const state = new AssistantState(), report = deferred(), scenario = deferred();
  const a = state.run("report", () => report.promise), b = state.run("scenario", () => scenario.promise);
  report.resolve({}); await a; assert.ok(state.pending.has("scenario"));
  scenario.resolve({}); await b; assert.equal(state.pending.size, 0);
});

test("decimal input accepts either locale while rejecting ambiguity and missing required amounts", () => {
  assert.equal(inputNumber("1,25"), 1.25); assert.equal(inputNumber(" -3.5 "), -3.5);
  assert.equal(inputNumber("", { optional: true }), undefined);
  for (const value of ["", "1.000,50", "1,000.50", "Infinity", "1e5", "0x10", "1 000", "NaN"]) assert.throws(() => inputNumber(value));
});
