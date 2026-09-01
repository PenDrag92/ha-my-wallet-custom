/* Currency axes include zero and use readable, whole minor-unit intervals. */
export function currencyScale(values, currency = "EUR", intervals = 4) {
  const digits = new Intl.NumberFormat("en", { style: "currency", currency }).resolvedOptions().maximumFractionDigits;
  const quantum = 10 ** -digits;
  let low = 0, high = 0;
  for (const value of values) {
    if (Number.isFinite(value)) { low = Math.min(low, value); high = Math.max(high, value); }
  }
  if (low === high) high = 1;
  low *= 1.05;
  high *= 1.05;
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
  return scale.ticks.map(value => formatter.format(value));
}
