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
  const flows = { invested: { total: 0, epoch: 0 }, dividends: { total: 0, epoch: 0 } };
  return points.map(point => {
    const converted = { ...point, value: point.real_value ?? null, cash: point.real_cash ?? null,
      nominal_invested: point.invested, nominal_dividends: point.dividends };
    for (const [key, flow] of Object.entries(flows)) {
      if (!finite(point[key])) { converted[key] = null; flow.gap = true; continue; }
      if (flow.previous) {
        const delta = point[key] - flow.previous[key];
        // A zero flow needs no inflation factor. Across a missing accounting
        // sample, a nonzero flow is convertible only if the factor stayed equal.
        const known = delta === 0 || (finite(point.factor) && point.factor > 0
          && (!flow.gap || point.factor === flow.previous.factor));
        if (known) flow.total += delta === 0 ? 0 : delta * point.factor;
        else { flow.total = 0; flow.epoch++; }
      }
      converted[key] = flow.total;
      converted[`${key}_epoch`] = flow.epoch;
      flow.previous = point; flow.gap = false;
    }
    return converted;
  });
}

export function evaluationWindow(points, key = "value") {
  const valid = point => finite(point[key]) && (key !== "value" || point[key] >= 0);
  const first = points.findIndex(valid), last = points.findLastIndex(valid);
  return { points: first < 0 ? [] : points.slice(first, last + 1),
    shortened: first >= 0 && (first > 0 || last < points.length - 1) };
}

export function periodMetrics(source, { position = false, accountingChanged = false, accountingEvents = [], timeZone = "UTC" } = {}) {
  const { points, shortened } = evaluationWindow(source);
  const first = points[0], last = points.at(-1);
  const result = {
    start: first ? timestamp(first) : null, end: last ? timestamp(last) : null,
    shortened, requested_start: source[0] ? timestamp(source[0]) : null, requested_end: source.at(-1) ? timestamp(source.at(-1)) : null,
    start_value: finite(first?.value) ? first.value : null, end_value: finite(last?.value) ? last.value : null,
    capital: null, dividends: null, gain: null, return: null, return_approximate: false, return_reason: null, reason: null, accounting_issues: [],
  };
  if (points.length < 2 || (timestamp(first) && timestamp(last) && Date.parse(timestamp(last)) <= Date.parse(timestamp(first)))) return { ...result, reason: "insufficient" };
  const sameEpoch = (a, b, key) => (a[`${key}_epoch`] ?? 0) === (b[`${key}_epoch`] ?? 0);
  if (finite(first.invested) && finite(last.invested) && sameEpoch(first, last, "invested")) result.capital = last.invested - first.invested;
  if (finite(first.dividends) && finite(last.dividends) && sameEpoch(first, last, "dividends")) result.dividends = last.dividends - first.dividends;
  if (!finite(result.capital) || (position && !finite(result.dividends))) result.reason = "capital";
  let linked = 1, measurable = false, previousBasis, previousFinancialRevision, previousValuation, previousIndex;
  let previousCapital, previousDividends, previousUnits;
  const issue = (code, point) => {
    result.reason = "accounting";
    result.accounting_issues.push({ code, timestamp: timestamp(point) || null });
  };
  const datedEvents = accountingEvents.filter(event => event.code === "legacy_correction" && /^\d{4}-\d{2}-\d{2}$/.test(event.date));
  // Legacy correction dates use the HA time zone, not the browser or UTC date.
  const localDate = point => {
    const stamp = timestamp(point);
    if (!stamp || !finite(Date.parse(stamp))) return null;
    if (stamp.length === 10) return stamp;
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(stamp)).map(part => [part.type, part.value]));
    return `${parts.year}-${parts.month}-${parts.day}`;
  };
  if (accountingChanged && !datedEvents.length) result.reason = "accounting";
  const startDay = datedEvents.length ? localDate(first) : null, endDay = datedEvents.length ? localDate(last) : null;
  for (const event of datedEvents) {
    if ((!startDay || event.date >= startDay) && (!endDay || event.date <= endDay)) {
      result.reason = "accounting";
      result.accounting_issues.push({ code: event.code, date: event.date });
    }
  }
  for (let index = 0; index < points.length; index++) {
    const point = points[index];
    let revisionIssue;
    if (point.financial_revision && previousFinancialRevision) {
      if (point.financial_revision !== previousFinancialRevision) revisionIssue = "financial_revision";
    } else if (point.revision && previousBasis?.revision && point.revision !== previousBasis.revision) revisionIssue = "legacy_revision";
    if (point.financial_revision) previousFinancialRevision = point.financial_revision;
    if (point.financial_revision || point.revision) previousBasis = point;
    const rawCapital = Object.hasOwn(point, "nominal_invested") ? point.nominal_invested : point.invested;
    const rawDividends = Object.hasOwn(point, "nominal_dividends") ? point.nominal_dividends : point.dividends;
    // Prefer an observable reason over a generic revision marker for this sample.
    // Compare known accounting samples even when an intervening quote is absent.
    if (finite(rawCapital) && finite(previousCapital) && rawCapital - previousCapital < -0.005) issue("capital_reduced", point);
    else if (finite(rawDividends) && finite(previousDividends) && rawDividends - previousDividends < -0.005) issue("dividends_reduced", point);
    else if (position && finite(point.units) && previousUnits && finite(rawCapital) && finite(previousUnits.capital)
      && Math.abs(point.units - previousUnits.units) > 1e-8 && Math.abs(rawCapital - previousUnits.capital) < 0.005) issue("units_changed", point);
    else if (revisionIssue) issue(revisionIssue, point);
    if (finite(rawCapital)) previousCapital = rawCapital;
    if (finite(rawDividends)) previousDividends = rawDividends;
    if (finite(point.units) && finite(rawCapital)) previousUnits = { units: point.units, capital: rawCapital };
    // Cumulative flows at valid boundaries survive gaps; no quotes are filled in.
    if (!finite(point.value) || point.value < 0 || !finite(point.invested) || (position && !finite(point.dividends))) continue;
    const prior = previousValuation, priorIndex = previousIndex;
    previousValuation = point; previousIndex = index;
    if (!prior) continue;
    if (result.reason) continue;
    const capital = point.invested - prior.invested;
    const income = position ? point.dividends - prior.dividends : 0;
    if (index > priorIndex + 1 && (Math.abs(capital) > 1e-10 || Math.abs(income) > 1e-10)) result.return_approximate = true;
    if (prior.value > 1e-10) {
      const factor = (point.value - capital + income) / prior.value;
      if (factor < 0 || !finite(factor)) result.return_reason = "unavailable";
      else { linked *= factor; measurable = true; }
    } else if (capital > 1e-10) {
      linked *= (point.value + income) / capital; measurable = true;
    } else if (Math.abs(point.value + income) > 0.005) result.reason = "capital";
  }
  if (!result.reason) {
    const gain = last.value - first.value - result.capital + (position ? result.dividends : 0);
    const rate = (linked - 1) * 100;
    result.gain = finite(gain) ? gain : null;
    result.return = !result.return_reason && measurable && finite(rate) ? rate : null;
  }
  // A rewritten basis cannot be labelled as a new deposit or dividend either.
  if (result.reason === "accounting") result.capital = result.dividends = null;
  if (result.return === null) result.return_approximate = false;
  return result;
}
