/* Calendar ranges and flow-adjusted returns for the exact displayed interval. */
const finite = Number.isFinite;
const timestamp = point => point.timestamp || point.date;

export function dailyPositionPoints(points, symbol, { real = false, unknownOpening = [] } = {}) {
  const prefix = real ? "real_" : "";
  return points.map(point => {
    const read = key => Object.hasOwn(point[`${prefix}${key}`] || {}, symbol) ? point[`${prefix}${key}`][symbol] : 0;
    // An absent position before its first purchase is zero; missing quotes or
    // inflation coverage are not. Never substitute another position's values.
    const missing = unknownOpening.includes(symbol) || (real && !finite(point.inflation_factor));
    return { date: point.date, value: missing ? null : read("positions"),
      invested: missing ? null : read("position_costs"), dividends: missing ? null : read("position_dividends") };
  });
}

export function dailyPeriod(points, period) {
  if (!points.length || period === "all") return points;
  const months = { month: 1, three: 3, six: 6, year: 12 }[period];
  if (!months) return points;
  const end = new Date(`${points.at(-1).date}T00:00:00Z`);
  const first = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - months, 1));
  const lastDay = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0)).getUTCDate();
  first.setUTCDate(Math.min(end.getUTCDate(), lastDay));
  const cutoff = first.toISOString().slice(0, 10);
  return points.filter(point => point.date >= cutoff);
}

export function recordedPoints(points, real = false) {
  if (!real) return points;
  // Only changes in capital belong to the interval. Rebase to zero so inflation
  // cannot turn a changing purchasing-power factor into a fictitious deposit.
  let capital = 0, income = 0, previous;
  return points.map(point => {
    if (previous) {
      const validCapital = finite(point.invested) && finite(previous.invested) && finite(point.factor);
      const validIncome = finite(point.dividends) && finite(previous.dividends) && finite(point.factor);
      capital = validCapital && finite(capital) ? capital + (point.invested - previous.invested) * point.factor : null;
      income = validIncome && finite(income) ? income + (point.dividends - previous.dividends) * point.factor : null;
    } else {
      if (!finite(point.invested)) capital = null;
      if (!finite(point.dividends)) income = null;
    }
    previous = point;
    return { ...point, value: point.real_value ?? null, cash: point.real_cash ?? null, invested: capital, dividends: income };
  });
}

export function periodMetrics(points, { position = false, accountingChanged = false, accountingEvents = [] } = {}) {
  const first = points[0], last = points.at(-1);
  const result = {
    start: first ? timestamp(first) : null, end: last ? timestamp(last) : null,
    start_value: finite(first?.value) ? first.value : null, end_value: finite(last?.value) ? last.value : null,
    capital: null, dividends: null, gain: null, return: null, reason: null, accounting_issues: [],
  };
  if (points.length < 2) return { ...result, reason: "insufficient" };
  if (finite(first.invested) && finite(last.invested)) result.capital = last.invested - first.invested;
  if (finite(first.dividends) && finite(last.dividends)) result.dividends = last.dividends - first.dividends;
  let linked = 1, measurable = false, previousBasis;
  const issue = (code, point) => {
    result.reason = "accounting";
    result.accounting_issues.push({ code, timestamp: timestamp(point) || null });
  };
  if (accountingChanged) result.reason = "accounting";
  for (const event of accountingEvents) {
    if (event.code === "legacy_correction" && /^\d{4}-\d{2}-\d{2}$/.test(event.date)) {
      result.reason = "accounting";
      result.accounting_issues.push({ code: event.code, date: event.date });
    }
  }
  for (let index = 0; index < points.length; index++) {
    const point = points[index], prior = points[index - 1];
    if (!finite(point.value) || point.value < 0) result.reason ||= "gaps";
    if (!finite(point.invested) || (position && !finite(point.dividends))) result.reason ||= "capital";
    let revisionIssue;
    if (point.financial_revision && previousBasis?.financial_revision) {
      if (point.financial_revision !== previousBasis.financial_revision) revisionIssue = "financial_revision";
    } else if (point.revision && previousBasis?.revision && point.revision !== previousBasis.revision) revisionIssue = "legacy_revision";
    if (point.financial_revision || point.revision) previousBasis = point;
    if (!prior) continue;
    const capital = finite(point.invested) && finite(prior.invested) ? point.invested - prior.invested : NaN;
    const dividends = finite(point.dividends) && finite(prior.dividends) ? point.dividends - prior.dividends : NaN;
    const income = position ? dividends : 0;
    // Prefer an observable reason over a generic revision marker for this sample.
    if (capital < -0.005) issue("capital_reduced", point);
    else if (dividends < -0.005) issue("dividends_reduced", point);
    else if (position && finite(point.units) && finite(prior.units) && Math.abs(point.units - prior.units) > 1e-8 && Math.abs(capital) < 0.005) issue("units_changed", point);
    else if (revisionIssue) issue(revisionIssue, point);
    if (result.reason) continue;
    if (prior.value > 1e-10) {
      const factor = (point.value - capital + income) / prior.value;
      if (factor < 0 || !finite(factor)) result.reason = "capital";
      else { linked *= factor; measurable = true; }
    } else if (capital > 1e-10) {
      linked *= (point.value + income) / capital; measurable = true;
    } else if (Math.abs(point.value + income) > 0.005) result.reason = "capital";
  }
  if (!result.reason) {
    const gain = last.value - first.value - result.capital + (position ? result.dividends : 0);
    const rate = (linked - 1) * 100;
    result.gain = finite(gain) ? gain : null;
    result.return = measurable && finite(rate) ? rate : null;
  }
  // A rewritten basis cannot be labelled as a new deposit or dividend either.
  if (result.reason === "accounting") result.capital = result.dividends = null;
  return result;
}
