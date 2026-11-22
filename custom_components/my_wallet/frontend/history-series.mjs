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

export function historyGapIds(points, key = "value") {
  const ids = [];
  const valid = point => finite(point[key]) && (key !== "value" || point[key] >= 0);
  for (let index = 0; index < points.length; index++) {
    const point = points[index];
    if (valid(point) || (index > 0 && !valid(points[index - 1]))) continue;
    // The last valid sample anchors the gap even while its end moves with
    // the clock or a later observation closes it.
    ids.push(index === 0 ? "start" : timestamp(points[index - 1]));
  }
  return ids;
}

export function periodMetrics(source, { position = false, accountingChanged = false, accountingEvents = [], timeZone = "UTC" } = {}) {
  const { points, shortened } = evaluationWindow(source);
  const first = points[0], last = points.at(-1);
  const result = {
    start: first ? timestamp(first) : null, end: last ? timestamp(last) : null,
    shortened, requested_start: source[0] ? timestamp(source[0]) : null, requested_end: source.at(-1) ? timestamp(source.at(-1)) : null,
    start_value: finite(first?.value) ? first.value : null, end_value: finite(last?.value) ? last.value : null,
    capital: null, dividends: null, gain: null, return: null, return_approximate: false, return_reason: null, reason: null, accounting_issues: [],
    value_change: null, comparable_sections: 0,
  };
  if (!hasInterval(points)) return { ...result, reason: "insufficient" };
  result.value_change = last.value - first.value;
  const { cuts, issues, unscoped } = accountingBreaks(points, position, accountingChanged, accountingEvents, timeZone);
  if (!issues.length && !unscoped) return { ...result, ...comparableMetrics(points, position) };
  result.reason = "accounting";
  result.accounting_issues = issues;
  if (unscoped) return result;

  const sections = [];
  let start = 0;
  for (const end of [...cuts, points.length]) {
    const section = evaluationWindow(points.slice(start, end)).points;
    if (hasInterval(section)) sections.push(comparableMetrics(section, position));
    start = end;
  }
  if (!sections.length) return result;
  result.comparable_sections = sections.length;
  for (const field of ["capital", "dividends", "gain"]) {
    if (sections.every(section => finite(section[field]))) {
      result[field] = sections.reduce((sum, section) => sum + section[field], 0);
    }
  }
  if (sections.every(section => !section.reason && !section.return_reason) &&
      sections.some(section => finite(section.return))) {
    const rate = (sections.reduce((factor, section) => factor * (1 + (section.return ?? 0) / 100), 1) - 1) * 100;
    if (finite(rate)) {
      result.return = rate;
      result.return_approximate = sections.some(section => section.return_approximate);
    }
  }
  return result;
}

function hasInterval(points) {
  if (points.length < 2) return false;
  const first = timestamp(points[0]), last = timestamp(points.at(-1));
  return !(first && last && Date.parse(last) <= Date.parse(first));
}

function accountingBreaks(points, position, accountingChanged, accountingEvents, timeZone) {
  const cuts = new Set(), issues = [];
  let previousBasis, previousFinancialRevision, previousBasisIndex, previousFinancialIndex;
  let previousCapital, previousDividends, previousUnits;
  let previousCapitalIndex, previousDividendsIndex;
  const issue = (code, point, index, since) => {
    for (let cut = since + 1; cut <= index; cut++) cuts.add(cut);
    issues.push({ code, timestamp: timestamp(point) || null });
  };
  const datedEvents = accountingEvents.filter(event => event.code === "legacy_correction" && /^\d{4}-\d{2}-\d{2}$/.test(event.date));
  // Legacy correction dates use the HA time zone, not the browser or UTC date.
  const formatter = datedEvents.length && new Intl.DateTimeFormat("en", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" });
  const localDate = point => {
    const stamp = timestamp(point);
    if (!stamp || !finite(Date.parse(stamp))) return null;
    if (stamp.length === 10) return stamp;
    const parts = Object.fromEntries(formatter.formatToParts(new Date(stamp)).map(part => [part.type, part.value]));
    return `${parts.year}-${parts.month}-${parts.day}`;
  };
  const startDay = datedEvents.length ? localDate(points[0]) : null, endDay = datedEvents.length ? localDate(points.at(-1)) : null;
  const relevantDates = datedEvents.filter(event => (!startDay || event.date >= startDay) && (!endDay || event.date <= endDay));
  issues.push(...relevantDates.map(({ code, date }) => ({ code, date })));
  // A date-only correction may have occurred anywhere that local day. Exclude
  // intervals touching it, including spans with no observation on that day.
  let previousDay;
  for (let index = 0; index < points.length; index++) {
    const point = points[index];
    if (relevantDates.length) {
      const day = localDate(point);
      if (index > 0 && relevantDates.some(event => (!previousDay || event.date >= previousDay) && (!day || event.date <= day))) cuts.add(index);
      previousDay = day;
    }
    let revisionIssue, revisionIndex;
    if (point.financial_revision && previousFinancialRevision) {
      if (point.financial_revision !== previousFinancialRevision) {
        revisionIssue = "financial_revision"; revisionIndex = previousFinancialIndex;
      }
    } else if (point.revision && previousBasis?.revision && point.revision !== previousBasis.revision) {
      revisionIssue = "legacy_revision"; revisionIndex = previousBasisIndex;
    }
    if (point.financial_revision) { previousFinancialRevision = point.financial_revision; previousFinancialIndex = index; }
    if (point.financial_revision || point.revision) { previousBasis = point; previousBasisIndex = index; }
    const rawCapital = Object.hasOwn(point, "nominal_invested") ? point.nominal_invested : point.invested;
    const rawDividends = Object.hasOwn(point, "nominal_dividends") ? point.nominal_dividends : point.dividends;
    // Prefer an observable reason over a generic revision marker for this sample.
    // Compare known accounting samples even when an intervening quote is absent.
    if (finite(rawCapital) && finite(previousCapital) && rawCapital - previousCapital < -0.005) issue("capital_reduced", point, index, previousCapitalIndex);
    else if (finite(rawDividends) && finite(previousDividends) && rawDividends - previousDividends < -0.005) issue("dividends_reduced", point, index, previousDividendsIndex);
    else if (position && finite(point.units) && previousUnits && finite(rawCapital) && finite(previousUnits.capital)
      && Math.abs(point.units - previousUnits.units) > 1e-8 && Math.abs(rawCapital - previousUnits.capital) < 0.005) issue("units_changed", point, index, previousUnits.index);
    else if (revisionIssue) issue(revisionIssue, point, index, revisionIndex);
    if (revisionIssue) for (let cut = revisionIndex + 1; cut <= index; cut++) cuts.add(cut);
    if (finite(rawCapital)) { previousCapital = rawCapital; previousCapitalIndex = index; }
    if (finite(rawDividends)) { previousDividends = rawDividends; previousDividendsIndex = index; }
    if (finite(point.units) && finite(rawCapital)) previousUnits = { units: point.units, capital: rawCapital, index };
  }
  return { cuts: [...cuts].sort((a, b) => a - b), issues, unscoped: accountingChanged && !datedEvents.length };
}

function comparableMetrics(points, position) {
  const first = points[0], last = points.at(-1);
  const delta = key => finite(first[key]) && finite(last[key]) &&
    (first[`${key}_epoch`] ?? 0) === (last[`${key}_epoch`] ?? 0) ? last[key] - first[key] : null;
  const result = { capital: delta("invested"), dividends: delta("dividends"), gain: null, return: null,
    return_approximate: false, return_reason: null, reason: null };
  if (result.capital === null || (position && result.dividends === null)) return { ...result, reason: "capital" };
  let linked = 1, measurable = false, previousValuation, previousIndex;
  for (let index = 0; index < points.length; index++) {
    const point = points[index];
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
  if (result.return === null) result.return_approximate = false;
  return result;
}
