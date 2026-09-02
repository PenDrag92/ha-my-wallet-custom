/* Accept decimal unit counts without silently treating blanks as zero. */
export function parseUnits(value) {
  if (typeof value !== "string" && typeof value !== "number") return null;
  const text = String(value).trim();
  if (!/^(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:e[+-]?\d+)?$/i.test(text)) return null;
  const units = Number(text.replace(",", "."));
  if (units === 0 && /[1-9]/.test(text.split(/e/i)[0])) return null;
  return Number.isFinite(units) && units >= 0 && units <= 1e12 ? units : null;
}
