/* Currency axes use readable minor-unit intervals; history can fit its data. */
export function currencyScale(values, currency = "EUR", intervals = 4, { includeZero = true } = {}) {
  const digits = new Intl.NumberFormat("en", { style: "currency", currency }).resolvedOptions().maximumFractionDigits;
  const quantum = 10 ** -digits;
  let low = includeZero ? 0 : Infinity, high = includeZero ? 0 : -Infinity;
  for (const value of values) {
    if (Number.isFinite(value)) { low = Math.min(low, value); high = Math.max(high, value); }
  }
  if (!Number.isFinite(low) || !Number.isFinite(high)) { low = 0; high = 1; }
  if (includeZero) {
    if (low === high) high = 1;
    low *= 1.05;
    high *= 1.05;
  } else {
    const minimum = low, maximum = high;
    const padding = high > low ? Math.max(quantum, (high - low) * .1) : Math.max(quantum * 2, Math.abs(low) * .001);
    low -= padding; high += padding;
    // Padding must not suggest a negative balance for nonnegative holdings.
    if (minimum >= 0) low = Math.max(0, low);
    else if (maximum <= 0) high = Math.min(0, high);
  }
  const rough = Math.max(quantum, (high - low) / intervals);
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map(factor => factor * magnitude).find(value =>
    value >= rough * (1 - 1e-12) && value >= quantum && Math.abs(value / quantum - Math.round(value / quantum)) < Math.max(1e-8, value / quantum * 1e-12)
  ) || Math.ceil(rough / quantum) * quantum;
  const first = Math.floor(low / step), last = Math.ceil(high / step);
  const ticks = Array.from({ length: last - first + 1 }, (_, index) => Number(((first + index) * step).toFixed(digits)));
  return { min: ticks[0], max: ticks.at(-1), step, ticks, digits };
}

export function axisLabels(scale, locale, currency) {
  const compact = Math.max(Math.abs(scale.min), Math.abs(scale.max)) >= 1e6;
  const formatter = new Intl.NumberFormat(locale, {
    style: "currency", currency, minimumFractionDigits: 0,
    maximumFractionDigits: compact ? Math.max(2, scale.digits) : scale.digits,
    ...(compact ? { notation: "compact" } : {}),
  });
  const labels = scale.ticks.map(value => formatter.format(value));
  if (new Set(labels).size === labels.length) return labels;
  // A tight axis around a large portfolio must not repeat the same "1M" label.
  const precise = new Intl.NumberFormat(locale, {
    style: "currency", currency, minimumFractionDigits: 0,
    maximumFractionDigits: scale.digits,
  });
  return scale.ticks.map(value => precise.format(value));
}
