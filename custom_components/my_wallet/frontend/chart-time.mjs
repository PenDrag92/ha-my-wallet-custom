/* Calendar boundaries for short Recorder charts, independent of sample times. */
export function dayBoundaries(start, end, timeZone = "UTC") {
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start
    || end - start > 32 * 86400000) return [];
  const date = new Intl.DateTimeFormat("en", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" });
  const result = [];
  // Find local date changes instead of adding 24 hours: DST days can be shorter
  // or longer, and some zones even skip midnight during an offset change.
  let previous = start, previousDate = date.format(start);
  while (previous < end) {
    const next = Math.min(previous + 6 * 3600000, end), nextDate = date.format(next);
    if (nextDate !== previousDate) {
      let low = previous, high = next;
      while (high - low > 1) {
        const middle = Math.floor((low + high) / 2);
        if (date.format(middle) === previousDate) low = middle;
        else high = middle;
      }
      if (high > start && high < end) result.push(high);
    }
    previous = next; previousDate = nextDate;
  }
  return result;
}
