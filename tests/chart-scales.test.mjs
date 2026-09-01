import assert from "node:assert/strict";
import { test } from "node:test";
import { axisLabels, currencyScale } from "../custom_components/my_wallet/frontend/chart-scales.mjs";

test("portfolio axes use rounded euro intervals instead of arbitrary quarter ranges", () => {
  const scale = currencyScale([375, 475, 555, 650, 689.41]);
  assert.deepEqual(scale.ticks, [0, 200, 400, 600, 800]);
  assert.ok(axisLabels(scale, "de", "EUR").every(label => label.includes("€")));
});

test("cash has an independent cent-accurate scale", () => {
  assert.deepEqual(currencyScale([0, 75.01, 0.01]).ticks, [0, 20, 40, 60, 80]);
  const small = currencyScale([0.01, 0.02, 0.03]);
  assert.equal(small.step, 0.01);
  assert.equal(new Set(axisLabels(small, "de", "EUR")).size, small.ticks.length);
});

test("empty, zero, negative, single-point and large values remain bounded and readable", () => {
  for (const values of [[], [null, NaN], [0], [0.01], [-75, 0, 25], [-25, -10], [6e9, 9e9]]) {
    const scale = currencyScale(values);
    assert.ok(scale.max > scale.min);
    assert.ok(scale.ticks.length >= 2 && scale.ticks.length <= 8);
    assert.ok(values.filter(Number.isFinite).every(value => value >= scale.min && value <= scale.max));
    assert.ok(scale.ticks.includes(0));
    assert.equal(new Set(axisLabels(scale, "de", "EUR")).size, scale.ticks.length);
  }
});

test("zero-decimal currencies do not show fractional currency ticks", () => {
  const scale = currencyScale([0, 2, 3], "JPY");
  assert.ok(scale.ticks.every(Number.isInteger));
  assert.equal(new Set(axisLabels(scale, "ja", "JPY")).size, scale.ticks.length);
});
