import assert from "node:assert/strict";
import test from "node:test";
import { parseUnits } from "../custom_components/my_wallet/frontend/unit-input.mjs";

test("exact fractional units accept German commas and decimal points", () => {
  assert.equal(parseUnits(" 2,949200123456 "), 2.949200123456);
  assert.equal(parseUnits("2.949200123456"), 2.949200123456);
  assert.equal(parseUnits(",3753"), 0.3753);
  assert.equal(parseUnits("0"), 0);
  assert.equal(parseUnits(0.000000000001), 0.000000000001);
  assert.equal(parseUnits("1e-12"), 0.000000000001);
});

test("empty, nonnumeric and ambiguously grouped input never becomes a holding", () => {
  for (const input of ["", " ", null, undefined, true, false, "1.234,5678", "1,234.5678", "1 234", "1,2,3", "3 Stück", "0x10"]) {
    assert.equal(parseUnits(input), null, String(input));
  }
});

test("negative, nonfinite and out-of-range holdings are rejected", () => {
  for (const input of ["-1", "-0,01", Infinity, NaN, "Infinity", "1e309", "1e-999", "1000000000001"]) {
    assert.equal(parseUnits(input), null, String(input));
  }
  assert.equal(parseUnits("1000000000000"), 1e12);
});
