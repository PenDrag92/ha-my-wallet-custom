/* Request ownership is shared by every assistant action, including document previews. */
export class AssistantState {
  constructor() { this.reset(null); }
  reset(key) {
    this.key = key;
    this.generation = (this.generation || 0) + 1;
    this.sequence = {};
    this.results = {};
    this.errors = {};
    this.pending = new Set();
    this.sessionId = null;
    this.messages = [];
  }
  async run(kind, action) {
    const generation = this.generation;
    const sequence = this.sequence[kind] = (this.sequence[kind] || 0) + 1;
    this.pending.add(kind);
    delete this.errors[kind];
    const current = () => this.generation === generation && this.sequence[kind] === sequence;
    try {
      const result = await action();
      if (!current()) return null;
      this.results[kind] = result;
      return result;
    } catch (error) {
      if (current()) this.errors[kind] = error;
      return null;
    } finally {
      if (current()) this.pending.delete(kind);
    }
  }
  invalidate(kind) {
    this.sequence[kind] = (this.sequence[kind] || 0) + 1;
    this.pending.delete(kind);
    delete this.results[kind];
    delete this.errors[kind];
  }
}

export function inputNumber(value, { optional = false } = {}) {
  const text = String(value ?? "").trim();
  if (!text && optional) return undefined;
  if (!/^[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)$/.test(text)) throw new Error("invalid_number");
  const result = Number(text.replace(",", "."));
  if (!Number.isFinite(result)) throw new Error("invalid_number");
  return result;
}
