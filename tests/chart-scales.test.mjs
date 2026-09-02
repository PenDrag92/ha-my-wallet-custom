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

const fitted = (values, currency = "EUR") => currencyScale(values, currency, 4, { includeZero: false });

test("short-period axes reveal small price changes without extending to zero", () => {
  const values = [641.15, 641.88, null, 642.12, 641.48];
  const scale = fitted(values);
  assert.ok(scale.min > 640 && scale.min < 641.15);
  assert.ok(scale.max > 642.12 && scale.max < 644);
  assert.ok(scale.max - scale.min < 3);
  assert.ok(scale.ticks.length >= 3 && scale.ticks.length <= 8);
  assert.ok(values.filter(Number.isFinite).every(value => value > scale.min && value < scale.max));
  assert.deepEqual(scale, fitted(values.filter(Number.isFinite)), "missing samples are not zeros");
  assert.equal(new Set(axisLabels(scale, "de", "EUR")).size, scale.ticks.length);
});

test("fitted scales handle unchanged, single, empty and cent-level balances", () => {
  for (const values of [[], [null, NaN, Infinity], [640], [640, 640], [0], [0.01, 0.02], [-25, -24], [-0.01, 0, 0.01]]) {
    const scale = fitted(values);
    assert.ok(Number.isFinite(scale.min) && Number.isFinite(scale.max));
    assert.ok(scale.max > scale.min);
    assert.ok(scale.ticks.length >= 2 && scale.ticks.length <= 8);
    assert.ok(values.filter(Number.isFinite).every(value => value >= scale.min && value <= scale.max));
    assert.equal(new Set(axisLabels(scale, "de", "EUR")).size, scale.ticks.length);
    if (values.filter(Number.isFinite).every(value => value >= 0)) assert.ok(scale.min >= 0);
  }
  assert.deepEqual(fitted([640]), fitted([640, 640]), "poll counts do not change a flat scale");
  assert.ok(fitted([640]).min > 638);
});

test("large portfolios retain distinct labels even for small short-period changes", () => {
  for (const currency of ["EUR", "JPY", "KWD"]) {
    const values = [1_000_000.001, 1_000_000.012];
    const scale = fitted(values, currency);
    const labels = axisLabels(scale, "de", currency);
    assert.ok(values.every(value => value >= scale.min && value <= scale.max));
    assert.equal(new Set(labels).size, labels.length);
    assert.ok(scale.ticks.length <= 8);
    if (currency === "JPY") assert.ok(scale.ticks.every(Number.isInteger));
  }
});

test("changing the visible period or selected position fits only that series", () => {
  const day = fitted([640, 641]);
  const week = fitted([600, 640, 641, 700]);
  const position = fitted([51, 52]);
  const cash = fitted([0.01, 0.02]);
  assert.ok(week.min < 600 && week.max > 700);
  assert.ok(day.max - day.min < week.max - week.min);
  assert.ok(position.max < day.min);
  assert.ok(cash.max < 0.1);
});
