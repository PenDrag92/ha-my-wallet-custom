import { AssistantState, inputNumber } from "./assistant-state.mjs?v=1.13.0";
import { explain, assumptionNotes } from "./assistant-messages.mjs?v=1.13.0";

const words = {
  de: {
    addedRecords: "Neue Buchungen", matchedRecords: "Bereits vorhandene Buchungen", cashChange: "Änderung des Verrechnungsguthabens",
    periodSource: "Quelle: rekonstruierte Tages-Schlusskurse und aktueller Buchungsverlauf. Der laufende Monat reicht bis zum letzten verfügbaren Tag.",
    estimatedPeriod: "Die zugrunde liegenden Käufe enthalten Schätzungen.",
    details: "Details", field: "Angabe", setting: "Wert", share: "Ist-Anteil", deviation: "Abweichung (Prozentpunkte)", threshold: "Schwelle", lot_ids: "Kaufreferenzen", dividend_ids: "Dividendenreferenzen", count: "Anzahl", first_date: "Erster betroffener Tag", first_balance: "Erster Fehlbetrag", lowest_balance: "Niedrigster Saldo", change_pct: "Kursänderung (%)", target_sum: "Summe der Zielanteile", price: "Kurs", previous_close: "Vorheriger Schlusskurs", configured_units: "Eingetragene Anteile", included_units: "Enthaltene Anteile",
    source_id: "Importquelle (z. B. Brokerdepot)", sourceHint: "Verwende für spätere Abrechnungen derselben Quelle dasselbe Label. Eine Kontonummer ist nicht nötig.",
    month: "Auswertungsmonat", skipped: "Übersprungen", value_date: "Valutadatum", future_contributions: "Künftige Einzahlungen", growth: "Wertzuwachs",
    title: "Dein Depot verstehen und planen", intro: "Auswertungen und Szenarien verwenden die gespeicherten Depotdaten. Wähle für freie Fragen einen eingerichteten KI-Assistenten.",
    report: "Depotanalyse", refresh: "Analyse aktualisieren", chat: "Frage zu deinem Depot", ask: "Frage stellen", question: "Zum Beispiel: Welche Positionen haben im letzten Monat zum Gewinn beigetragen?",
    agent: "KI-Assistent", noAgent: "Noch kein passender KI-Assistent eingerichtet. Ordne einem Gesprächsassistenten in Home Assistant ausschließlich die unten genannte Wallet-API zu.",
    consent: "Ich möchte Frage und benötigte Depotdaten an den ausgewählten Anbieter senden.", local: "Lokal", cloud: "Externer Anbieter",
    scenario: "Szenario vergleichen", years: "Jahre", annual_return: "Renditeannahme pro Jahr (%)", monthly_extra: "Zusätzlich pro Monat", one_off: "Einmalige Einzahlung", start_date: "Änderung ab",
    plan_id: "Sparplan ändern (optional)", allPlans: "Alle / keine einzelne Planänderung", monthly_amount: "Neue Monatsrate dieses Plans", pause_until: "Sparplanpause bis",
    calculate: "Vergleichen", baseline: "Bisherige Planung", changed: "Dein Szenario", difference: "Unterschied", assumption: "Annahmen", mathematical: "Mathematisches Szenario mit deinen Annahmen. Angezeigte Beträge sind keine Vorhersage einzelner Wertpapierkurse.",
    allocation: "Neue Einzahlung verteilen", amount: "Neue Einzahlung", useCash: "Vorhandenes Verrechnungsguthaben mit einbeziehen", allocate: "Verteilung berechnen", remaining: "Verbleibendes Cash", symbol: "Position", target: "Ziel", before: "Vorher", after: "Nachher", buy: "Zuteilung",
    documents: "Abrechnung importieren", file: "CSV oder PDF", documentHint: "CSV: My-Wallet-Ereignisformat. PDF: Textdokument, strukturierte Erkennung durch eine AI-Task-Entität. Prüfe jede erkannte Buchung mit der Belegstelle.",
    aiTask: "AI-Task-Entität für PDF", documentConsent: "Ich möchte den Dokumenttext zur Erkennung an die ausgewählte AI-Task-Entität senden.",
    prepare: "Dokument prüfen", review: "Entscheidungen prüfen", commit: "Geprüfte Buchungen übernehmen", confirmed: "Ich habe alle Buchungen und Belegstellen geprüft.", done: "Die Buchungen wurden übernommen.",
    date: "Datum", type: "Buchung", units: "Anteile", source: "Belegstelle", status: "Prüfstatus", decision: "Entscheidung", choose: "Bitte entscheiden", skip: "Überspringen", add: "Als eigene Buchung hinzufügen", match: "Vorhandene Buchung",
    add_status: "Neu", duplicate: "Bereits vorhanden", review_status: "Prüfen", invalid: "Angaben korrigieren", deposit: "Einzahlung", purchase: "Kauf", dividend: "Dividende",
    busy: "Wird bearbeitet …", unavailable: "Für diese Auswertung fehlen geeignete Daten.", error: "Die Anfrage konnte nicht abgeschlossen werden.", noFindings: "Keine Hinweise aus den verfügbaren Prüfungen.",
    findings: "Hinweise zur Prüfung", facts: "Aktueller Stand", positions: "Positionen", period: "Monatsauswertung", gain: "Gewinn / Verlust", value: "Wert", cash: "Verrechnungskonto", invested: "Eingezahltes Kapital", profit: "Gewinn / Verlust", dividends: "Dividenden", currency: "Währung",
    asOf: "Berechnungsdatum", sampled: "Letzter Kursabruf", noPeriod: "Eine vollständige Monatsauswertung ist mit den verfügbaren Daten nicht möglich.", nominal: "Beträge in der Depotwährung, nominal.", chatHint: "Der Gesprächsassistent kann dieses Depot lesen und Szenarien berechnen.",
    newSession: "Neues Gespräch", sourceNote: "Erklärungen basieren auf den verfügbaren Daten. Prüfe Beträge in den Tabellen.", edits: "Angaben bearbeiten", fileLarge: "Die Datei ist zu groß (maximal 2 MB).",
  },
  en: {
    addedRecords: "New records", matchedRecords: "Existing records", cashChange: "Settlement cash change",
    periodSource: "Source: reconstructed daily closes and the current ledger. The current month ends at the latest available day.",
    estimatedPeriod: "The underlying purchases include estimates.",
    details: "Details", field: "Input", setting: "Value", share: "Current share", deviation: "Deviation (percentage points)", threshold: "Threshold", lot_ids: "Purchase references", dividend_ids: "Dividend references", count: "Count", first_date: "First affected date", first_balance: "First deficit", lowest_balance: "Lowest balance", change_pct: "Quote change (%)", target_sum: "Target sum", price: "Quote", previous_close: "Previous close", configured_units: "Configured units", included_units: "Included units",
    source_id: "Import source (e.g. broker account label)", sourceHint: "Reuse this label for later statements from the same source. An account number is not needed.",
    month: "Report month", skipped: "Skipped", value_date: "Value date", future_contributions: "Future contributions", growth: "Growth",
    title: "Understand and plan your portfolio", intro: "Reports and scenarios use saved portfolio data. Select a configured AI assistant for free-form questions.",
    report: "Portfolio report", refresh: "Refresh report", chat: "Ask about your portfolio", ask: "Ask", question: "For example: Which positions contributed to last month's gain?",
    agent: "AI assistant", noAgent: "No suitable assistant configured. In Home Assistant, assign only the Wallet API shown below to a conversation assistant.",
    consent: "Send my question and the required portfolio data to the selected provider.", local: "Local", cloud: "External provider",
    scenario: "Compare a scenario", years: "Years", annual_return: "Expected annual return (%)", monthly_extra: "Extra monthly contribution", one_off: "One-off deposit", start_date: "Changes start",
    plan_id: "Change a savings plan (optional)", allPlans: "All / no individual plan change", monthly_amount: "New monthly amount for this plan", pause_until: "Pause savings plans until",
    calculate: "Compare", baseline: "Existing plan", changed: "Your scenario", difference: "Difference", assumption: "Assumptions", mathematical: "A mathematical scenario using your assumptions. Amounts do not predict individual security prices.",
    allocation: "Allocate a new deposit", amount: "New deposit", useCash: "Include existing settlement cash", allocate: "Calculate allocation", remaining: "Remaining cash", symbol: "Position", target: "Target", before: "Before", after: "After", buy: "Allocation",
    documents: "Import a statement", file: "CSV or PDF", documentHint: "CSV: My Wallet event format. PDF: a text document, extracted by an AI Task entity. Check every extracted record against its source.",
    aiTask: "AI Task entity for PDF", documentConsent: "Send the document text to the selected AI Task entity for extraction.",
    prepare: "Review document", review: "Check decisions", commit: "Save reviewed records", confirmed: "I have checked every record and source.", done: "The records have been saved.",
    date: "Date", type: "Event", units: "Units", source: "Source", status: "Review status", decision: "Decision", choose: "Choose", skip: "Skip", add: "Add as a separate record", match: "Existing record",
    add_status: "New", duplicate: "Already present", review_status: "Review", invalid: "Correct details", deposit: "Deposit", purchase: "Purchase", dividend: "Dividend",
    busy: "Working …", unavailable: "Suitable data is missing for this calculation.", error: "The request could not be completed.", noFindings: "No findings from the available checks.",
    findings: "Items to review", facts: "Current portfolio", positions: "Positions", period: "Monthly report", gain: "Gain / loss", value: "Value", cash: "Settlement cash", invested: "Deposited capital", profit: "Gain / loss", dividends: "Dividends", currency: "Currency",
    asOf: "Calculation date", sampled: "Latest quote refresh", noPeriod: "The available data does not support a complete monthly report.", nominal: "Nominal amounts in the portfolio currency.", chatHint: "The conversation assistant can read this portfolio and calculate scenarios.",
    newSession: "New conversation", sourceNote: "Explanations use the available data. Check amounts against the tables.", edits: "Edit details", fileLarge: "File too large (maximum 2 MB).",
  },
};

const css = ":host{display:block;color:var(--primary-text-color,#202b36);font:14px/1.5 system-ui}*{box-sizing:border-box}h2{margin:0 0 8px;font-size:20px}h3{margin:0 0 12px}p{margin:8px 0}.muted{color:var(--secondary-text-color,#687581)}section{background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dae1e7);border-radius:14px;padding:22px;margin:16px 0}label{display:flex;flex-direction:column;gap:5px}input,select,textarea,button{font:inherit;color:inherit;border:1px solid var(--divider-color,#aebbc7);border-radius:7px;padding:9px;background:var(--card-background-color,#fff)}button{cursor:pointer}button.primary{background:var(--primary-color,#1878b5);color:#fff}button:disabled{opacity:.5;cursor:default}textarea{width:100%;min-height:85px;resize:vertical}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}.check{flex-direction:row;align-items:flex-start;margin:12px 0}.check input{margin-top:4px}.actions{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;margin:12px 0}th,td{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid var(--divider-color,#dae1e7)}td.number,th.number{text-align:right;white-space:nowrap}.metric{padding:14px;background:var(--secondary-background-color,#f1f5f8);border-radius:8px}.metric strong{display:block;font-size:22px;margin-top:6px}.notice{border-left:3px solid var(--primary-color,#1878b5);padding:8px 12px;background:var(--secondary-background-color,#f1f5f8)}.error{border-color:var(--error-color,#c33)}.message{white-space:pre-wrap;padding:12px 14px;border-radius:9px;background:var(--secondary-background-color,#f1f5f8);margin:12px 0}.question{font-weight:600}summary{cursor:pointer;font-weight:600}details{margin:10px 0}td input{max-width:155px}code{overflow-wrap:anywhere}a{color:var(--primary-color,#1878b5)}@media(max-width:600px){section{padding:15px}.grid{grid-template-columns:1fr}th,td{padding:7px}h2{font-size:18px}}";
function el(tag, text, className) {
  const element = document.createElement(tag);
  if (text != null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}
function btn(text, action, primary = false) {
  const item = el("button", text, primary ? "primary" : "");
  item.type = "button"; item.addEventListener("click", action); return item;
}
function option(value, text) { const item = el("option", text); item.value = value; return item; }

export class WalletAssistant extends HTMLElement {
  constructor() {
    super(); this.attachShadow({ mode: "open" }); this.state = new AssistantState();
    this.form = {}; this.decisions = {}; this.corrections = {};
  }
  configure({ hass, wallet, lang, onChange }) {
    const key = (hass.user?.id || "") + ":" + wallet.entry_id;
    this.hass = hass; this.wallet = wallet; this.lang = lang; this.onChange = onChange;
    if (key !== this.state.key) {
      this.state.reset(key); this.form = { years: "10", monthly_extra: "0", one_off: "0", amount: "500" };
      this.decisions = {}; this.corrections = {}; this.file = null; this.confirmed = false;
      this.load();
    } else if (!this.shadowRoot.childNodes.length) this.render();
  }
  t(key) { return words[this.lang]?.[key] || words.en[key] || key; }
  money(value) { return typeof value === "number" && Number.isFinite(value) ? new Intl.NumberFormat(this.lang, { style: "currency", currency: this.wallet.currency }).format(value) : "—"; }
  pct(value) { return typeof value === "number" && Number.isFinite(value) ? new Intl.NumberFormat(this.lang, { maximumFractionDigits: 2 }).format(value) + " %" : "—"; }
  call(type, args = {}) { return this.hass.callWS({ type: "my_wallet/" + type, entry_id: this.wallet.entry_id, ...args }); }
  async run(kind, action) {
    const promise = this.state.run(kind, action); this.render();
    const result = await promise; this.render(); return result;
  }
  async load() {
    await Promise.all([
      this.run("report", () => this.call("assistant/report")),
      this.run("agents", () => this.call("assistant/agents")),
    ]);
  }
  notice(parent, text, error = false) { parent.append(el("p", text, "notice" + (error ? " error" : ""))); }
  status(parent, kind) {
    if (this.state.pending.has(kind)) { const p = el("p", this.t("busy"), "notice"); p.setAttribute("role", "status"); parent.append(p); }
    const error = this.state.errors[kind];
    if (error) this.notice(parent, explain(error.code || error.message, this.lang, this.t("error") + " " + (error.message || error.code || "")), true);
  }
  section(key) { const node = el("section"); node.append(el("h2", this.t(key))); this.shadowRoot.append(node); return node; }
  resultArea(parent, kind) {
    const area = el("div"); (this.resultNodes ||= {})[kind] = area; parent.append(area); return area;
  }
  invalidateResult(kind) {
    this.state.invalidate(kind);
    this.resultNodes?.[kind]?.replaceChildren();
  }
  input(parent, key, initial = "", type = "text") {
    const label = el("label", this.t(key)); const input = el("input");
    input.type = type; input.value = this.form[key] ?? initial;
    const kind = ["years", "annual_return", "monthly_extra", "one_off", "start_date", "monthly_amount", "pause_until"].includes(key) ? "scenario" : key === "amount" ? "allocation" : key === "month" ? "report" : ["source_id", "aiTask"].includes(key) ? "document" : null;
    input.disabled = Boolean(kind && this.state.pending.has(kind));
    input.addEventListener("input", () => { this.form[key] = input.value; if (kind) this.invalidateResult(kind); });
    label.append(input); parent.append(label); return input;
  }
  check(parent, key, stateKey) {
    const label = el("label", null, "check"), input = el("input"); input.type = "checkbox"; input.checked = Boolean(this.form[stateKey]);
    input.addEventListener("change", () => { this.form[stateKey] = input.checked; if (stateKey === "useCash") this.state.invalidate("allocation"); this.render(); });
    input.disabled = this.state.pending.has(stateKey === "useCash" ? "allocation" : stateKey === "consent" ? "ask" : "document");
    label.append(input, el("span", this.t(key))); parent.append(label); return input;
  }
  table(parent, headings, rows) {
    const scroll = el("div", null, "scroll"), table = el("table"), head = el("tr");
    for (const heading of headings) { const th = el("th", this.t(heading)); th.scope = "col"; head.append(th); }
    const thead = el("thead"); thead.append(head); table.append(thead);
    const body = el("tbody");
    for (const row of rows) { const tr = el("tr"); for (const value of row) { const td = el("td"); value instanceof Node ? td.append(value) : td.append(el("span", value ?? "—")); tr.append(td); } body.append(tr); }
    table.append(body); scroll.append(table); parent.append(scroll);
  }
  metrics(parent, pairs) {
    const grid = el("div", null, "grid");
    for (const [key, value] of pairs) { const metric = el("div", this.t(key), "metric"); metric.append(el("strong", this.money(value))); grid.append(metric); }
    parent.append(grid);
  }
  render() {
    this.shadowRoot.replaceChildren(el("style", css));
    if (!this.wallet) return;
    this.shadowRoot.append(el("h2", this.t("title")), el("p", this.t("intro"), "muted"));
    this.renderChat(); this.renderReport(); this.renderScenario(); this.renderAllocation(); this.renderDocuments();
  }
  renderChat() {
    const box = this.section("chat"), agents = this.state.results.agents?.agents || [];
    this.status(box, "agents");
    if (!agents.length) {
      this.notice(box, this.t("noAgent")); box.append(el("code", this.state.results.agents?.api_id || ""));
      box.append(btn(this.t("refresh"), () => this.load())); return;
    }
    const label = el("label", this.t("agent")), select = el("select");
    select.append(option("", this.t("choose")));
    for (const agent of agents) select.append(option(agent.agent_id, agent.name + " · " + (agent.external ? this.t("cloud") : this.t("local"))));
    select.value = this.form.agent || "";
    select.disabled = this.state.pending.has("ask");
    select.addEventListener("change", () => { this.state.invalidate("ask"); this.form.agent = select.value; this.form.consent = false; this.state.sessionId = null; this.state.messages = []; this.render(); });
    label.append(select); box.append(label, el("p", this.t("chatHint"), "muted"));
    const agent = agents.find(item => item.agent_id === this.form.agent);
    if (agent?.external) this.check(box, "consent", "consent");
    for (const message of this.state.messages) box.append(el("div", message.text, "message" + (message.role === "user" ? " question" : "")));
    const prompt = el("textarea"); prompt.placeholder = this.t("question"); prompt.setAttribute("aria-label", this.t("chat")); prompt.maxLength = 4000; prompt.value = this.form.question || "";
    prompt.addEventListener("input", () => { this.form.question = prompt.value; }); box.append(prompt);
    const ask = btn(this.t("ask"), () => this.ask(), true); ask.disabled = !agent || this.state.pending.has("ask");
    const actions = el("div", null, "actions"); actions.append(ask, btn(this.t("newSession"), () => { this.state.invalidate("ask"); this.state.sessionId = null; this.state.messages = []; this.render(); })); box.append(actions);
    this.status(box, "ask");
  }
  async ask() {
    const text = (this.form.question || "").trim(); if (!text) return;
    const generation = this.state.generation;
    const result = await this.run("ask", () => this.call("assistant/ask", { agent_id: this.form.agent, text, language: this.lang, allow_external: Boolean(this.form.consent), ...(this.state.sessionId ? { session_id: this.state.sessionId } : {}) }));
    if (result && generation === this.state.generation) {
      this.state.sessionId = result.session_id; this.state.messages.push({ role: "user", text }, { role: "assistant", text: result.text }); this.form.question = "";
      for (const item of result.results || []) if (["report", "scenario", "allocation"].includes(item.tool)) this.state.results[item.tool] = item.result;
      this.render();
    }
  }
  renderReport() {
    let box = this.section("report"); const report = this.state.results.report;
    this.input(box, "month", "", "month");
    box.append(btn(this.t("refresh"), () => this.run("report", () => this.call("assistant/report", this.form.month ? { month: this.form.month } : {}))));
    box = this.resultArea(box, "report"); this.status(box, "report");
    if (!report) return;
    box.append(el("p", this.t("asOf") + ": " + (report.as_of || "—") + " · " + this.t("sampled") + ": " + (report.sampled_at || "—"), "muted"), el("p", this.t("nominal"), "muted"));
    const facts = report.facts || {};
    this.metrics(box, [["value", facts.value ?? facts.total], ["invested", facts.invested ?? facts.cost], ["profit", facts.profit], ["cash", facts.cash]]);
    box.append(el("h3", this.t("findings")));
    if (!(report.findings || []).length) box.append(el("p", this.t("noFindings"), "muted"));
    for (const item of report.findings || []) {
      this.notice(box, (item.evidence?.symbol ? item.evidence.symbol + ": " : "") + explain(item.code, this.lang, item.message?.[this.lang] || item.message || item.description || item.code));
      if (Object.keys(item.evidence || {}).length) {
        const details = el("details"); details.append(el("summary", this.t("details")));
        this.table(details, ["field", "setting"], Object.entries(item.evidence).map(([key, value]) => [this.t(key), Array.isArray(value) ? value.join(", ") : typeof value === "number" ? new Intl.NumberFormat(this.lang, { maximumFractionDigits: 4 }).format(value) : value]));
        box.append(details);
      }
    }
    const period = report.period;
    box.append(el("h3", this.t("period")));
    box.append(el("p", this.t("periodSource"), "muted"));
    if (period?.estimated_purchases) this.notice(box, this.t("estimatedPeriod"));
    if (period?.status === "ok") {
      box.append(el("p", period.month || period.period || ""));
      this.metrics(box, [["gain", period.wallet?.gain]]);
      this.table(box, ["symbol", "gain"], (period.positions || period.contributions || []).map(item => [item.symbol, this.money(item.gain)]));
    } else this.notice(box, this.t("noPeriod"));
    this.table(box, ["symbol", "value", "profit", "target"], (report.positions || []).map(item => [item.alias || item.symbol, this.money(item.nominal?.value), this.money(item.nominal?.profit), this.pct(item.target_share ?? item.target)]));
  }
  renderScenario() {
    let box = this.section("scenario"); const form = el("div", null, "grid");
    for (const [key, initial, type] of [["years", "10"], ["annual_return", ""], ["monthly_extra", "0"], ["one_off", "0"], ["start_date", "", "date"]]) this.input(form, key, initial, type);
    const label = el("label", this.t("plan_id")), select = el("select");
    select.append(option("", this.t("allPlans")));
    for (const plan of this.wallet.plans || []) select.append(option(plan.id, plan.name || plan.id));
    select.value = this.form.plan_id || ""; select.disabled = this.state.pending.has("scenario");
    select.addEventListener("change", () => { this.form.plan_id = select.value; this.state.invalidate("scenario"); this.render(); }); label.append(select); form.append(label);
    this.input(form, "monthly_amount"); this.input(form, "pause_until", "", "date"); box.append(form);
    const action = btn(this.t("calculate"), () => this.run("scenario", () => {
      const scenario = {};
      for (const key of ["years", "annual_return", "monthly_extra", "one_off", "monthly_amount"]) {
        const value = inputNumber(this.form[key], { optional: key !== "years" }); if (value !== undefined) scenario[key] = value;
      }
      for (const key of ["start_date", "plan_id", "pause_until"]) if (this.form[key]) scenario[key] = this.form[key];
      return this.call("assistant/scenario", { scenario });
    }), true); action.disabled = this.state.pending.has("scenario"); box.append(el("p", this.t("mathematical"), "muted"), action);
    box = this.resultArea(box, "scenario"); this.status(box, "scenario");
    const result = this.state.results.scenario;
    if (result?.status === "ok") {
      const value = item => typeof item === "number" ? item : item?.final_value;
      this.metrics(box, [["baseline", value(result.baseline)], ["changed", value(result.scenario)], ["difference", value(result.difference)]]);
      this.table(box, ["", "baseline", "changed"], [["future_contributions", result.baseline.future_contributions, result.scenario.future_contributions], ["growth", result.baseline.growth, result.scenario.growth]].map(([label, before, after]) => [this.t(label), this.money(before), this.money(after)]));
      box.append(el("p", result.as_of + " → " + result.through, "muted")); this.assumptions(box, result);
    } else if (result) this.notice(box, explain(result.reason, this.lang, this.t("unavailable")));
  }
  assumptions(box, result) {
    if (!result.assumptions) return;
    const details = el("details"); details.append(el("summary", this.t("assumption")));
    const list = el("ul"), assumptions = assumptionNotes(result, this.lang);
    for (const text of Array.isArray(assumptions) ? assumptions : Object.entries(assumptions).map(([key, value]) => this.t(key) + ": " + (typeof value === "object" ? JSON.stringify(value) : value))) list.append(el("li", text));
    details.append(list); box.append(details);
    if (result.inputs) this.table(details, ["field", "setting"], Object.entries(result.inputs).filter(([, value]) => value != null).map(([key, value]) => [this.t(key), value]));
  }
  renderAllocation() {
    let box = this.section("allocation");
    this.input(box, "amount", "500"); this.check(box, "useCash", "useCash");
    const action = btn(this.t("allocate"), () => this.run("allocation", () => this.call("assistant/allocation", { amount: inputNumber(this.form.amount), use_cash: Boolean(this.form.useCash) })), true);
    action.disabled = this.state.pending.has("allocation"); box.append(action);
    box = this.resultArea(box, "allocation"); this.status(box, "allocation");
    const result = this.state.results.allocation;
    if (result?.status === "ok") {
      this.table(box, ["symbol", "buy", "target", "before", "after"], result.allocations.map(row => [row.symbol, this.money(row.amount), this.pct(row.target_share), this.pct(row.before_share), this.pct(row.after_share)]));
      box.append(el("p", this.t("remaining") + ": " + this.money(result.remaining_cash))); this.assumptions(box, result);
    } else if (result) this.notice(box, explain(result.reason, this.lang, this.t("unavailable")));
  }
  renderDocuments() {
    let box = this.section("documents"); box.append(el("p", this.t("documentHint"), "muted"));
    const pending = this.state.pending.has("document");
    const sourceInput = this.input(box, "source_id"); sourceInput.disabled = pending;
    box.append(el("p", this.t("sourceHint"), "muted"));
    const fileLabel = el("label", this.t("file")), input = el("input"); input.type = "file"; input.accept = ".csv,.pdf";
    input.disabled = this.state.pending.has("document");
    input.addEventListener("change", () => { this.state.invalidate("document"); this.file = input.files?.[0] || null; this.decisions = {}; this.corrections = {}; this.confirmed = false; this.render(); }); fileLabel.append(input); box.append(fileLabel);
    if (this.file) box.append(el("p", this.file.name));
    const pdf = this.file?.name.toLowerCase().endsWith(".pdf");
    if (pdf) { this.input(box, "aiTask").disabled = pending; this.check(box, "documentConsent", "documentConsent").disabled = pending; }
    const prepare = btn(this.t("prepare"), () => this.prepareDocument(), true); prepare.disabled = !this.file || this.state.pending.has("document"); box.append(prepare);
    box = this.resultArea(box, "document"); this.status(box, "document");
    const preview = this.state.results.document;
    if (!preview) return;
    if (preview.saved) { this.notice(box, this.t("done")); return; }
    if (preview.summary) box.append(el("p", this.t("addedRecords") + ": " + preview.summary.added + " · " + this.t("matchedRecords") + ": " + preview.summary.duplicates + " · " + this.t("cashChange") + ": " + this.money(preview.summary.cash_change)));
    for (const issue of preview.issues || []) this.notice(box, explain(typeof issue === "string" ? issue : issue.code, this.lang, typeof issue === "string" ? issue : issue.message || issue.code), true);
    const rows = (preview.rows || []).map(row => {
      const source = row.source || {}, proof = el("div");
      proof.append(el("p", source.filename + (source.page ? " · p. " + source.page : source.row ? " · " + source.row : "")), el("q", source.quote || ""));
      const status = el("div", this.t(row.status === "add" ? "add_status" : row.status === "review" ? "review_status" : row.status));
      for (const issue of row.issues || []) status.append(el("p", explain(typeof issue === "string" ? issue : issue.code, this.lang)));
      const select = el("select"); select.append(option("", this.t("choose")), option("skip", this.t("skip")), option("add", this.t("add")));
      select.disabled = pending;
      for (const match of row.matches || []) { const id = typeof match === "string" ? match : match.id; select.append(option(id, this.t("match") + ": " + (match.date ? match.date + " · " + this.money(match.amount) + " · " : "") + id)); }
      select.value = this.decisions[row.id] || ""; select.addEventListener("change", () => { this.decisions[row.id] = select.value; preview.token = null; this.confirmed = false; this.render(); });
      const edit = el("details"); edit.append(el("summary", this.t("edits")));
      for (const key of ["type", "date", "amount", "currency", "symbol", "units", "value_date"]) {
        const label = el("label", this.t(key)), field = el("input"); field.value = this.corrections[row.id]?.[key] ?? row[key] ?? ""; field.disabled = pending;
        field.addEventListener("input", () => { (this.corrections[row.id] ||= {})[key] = field.value; preview.token = null; this.confirmed = false; });
        field.addEventListener("change", () => this.render()); label.append(field); edit.append(label);
      }
      const decision = el("div"); decision.append(select, edit);
      return [this.t(row.type), row.date, row.symbol || "—", String(row.amount ?? "—") + " " + (row.currency || ""), row.units || "—", proof, status, decision];
    });
    this.table(box, ["type", "date", "symbol", "amount", "units", "source", "status", "decision"], rows);
    const review = btn(this.t("review"), () => this.run("document", () => this.call("document_review", { draft_id: preview.draft_id, decisions: this.decisions, corrections: this.corrections })));
    review.disabled = pending; box.append(review);
    if (preview.token) {
      const check = el("label", null, "check"), checkbox = el("input"); checkbox.type = "checkbox"; checkbox.checked = this.confirmed;
      checkbox.disabled = pending;
      checkbox.addEventListener("change", () => { this.confirmed = checkbox.checked; this.render(); }); check.append(checkbox, el("span", this.t("confirmed"))); box.append(check);
      const commit = btn(this.t("commit"), () => this.commitDocument(), true); commit.disabled = !this.confirmed || this.state.pending.has("document"); box.append(commit);
    }
  }
  async prepareDocument() {
    const file = this.file; if (!file) return;
    const generation = this.state.generation; this.decisions = {}; this.corrections = {}; this.confirmed = false;
    await this.run("document", async () => {
      if (!this.form.source_id?.trim()) throw new Error(this.t("source_id"));
      if (file.size > 2000000) throw new Error(this.t("fileLarge"));
      const pdf = file.name.toLowerCase().endsWith(".pdf");
      let content;
      if (pdf) {
        const bytes = new Uint8Array(await file.arrayBuffer()); const chunks = [];
        for (let start = 0; start < bytes.length; start += 8192) chunks.push(String.fromCharCode(...bytes.subarray(start, start + 8192)));
        content = btoa(chunks.join(""));
      } else content = await file.text();
      if (generation !== this.state.generation || file !== this.file) throw new Error("document_changed");
      return this.call("document_prepare", { format: pdf ? "pdf" : "csv", source_id: this.form.source_id.trim(), filename: file.name, content, ...(pdf ? { ai_task_entity_id: this.form.aiTask || "", allow_external: Boolean(this.form.documentConsent) } : {}) });
    });
  }
  async commitDocument() {
    const preview = this.state.results.document; if (!preview?.token || !this.confirmed) return;
    const result = await this.run("document", () => this.call("document_commit", { token: preview.token, confirm: true }));
    if (result) { this.state.results.document = { saved: true }; this.render(); await this.onChange?.(); this.load(); }
  }
}
if (!customElements.get("wallet-assistant")) customElements.define("wallet-assistant", WalletAssistant);
