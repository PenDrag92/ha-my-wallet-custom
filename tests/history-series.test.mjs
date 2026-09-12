import test from "node:test";
import assert from "node:assert/strict";
import { dailyPeriod, dailyPositionPoints, periodMetrics, recordedPoints } from "../custom_components/my_wallet/frontend/history-series.mjs";

const sample = (value, invested, dividends = 0, extra = {}) => ({ value, invested, dividends, ...extra });
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-8, `${actual} != ${expected}`);

test("component metrics isolate purchases and dividends while keeping the same daily window", () => {
  const rows = [
    { date: "2026-08-01", value: 999, positions: { AAA: 100, BBB: 200 }, position_costs: { AAA: 100, BBB: 200 }, position_dividends: { AAA: 0, BBB: 0 } },
    { date: "2026-08-02", value: 1999, positions: { AAA: 160, BBB: 198 }, position_costs: { AAA: 150, BBB: 200 }, position_dividends: { AAA: 2, BBB: 0 } },
  ];
  const original = structuredClone(rows);
  const a = dailyPositionPoints(rows, "AAA"), b = dailyPositionPoints(rows, "BBB");
  const metrics = periodMetrics(a, { position: true });
  assert.equal(metrics.capital, 50); assert.equal(metrics.dividends, 2); assert.equal(metrics.gain, 12); near(metrics.return, 12);
  assert.equal(periodMetrics(b, { position: true }).gain, -2);
  assert.deepEqual(a.map(p => p.date), b.map(p => p.date));
  assert.deepEqual(rows, original);
});

test("component history distinguishes absent holdings, missing quotes and unknown opening holdings", () => {
  const rows = [{ date: "2026-08-01", positions: {} }, { date: "2026-08-02", positions: { AAA: null, BBB: 5 }, position_costs: { AAA: 100 } }];
  const a = dailyPositionPoints(rows, "AAA");
  assert.equal(a[0].value, 0); assert.equal(a[1].value, null);
  assert.equal(periodMetrics(a, { position: true }).gain, null);
  assert.deepEqual(dailyPositionPoints(rows, "BBB", { unknownOpening: ["BBB"] }).map(p => p.value), [null, null]);
});

test("real component history uses per-position purchasing power and leaves missing coverage blank", () => {
  const rows = [
    { date: "2026-08-01", inflation_factor: 1.1, positions: { AAA: 100 }, real_positions: { AAA: 110 }, real_position_costs: { AAA: 99 }, real_position_dividends: { AAA: 2 } },
    { date: "2026-08-02", inflation_factor: null, positions: { AAA: 120 } },
  ];
  const points = dailyPositionPoints(rows, "AAA", { real: true });
  assert.deepEqual(points[0], { date: "2026-08-01", value: 110, invested: 99, dividends: 2 });
  assert.equal(points[1].value, null); assert.equal(points[1].invested, null);
  assert.equal(dailyPositionPoints(rows, "BBB", { real: true })[1].value, null);
});

test("metadata-sensitive legacy hashes do not hide returns for new recordings", () => {
  const points = [
    sample(100, 100, 0, { revision: "old-a", financial_revision: "same" }),
    sample(155, 150, 0, { revision: "old-b", financial_revision: "same" }),
  ];
  const result = periodMetrics(points);
  assert.equal(result.reason, null); near(result.gain, 5); near(result.capital, 50);
  assert.deepEqual(result.accounting_issues, []);
});

test("upgrades preserve legacy comparisons without inventing a correction", () => {
  const first = sample(100, 100, 0, { revision: "old" });
  const next = sample(101, 100, 0, { revision: "old", financial_revision: "new", timestamp: "2026-09-09T10:00:00Z" });
  assert.equal(periodMetrics([first, next]).reason, null);
  const changed = periodMetrics([first, { ...next, revision: "changed" }]);
  assert.equal(changed.reason, "accounting"); assert.equal(changed.gain, null);
  assert.deepEqual(changed.accounting_issues, [{ code: "legacy_revision", timestamp: next.timestamp }]);
});

test("financial revisions and reversals report the first affected sample, even across gaps", () => {
  const points = [
    sample(100, 100, 0, { financial_revision: "a", timestamp: "2026-09-09T08:00:00Z" }),
    sample(null, null),
    sample(120, 100, 0, { financial_revision: "b", timestamp: "2026-09-09T09:00:00Z" }),
    sample(100, 100, 0, { financial_revision: "c", timestamp: "2026-09-09T10:00:00Z" }),
  ];
  const result = periodMetrics(points);
  assert.equal(result.reason, "accounting"); assert.equal(result.gain, null);
  assert.deepEqual(result.accounting_issues, points.slice(2).map(p => ({ code: "financial_revision", timestamp: p.timestamp })));
});

test("observable changes give specific reasons instead of an opaque revision message", () => {
  for (const [code, changes] of [
    ["capital_reduced", { invested: 80 }],
    ["dividends_reduced", { dividends: 5 }],
    ["units_changed", { units: 12 }],
  ]) {
    const start = sample(100, 100, 10, { units: 10, financial_revision: "a" });
    const end = { ...start, ...changes, financial_revision: "b", timestamp: "2026-09-09T10:00:00Z" };
    const result = periodMetrics([start, end], { position: true });
    assert.deepEqual(result.accounting_issues, [{ code, timestamp: end.timestamp }]);
    assert.equal(result.capital, null); assert.equal(result.dividends, null);
  }
});

test("legacy correction dates stay date-only and cannot be mistaken for edit timestamps", () => {
  const result = periodMetrics([sample(100, 100), sample(110, 100)], {
    accountingEvents: [{ code: "legacy_correction", date: "2026-09-09" }],
  });
  assert.equal(result.reason, "accounting"); assert.equal(result.gain, null);
  assert.deepEqual(result.accounting_issues, [{ code: "legacy_correction", date: "2026-09-09" }]);
});

test("cash deposits do not become gains, and returns compound across intervals", () => {
  const result = periodMetrics([sample(100, 100), sample(110, 100), sample(175, 150)]);
  near(result.gain, 25); near(result.return, 25); near(result.capital, 50);
  assert.equal(result.reason, null);
  near(periodMetrics([sample(100, 100), sample(200, 200)]).gain, 0);
});

test("position dividends count as income but portfolio cash is not counted twice", () => {
  const position = periodMetrics([sample(100, 100), sample(95, 100, 10)], { position: true });
  near(position.gain, 5); near(position.return, 5); near(position.dividends, 10);
  const wallet = periodMetrics([sample(100, 100), sample(105, 100, 10)]);
  near(wallet.gain, 5); near(wallet.return, 5);
});

test("missing samples and missing capital never become zero-valued investments", () => {
  for (const points of [
    [sample(null, 100), sample(110, 100)],
    [sample(100, 100), sample(null, 100), sample(110, 100)],
    [sample(100, null), sample(110, 100)],
    [sample(100, 100), sample(Infinity, 100)],
    [sample(100, 100), sample(NaN, 100)],
  ]) {
    const result = periodMetrics(points);
    assert.equal(result.gain, null); assert.equal(result.return, null); assert.ok(result.reason);
  }
});

test("corrections and rewritten cash bases are not classified as performance", () => {
  const cases = [
    [sample(100, 100, 0, { revision: "a" }), sample(120, 100, 0, { revision: "b" })],
    [sample(100, 100), sample(100, 80)],
    [sample(100, 100, 0, { units: 10 }), sample(120, 100, 0, { units: 12 })],
  ];
  for (const points of cases) {
    const result = periodMetrics(points, { position: true });
    assert.equal(result.reason, "accounting"); assert.equal(result.gain, null);
    assert.equal(result.capital, null); assert.equal(result.return, null);
  }
  assert.equal(periodMetrics([sample(100, 100), sample(120, 100)], { accountingChanged: true }).return, null);
});

test("starting at zero permits the first investment without dividing by zero", () => {
  const result = periodMetrics([sample(0, 0), sample(50, 50), sample(55, 50)]);
  near(result.gain, 5); near(result.return, 10);
  assert.equal(periodMetrics([sample(0, 0), sample(0, 0)]).return, null);
  assert.equal(periodMetrics([sample(55, 50)]).reason, "insufficient");
});

test("calendar ranges clamp month ends and leap days without mutating history", () => {
  const march = ["2026-02-27", "2026-02-28", "2026-03-01", "2026-03-31"].map(date => ({ date }));
  assert.deepEqual(dailyPeriod(march, "month").map(p => p.date), ["2026-02-28", "2026-03-01", "2026-03-31"]);
  assert.equal(march.length, 4);
  const leap = ["2023-02-27", "2023-02-28", "2024-02-29"].map(date => ({ date }));
  assert.equal(dailyPeriod(leap, "year")[0].date, "2023-02-28");
  assert.strictEqual(dailyPeriod(march, "all"), march);
  assert.deepEqual(dailyPeriod([], "month"), []);
});

test("inflation conversion adjusts interval flows without inventing capital changes", () => {
  const points = [
    sample(100, 100, 0, { real_value: 101, real_cash: 0, factor: 1.01 }),
    sample(210, 200, 0, { real_value: 210, real_cash: 0, factor: 1 }),
  ];
  const result = periodMetrics(recordedPoints(points, true));
  near(result.capital, 100); near(result.gain, 9); near(result.return, 9 / 101 * 100);
  assert.equal(points[0].invested, 100);
  assert.strictEqual(recordedPoints(points, false), points);
  const missing = periodMetrics(recordedPoints([points[0], { ...points[1], factor: null, real_value: null }], true));
  assert.equal(missing.return, null);
});

test("rolling history keeps exact UTC timestamps through daylight-saving transitions", () => {
  const points = [
    sample(100, 100, 0, { timestamp: "2026-10-25T00:30:00+00:00" }),
    sample(101, 100, 0, { timestamp: "2026-10-25T01:30:00+00:00" }),
  ];
  const result = periodMetrics(points);
  assert.equal(result.start, points[0].timestamp); assert.equal(result.end, points[1].timestamp);
  near(result.return, 1);
});
