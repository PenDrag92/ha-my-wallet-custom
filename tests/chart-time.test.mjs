import assert from "node:assert/strict";
import test from "node:test";
import { dayBoundaries } from "../custom_components/my_wallet/frontend/chart-time.mjs";

const boundaries = (start, end, zone) => dayBoundaries(Date.parse(start), Date.parse(end), zone).map(time => new Date(time).toISOString());

test("week boundaries use HA local midnight even when no quote exists there", () => {
  assert.deepEqual(boundaries("2026-10-21T17:13:00Z", "2026-10-28T17:13:00Z", "Europe/Berlin"), [
    "2026-10-21T22:00:00.000Z", "2026-10-22T22:00:00.000Z", "2026-10-23T22:00:00.000Z",
    "2026-10-24T22:00:00.000Z", "2026-10-25T23:00:00.000Z", "2026-10-26T23:00:00.000Z", "2026-10-27T23:00:00.000Z",
  ]);
});

test("spring DST gives a 23-hour calendar day; the autumn repeated hour is not another day", () => {
  const spring = dayBoundaries(Date.parse("2026-03-28T12:00:00Z"), Date.parse("2026-03-30T12:00:00Z"), "Europe/Berlin");
  assert.deepEqual(spring.map(time => new Date(time).toISOString()), ["2026-03-28T23:00:00.000Z", "2026-03-29T22:00:00.000Z"]);
  assert.equal((spring[1] - spring[0]) / 3600000, 23);
  assert.deepEqual(boundaries("2026-10-24T22:01:00Z", "2026-10-25T23:01:00Z", "Europe/Berlin"), ["2026-10-25T23:00:00.000Z"]);
});

test("fractional offsets and half-hour DST changes keep exact local boundaries", () => {
  assert.deepEqual(boundaries("2026-10-28T10:00:00Z", "2026-10-29T10:00:00Z", "Asia/Kathmandu"), ["2026-10-28T18:15:00.000Z"]);
  const points = dayBoundaries(Date.parse("2026-10-03T00:00:00Z"), Date.parse("2026-10-05T00:00:00Z"), "Australia/Lord_Howe");
  assert.deepEqual(points.map(time => new Date(time).toISOString()), ["2026-10-03T13:30:00.000Z", "2026-10-04T13:00:00.000Z"]);
});

test("day boundaries do not add duplicate edges or fictitious skipped dates", () => {
  assert.deepEqual(boundaries("2026-10-27T23:00:00Z", "2026-10-28T23:00:00Z", "Europe/Berlin"), []);
  assert.deepEqual(boundaries("2026-12-31T12:00:00Z", "2027-01-01T12:00:00Z", "UTC"), ["2027-01-01T00:00:00.000Z"]);
  assert.deepEqual(boundaries("2011-12-29T12:00:00Z", "2011-12-30T12:00:00Z", "Pacific/Apia"), ["2011-12-30T10:00:00.000Z"]);
});

test("empty, single-instant and invalid ranges produce no calendar grid", () => {
  for (const [start, end] of [[NaN, 1], [1, Infinity], [0, 0], [2, 1], [0, 33 * 86400000]]) assert.deepEqual(dayBoundaries(start, end), []);
});
