/* My Wallet: local-only UI. Financial data comes from authenticated HA WebSocket calls. */
const WORDS = {
  de: {
    subtitle: "Depotverlauf", wallet: "Depot", refresh: "Aktualisieren", settings: "Verwalten",
    value: "Depotwert inkl. Cash", invested: "Eingezahltes Kapital", cash: "Verrechnungskonto",
    dividends: "Dividenden", history: "Wertentwicklung", ledger: "Buchungsverlauf", plans: "Sparpläne",
    all: "Gesamt", year: "1 Jahr", six: "6 Monate", three: "3 Monate", date: "Datum",
    type: "Buchung", symbol: "Wertpapier / Sparplan", amount: "Betrag", units: "Anteile",
    deposit: "Einzahlung", purchase: "Kauf", dividend: "Dividende", opening: "Anfangsbestand",
    estimate: "geschätzt", noWallet: "Noch kein Depot vorhanden. Lege My Wallet an oder importiere einen Verlauf.",
    noRows: "Für diese Auswahl sind keine Buchungen vorhanden.", loading: "Verlauf und historische Kurse werden geladen …",
    estimated: "Stückzahlen mit dem Hinweis „geschätzt“ beruhen auf Yahoo-Schlusskursen. Der Depotwert ist damit ebenfalls eine Näherung; die erfassten Zahlungsbeträge bleiben unverändert.",
    openingWarning: "Für Teile des Anfangsbestands fehlen Kaufdaten. Der historische Depotwert bleibt deshalb leer; Einzahlungen und Cash werden angezeigt.",
    openingConflict: "Anfangsbestand und enthaltene Kauftranchen passen nicht zusammen. Automatische Sparplanbuchungen sind pausiert; die historische Wertkurve bleibt leer. Prüfe unter „Verwalten“ den Anfangsbestand und die als enthalten markierten Kauftranchen anhand deiner Abrechnungen. Die gespeicherten Stückzahlen wurden nicht verändert.",
    configuredUnits: "Anfangsbestand", includedUnits: "als enthalten markierte Anteile",
    quotesWarning: "Bei fehlenden historischen Kursen oder Wechselkursen bleibt die Wertkurve an den betroffenen Tagen unterbrochen.",
    limited: "Die Kurve zeigt höchstens die letzten zehn Jahre. Der Buchungsverlauf enthält weiterhin alle Einträge.",
    closeHint: "Tageswerte anhand bestätigter Schlusskurse; heutiger Depotwert oben nach dem letzten Sensor-Update.",
    import: "Verlauf importieren", importHint: "Wähle eine My-Wallet-JSON-Datei. Der Import erstellt nach deiner Bestätigung ein eigenes Depot. Bestehende Depots bleiben unverändert. Die Datei bleibt in deiner Home-Assistant-Installation; an Yahoo gehen nur Symbol- und Kursanfragen.",
    preview: "Import prüfen", preparing: "Buchungen werden geprüft und fehlende Stückzahlen aus historischen Kursen geschätzt …",
    confirm: "Als neues Depot importieren", cancel: "Abbrechen", confirmCheck: "Ich habe die Vorschau geprüft und möchte dieses neue Depot anlegen.",
    missing: "Für diese Käufe ist kein geeigneter Kurs verfügbar. Trage die tatsächlichen Stückzahlen aus der Abrechnung ein und prüfe erneut. Bisher wurde nichts gespeichert.",
    counts: "Einzahlungen / Käufe / Dividenden", spending: "Kaufsumme", newWallet: "Neues Depot",
    unitsInput: "Tatsächliche Stückzahl", previewExpires: "Die Vorschau ist zehn Minuten gültig. Eine bereits importierte Datei wird nicht erneut gebucht.",
    enabled: "aktiv", disabled: "pausiert", ended: "beendet", from: "ab", until: "bis", monthly: "monatlich",
    export: "Buchungen als CSV", selectDate: "Tag im Verlauf auswählen", allTypes: "Alle Buchungen",
    pending: "Ausführungen warten auf Klärung. Details findest du beim Sensor „Nächste Ausführung“ und in den Sparplan-Optionen.",
    error: "Die Aktion konnte nicht abgeschlossen werden. Bitte erneut versuchen.",
    already_imported: "Diese Datei wurde bereits importiert. Es wurden keine weiteren Buchungen angelegt.",
    import_expired: "Die Vorschau ist abgelaufen. Bitte den Import erneut prüfen.",
    import_cash_conflict: "Die Zahlungsfolge würde zwischenzeitlich einen negativen Cash-Bestand erzeugen. Bitte Einzahlungstage, Kaufbeträge und Dividenden prüfen.",
    future_date: "Der Import enthält eine Einzahlung, einen Kauf oder eine Dividende in der Zukunft.",
    invalid_import: "Die Datei entspricht nicht dem My-Wallet-Importformat. Es wurde nichts gespeichert.",
    unauthorized: "Die Verlaufsansicht und der Import sind nur für Administratoren verfügbar.",
    emptyValue: "nicht verfügbar", priceDate: "Kursdatum", booked: "Buchungsdatum", dateUnknown: "ohne Datum",
  },
  en: {
    subtitle: "Portfolio history", wallet: "Wallet", refresh: "Refresh", settings: "Manage",
    value: "Portfolio including cash", invested: "Deposited capital", cash: "Settlement cash",
    dividends: "Dividends", history: "Value history", ledger: "Transaction history", plans: "Savings plans",
    all: "All", year: "1 year", six: "6 months", three: "3 months", date: "Date",
    type: "Transaction", symbol: "Asset / savings plan", amount: "Amount", units: "Units",
    deposit: "Deposit", purchase: "Purchase", dividend: "Dividend", opening: "Opening balance",
    estimate: "estimated", noWallet: "No wallet yet. Set up My Wallet or import a transaction history.",
    noRows: "No transactions match this selection.", loading: "Loading history and historical prices …",
    estimated: "Units marked estimated use Yahoo daily closes. Portfolio values are therefore approximate; recorded payment amounts are unchanged.",
    openingWarning: "Some opening holdings have no purchase dates. Historical portfolio values remain empty; deposits and cash are shown.",
    openingConflict: "Opening holdings and included purchase lots disagree. Automatic plan bookings are paused and the historical value curve remains empty. Use Manage to reconcile opening units and included purchase lots against your statements. Stored quantities were not changed.",
    configuredUnits: "opening units", includedUnits: "units marked included",
    quotesWarning: "Missing historical prices or exchange rates leave gaps in the value curve.",
    limited: "The chart shows up to ten years. The ledger still includes every transaction.",
    closeHint: "Daily values use confirmed closing prices. The current value above comes from the latest sensor update.",
    import: "Import history", importHint: "Choose a My Wallet JSON file. After confirmation, the import creates a separate wallet and leaves existing wallets untouched. The file stays in your Home Assistant installation; only symbol and price requests go to Yahoo.",
    preview: "Preview import", preparing: "Checking transactions and estimating missing units from historical prices …",
    confirm: "Import as a new wallet", cancel: "Cancel", confirmCheck: "I have reviewed the preview and want to create this new wallet.",
    missing: "No suitable price was available for these purchases. Enter the actual units from your trade confirmations and preview again. Nothing has been saved.",
    counts: "Deposits / purchases / dividends", spending: "Purchase total", newWallet: "New wallet",
    unitsInput: "Actual units", previewExpires: "The preview expires after ten minutes. A previously imported file cannot be booked again.",
    enabled: "active", disabled: "paused", ended: "ended", from: "from", until: "until", monthly: "monthly",
    export: "Export transactions as CSV", selectDate: "Select a history date", allTypes: "All transactions",
    pending: "Executions need attention. See the Next Execution sensor and savings-plan options for details.",
    error: "The action could not be completed. Please try again.",
    already_imported: "This file was already imported. No additional transactions were created.",
    import_expired: "The preview expired. Please prepare a new preview.",
    import_cash_conflict: "The payment sequence would create a negative cash balance. Check deposit dates, purchase amounts and dividends.",
    future_date: "The import includes a future deposit, purchase or dividend.",
    invalid_import: "The file does not match the My Wallet import format. Nothing was saved.",
    unauthorized: "The history panel and import require administrator access.",
    emptyValue: "unavailable", priceDate: "Price date", booked: "Booking date", dateUnknown: "undated",
  },
};

const CSS = `
  :host{display:block;height:100%;overflow:auto;color:var(--primary-text-color,#182b42);background:var(--primary-background-color,#f4f6f8);font:14px/1.5 var(--paper-font-body1_-_font-family,system-ui,sans-serif)}
  *{box-sizing:border-box} header{display:flex;align-items:center;gap:14px;padding:16px 24px;border-bottom:1px solid var(--divider-color,#dde3ea);background:var(--card-background-color,#fff)}
  h1{font-size:22px;line-height:1.2;margin:0}h2{font-size:18px;margin:0 0 16px}h3{font-size:15px;margin:12px 0 4px}p{margin:8px 0}.sub,.hint{color:var(--secondary-text-color,#57667a)}.hint{font-size:13px}.grow{flex:1}
  main{max-width:1320px;margin:auto;padding:24px} .toolbar,.controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:18px}
  button,select,input{font:inherit;color:inherit} button,.button{cursor:pointer;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#cad3dd);border-radius:8px;padding:9px 14px;text-decoration:none;color:inherit}
  button:disabled{opacity:.5;cursor:default}.primary,button.active{background:var(--primary-color,#1878b5);color:white;border-color:var(--primary-color,#1878b5)}button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible{outline:3px solid #de9d30;outline-offset:2px}
  select,input[type=number]{padding:9px;border:1px solid var(--divider-color,#cad3dd);border-radius:7px;background:var(--card-background-color,#fff)}select{max-width:100%}label{display:inline-flex;align-items:center;gap:7px}input[type=checkbox]{width:18px;height:18px;accent-color:var(--primary-color,#1878b5)}
  .stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:18px 0}.stat,.card{background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dce3eb);border-radius:12px;padding:20px}.stat strong{display:block;font-size:24px;letter-spacing:-.5px;margin-top:4px;font-variant-numeric:tabular-nums}.stat span{color:var(--secondary-text-color,#57667a);font-size:13px}.card{margin-bottom:18px}
  .notice{padding:12px 16px;background:color-mix(in srgb,var(--primary-color,#1878b5) 9%,var(--card-background-color,#fff));border-left:3px solid var(--primary-color,#1878b5);border-radius:5px;margin:12px 0}.warning{border-color:#c4851b;background:color-mix(in srgb,#e6ac37 12%,var(--card-background-color,#fff))}.error{border-color:#c63c45;background:color-mix(in srgb,#c63c45 9%,var(--card-background-color,#fff))}
  svg{display:block;width:100%;height:auto;touch-action:pan-y;overflow:visible}.chart{min-width:260px}.legend{display:flex;gap:18px;flex-wrap:wrap;margin-bottom:8px}.legend span:before{content:'';display:inline-block;width:18px;height:3px;vertical-align:middle;margin-right:6px;background:var(--line)}.tip{font-variant-numeric:tabular-nums;min-height:30px;margin:10px 0}.scrub{width:100%;accent-color:#157bc0}
  .tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid var(--divider-color,#e4e9ef);white-space:nowrap}th{font-size:12px;color:var(--secondary-text-color,#57667a)}th.num,td.num{text-align:right}td .hint{display:block;font-size:12px;max-width:500px;overflow:hidden;text-overflow:ellipsis}.badge{font-size:11px;border-radius:4px;padding:2px 5px;background:color-mix(in srgb,#dfaa34 17%,transparent);margin-left:6px}.positive{color:var(--success-color,#208461)}.planlist{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}.plan{padding:12px;border:1px solid var(--divider-color,#dce3eb);border-radius:8px}.plan h3{margin-top:0}
  .loading:before{content:'';display:inline-block;width:14px;height:14px;border:2px solid #9daec0;border-top-color:#1878b5;border-radius:50%;animation:spin .8s linear infinite;margin-right:9px;vertical-align:middle}@keyframes spin{to{transform:rotate(360deg)}}
  input[type=file]{max-width:100%;margin:12px 0} .missing-row{display:flex;align-items:center;gap:12px;justify-content:space-between;border-bottom:1px solid var(--divider-color,#e4e9ef);padding:10px 0}.missing-row input{width:155px}
  @media(max-width:700px){header{padding:12px}main{padding:14px}.stats{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.stat,.card{padding:14px}.stat strong{font-size:20px}h1{font-size:20px}.toolbar{gap:8px}.toolbar label{width:100%}.toolbar select{flex:1}.missing-row{align-items:flex-start;flex-direction:column}.controls{gap:8px}th,td{padding:10px 7px}}
  @media(prefers-reduced-motion:reduce){.loading:before{animation:none}}
`;

function node(tag, text, cls) {
  const result = document.createElement(tag);
  if (text != null) result.textContent = text;
  if (cls) result.className = cls;
  return result;
}
function button(text, action, cls) {
  const result = node("button", text, cls);
  result.type = "button";
  result.addEventListener("click", action);
  return result;
}
function svgNode(tag, attrs) {
  const result = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) result.setAttribute(key, String(value));
  return result;
}

class MyWalletPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._wallets = [];
    this._period = "all";
    this._type = "all";
    this._cashLine = false;
    this._busy = false;
    this._importOpen = false;
  }
  set hass(value) {
    this._hass = value;
    this._lang = (value.language || value.locale?.language || "en").startsWith("de") ? "de" : "en";
    if (this.isConnected && !this._started) this._start();
  }
  connectedCallback() { if (this._hass) this._start(); }
  disconnectedCallback() { clearInterval(this._timer); window.removeEventListener("resize", this._resize); this._started = false; }
  _start() {
    if (this._started) return;
    this._started = true;
    this._resize = () => { if (this._history && !this._busy && !this._importOpen) this._render(); };
    window.addEventListener("resize", this._resize);
    this._refresh();
    this._timer = setInterval(() => {
      if (!this._busy && !this._importOpen && document.visibilityState !== "hidden") this._refresh(true);
    }, 60000);
  }
  t(key) { return WORDS[this._lang || "en"][key] || WORDS.en[key] || key; }
  money(value, currency = this._wallet()?.currency || "EUR") {
    return value == null ? "—" : new Intl.NumberFormat(this._lang, { style: "currency", currency }).format(value);
  }
  day(value) { return value ? new Intl.DateTimeFormat(this._lang, { day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date(`${value}T12:00:00`)) : this.t("dateUnknown"); }
  _wallet() { return this._wallets.find(wallet => wallet.entry_id === this._selected); }
  _call(type, data = {}) { return this._hass.callWS({ type: `my_wallet/${type}`, ...data }); }
  _errorText(err) {
    const code = err?.code || "error";
    if (WORDS.en[code]) return this.t(code);
    if (code.startsWith("invalid_") || code.includes("import_items")) return this.t("invalid_import");
    return this.t("error");
  }
  async _refresh(quiet = false) {
    if (this._busy) return;
    this._busy = true;
    this._error = null;
    if (!quiet) this._render();
    try {
      const result = await this._call("wallets");
      this._wallets = result.wallets;
      if (!this._wallet()) this._selected = this._wallets[0]?.entry_id;
      this._history = this._selected ? await this._call("history", { entry_id: this._selected }) : null;
    } catch (err) { this._error = this._errorText(err); }
    finally { this._busy = false; this._render(); }
  }
  _notice(parent, text, kind = "") { parent.append(node("p", text, `notice ${kind}`)); }
  _stat(parent, label, value) {
    const card = node("div", null, "stat");
    card.append(node("span", label), node("strong", value));
    parent.append(card);
  }
  _render() {
    const root = this.shadowRoot;
    root.replaceChildren(node("style", CSS));
    const header = node("header");
    const menu = node("ha-menu-button");
    menu.hass = this._hass;
    menu.narrow = this.narrow;
    const heading = node("div");
    heading.append(node("h1", "My Wallet"), node("div", this.t("subtitle"), "sub"));
    header.append(menu, heading);
    root.append(header);
    const main = node("main");
    root.append(main);
    const toolbar = node("div", null, "toolbar");
    const selectLabel = node("label", this.t("wallet"));
    const select = node("select");
    for (const wallet of this._wallets) {
      const option = node("option", wallet.name);
      option.value = wallet.entry_id;
      option.selected = wallet.entry_id === this._selected;
      select.append(option);
    }
    select.disabled = this._busy || !this._wallets.length;
    select.addEventListener("change", () => { this._selected = select.value; this._history = null; this._refresh(); });
    selectLabel.append(select);
    const refresh = button(this.t("refresh"), () => this._refresh());
    refresh.disabled = this._busy;
    const settings = node("a", this.t("settings"), "button");
    settings.href = "/config/integrations/integration/my_wallet";
    const importButton = button(this.t("import"), () => { this._importOpen = !this._importOpen; this._render(); });
    importButton.disabled = this._busy;
    toolbar.append(selectLabel, node("div", null, "grow"), refresh, settings, importButton);
    main.append(toolbar);
    if (this._error) this._notice(main, this._error, "error");
    if (this._busy) this._notice(main, this.t(this._importBusy ? "preparing" : "loading"), "loading");
    if (this._importOpen) this._renderImport(main);
    const wallet = this._wallet();
    if (!wallet) { this._notice(main, this.t("noWallet")); return; }
    if (wallet.opening_conflicts?.length) {
      const warning = node("div", null, "notice warning");
      warning.setAttribute("role", "alert");
      warning.append(node("p", this.t("openingConflict")));
      const list = node("ul");
      const number = new Intl.NumberFormat(this._lang, { maximumFractionDigits: 12 });
      for (const item of wallet.opening_conflicts) list.append(node("li", `${item.symbol}: ${this.t("configuredUnits")} ${number.format(item.configured_units)}; ${this.t("includedUnits")} ${number.format(item.included_units)}`));
      warning.append(list);
      main.append(warning);
    }
    const stats = node("div", null, "stats");
    for (const [key, value] of [["value", wallet.total], ["invested", wallet.invested], ["cash", wallet.cash], ["dividends", wallet.dividends]]) this._stat(stats, this.t(key), this.money(value));
    main.append(stats);
    if (wallet.pending?.length) this._notice(main, this.t("pending"), "warning");
    if (this._history) {
      if (this._history.estimated) this._notice(main, this.t("estimated"));
      if (this._history.unknown_opening.length) this._notice(main, this.t("openingWarning"), "warning");
      if (this._history.missing_history.length) this._notice(main, this.t("quotesWarning"), "warning");
      if (this._history.range_limited) this._notice(main, this.t("limited"));
      this._renderChart(main);
      this._renderPlans(main, wallet.plans, wallet.currency);
      this._renderLedger(main);
    }
  }
  _renderPlans(parent, plans, currency) {
    if (!plans?.length) return;
    const card = node("section", null, "card");
    card.append(node("h2", this.t("plans")));
    const list = node("div", null, "planlist");
    const today = new Date().toLocaleDateString("sv-SE");
    for (const plan of plans) {
      const item = node("article", null, "plan");
      item.append(node("h3", plan.name));
      const status = !plan.enabled ? "disabled" : plan.end_date && plan.end_date < today ? "ended" : "enabled";
      item.append(node("div", `${this.money(plan.amount, currency)} ${this.t("monthly")} · ${this.t(status)}`));
      item.append(node("div", `${this.t("from")} ${this.day(plan.first_date)}${plan.end_date ? ` · ${this.t("until")} ${this.day(plan.end_date)}` : ""}`, "hint"));
      for (const row of plan.allocations) item.append(node("div", `${row.symbol}: ${plan.allocation_mode === "percentage" ? `${row.value} %` : this.money(row.value, currency)}`, "hint"));
      list.append(item);
    }
    card.append(list);
    parent.append(card);
  }
  _renderChart(parent) {
    const section = node("section", null, "card chart");
    section.append(node("h2", this.t("history")));
    const controls = node("div", null, "controls");
    for (const key of ["all", "year", "six", "three"]) controls.append(button(this.t(key), () => { this._period = key; this._render(); }, this._period === key ? "active" : ""));
    const cashLabel = node("label", this.t("cash"));
    const cashCheck = node("input");
    cashCheck.type = "checkbox";
    cashCheck.checked = this._cashLine;
    cashCheck.addEventListener("change", () => { this._cashLine = cashCheck.checked; this._render(); });
    cashLabel.prepend(cashCheck);
    controls.append(cashLabel);
    section.append(controls);
    const limit = { year: 366, six: 184, three: 93 }[this._period];
    const points = limit ? this._history.points.slice(-limit) : this._history.points;
    const keys = ["value", "invested", ...(this._cashLine ? ["cash"] : [])];
    const colors = { value: "#157bc0", invested: "#269e81", cash: "#c48925" };
    const legend = node("div", null, "legend");
    for (const key of keys) { const item = node("span", this.t(key)); item.style.setProperty("--line", colors[key]); legend.append(item); }
    section.append(legend);
    if (!points.length) { this._notice(section, this.t("noRows")); parent.append(section); return; }
    const width = Math.max(300, Math.min(1000, this.clientWidth - 56));
    const height = width < 500 ? 280 : 330, left = width < 500 ? 56 : 82, top = 16, bottom = height - 40, right = width - 16;
    const values = points.flatMap(point => keys.map(key => point[key])).filter(Number.isFinite);
    let low = Math.min(0, ...values), high = Math.max(1, ...values);
    high += (high - low) * 0.08;
    const x = index => left + index / Math.max(1, points.length - 1) * (right - left);
    const y = value => bottom - (value - low) / (high - low) * (bottom - top);
    const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": this.t("history") });
    for (let i = 0; i <= 4; i++) {
      const value = low + (high - low) * i / 4;
      svg.append(svgNode("line", { x1: left, x2: right, y1: y(value), y2: y(value), stroke: "var(--divider-color,#e0e6ed)", "stroke-width": 1 }));
      const label = svgNode("text", { x: left - 12, y: y(value) + 4, fill: "var(--secondary-text-color,#57667a)", "font-size": 12, "text-anchor": "end" });
      label.textContent = new Intl.NumberFormat(this._lang, { maximumFractionDigits: 0 }).format(value);
      svg.append(label);
    }
    for (const index of [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])]) {
      const label = svgNode("text", { x: x(index), y: bottom + 26, fill: "var(--secondary-text-color,#57667a)", "font-size": 12, "text-anchor": index === 0 ? "start" : index === points.length - 1 ? "end" : "middle" });
      label.textContent = this.day(points[index].date);
      svg.append(label);
    }
    for (const key of keys) {
      let path = "", active = false;
      points.forEach((point, index) => {
        if (!Number.isFinite(point[key])) { active = false; return; }
        path += !active ? `M${x(index)} ${y(point[key])}` : key === "invested" ? `H${x(index)}V${y(point[key])}` : `L${x(index)} ${y(point[key])}`;
        active = true;
      });
      svg.append(svgNode("path", { d: path, fill: "none", stroke: colors[key], "stroke-width": 2.5, "stroke-linejoin": "round", "vector-effect": "non-scaling-stroke" }));
    }
    const cursor = svgNode("line", { x1: right, x2: right, y1: top, y2: bottom, stroke: "var(--secondary-text-color,#66788a)", "stroke-dasharray": "4 5" });
    svg.append(cursor);
    const output = node("output", null, "tip");
    const scrub = node("input", null, "scrub");
    scrub.type = "range"; scrub.min = "0"; scrub.max = String(points.length - 1); scrub.value = scrub.max;
    scrub.setAttribute("aria-label", this.t("selectDate"));
    const show = index => {
      const point = points[index];
      output.textContent = `${this.day(point.date)} · ${keys.map(key => `${this.t(key)}: ${this.money(point[key])}`).join(" · ")}`;
      cursor.setAttribute("x1", x(index)); cursor.setAttribute("x2", x(index)); scrub.value = String(index);
    };
    scrub.addEventListener("input", () => show(Number(scrub.value)));
    svg.addEventListener("pointermove", event => {
      const rectangle = svg.getBoundingClientRect();
      const fraction = ((event.clientX - rectangle.left) / rectangle.width * width - left) / (right - left);
      show(Math.max(0, Math.min(points.length - 1, Math.round(fraction * (points.length - 1)))));
    });
    show(points.length - 1);
    section.append(svg, output, scrub, node("p", this.t("closeHint"), "hint"));
    parent.append(section);
  }
  _renderLedger(parent) {
    const section = node("section", null, "card");
    const controls = node("div", null, "controls");
    controls.append(node("h2", this.t("ledger")), node("div", null, "grow"));
    const filter = node("select");
    filter.setAttribute("aria-label", this.t("type"));
    for (const key of ["all", "deposit", "purchase", "dividend", "opening"]) {
      const option = node("option", this.t(key === "all" ? "allTypes" : key));
      option.value = key; option.selected = this._type === key; filter.append(option);
    }
    filter.addEventListener("change", () => { this._type = filter.value; this._render(); });
    controls.append(filter, button(this.t("export"), () => this._export()));
    section.append(controls);
    const wrap = node("div", null, "tablewrap"), table = node("table"), head = node("thead"), hr = node("tr");
    for (const key of ["date", "type", "symbol", "amount", "units"]) hr.append(node("th", this.t(key), ["amount", "units"].includes(key) ? "num" : ""));
    head.append(hr); table.append(head);
    const body = node("tbody");
    const rows = [...this._history.ledger].reverse().filter(row => this._type === "all" || row.type === this._type);
    for (const row of rows) {
      const tr = node("tr"), dateCell = node("td", this.day(row.date));
      if (row.booking_date && row.booking_date !== row.date) dateCell.append(node("span", `${this.t("booked")}: ${this.day(row.booking_date)}`, "hint"));
      const asset = node("td", row.symbol || row.plan || "—");
      if (row.symbol && row.plan) asset.append(node("span", row.plan, "hint"));
      if (row.note) asset.append(node("span", row.note, "hint"));
      const units = node("td", row.units == null ? "—" : new Intl.NumberFormat(this._lang, { maximumFractionDigits: 6 }).format(row.units), "num");
      if (row.estimated) units.append(node("span", this.t("estimate"), "badge"));
      if (row.price_date && row.price_date !== row.date) units.append(node("span", `${this.t("priceDate")}: ${this.day(row.price_date)}`, "hint"));
      tr.append(dateCell, node("td", this.t(row.type)), asset, node("td", this.money(row.amount), `num ${row.amount > 0 ? "positive" : ""}`), units);
      body.append(tr);
    }
    table.append(body); wrap.append(table); section.append(wrap);
    if (!rows.length) this._notice(section, this.t("noRows"));
    parent.append(section);
  }
  _export() {
    const cell = value => {
      let text = String(value ?? "");
      if (typeof value === "string" && /^[=+\-@\t\r]/.test(text)) text = `'${text}`;
      return `"${text.replaceAll('"', '""')}"`;
    };
    const rows = [["date", "type", "symbol", "plan", "amount", "currency", "units", "estimated", "price_date", "note"], ...this._history.ledger.map(row => [row.date, row.type, row.symbol, row.plan, row.amount, this._wallet().currency, row.units, row.estimated ?? false, row.price_date, row.note])];
    const blob = new Blob(["\uFEFF" + rows.map(row => row.map(cell).join(";")).join("\r\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob), anchor = node("a");
    anchor.href = url; anchor.download = "my-wallet-history.csv"; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  _renderImport(parent) {
    const section = node("section", null, "card");
    section.append(node("h2", this.t("import")), node("p", this.t("importHint"), "hint"));
    const file = node("input");
    file.type = "file"; file.accept = ".json,application/json"; file.disabled = this._busy;
    file.setAttribute("aria-label", this.t("import"));
    file.addEventListener("change", async () => {
      const selected = file.files[0];
      if (!selected) return;
      try {
        if (selected.size > 2000000) throw new Error("size");
        this._document = JSON.parse(await selected.text());
        this._preview = null;
        await this._prepareImport();
      } catch { this._error = this.t("invalid_import"); this._render(); }
    });
    section.append(file);
    if (this._preview) {
      const summary = this._preview.summary;
      section.append(node("h3", `${this.t("newWallet")}: ${summary.wallet_name}`));
      section.append(node("p", `${this.t("counts")}: ${summary.deposits} / ${summary.purchases} / ${summary.dividends}`));
      const stats = node("div", null, "stats");
      for (const [key, value] of [["invested", summary.capital], ["spending", summary.spending], ["dividends", summary.dividend_total], ["cash", summary.cash]]) this._stat(stats, this.t(key), this.money(value, summary.currency));
      section.append(stats);
      if (summary.estimated) this._notice(section, this.t("estimated"));
      this._renderPlans(section, summary.plans, summary.currency);
      if (summary.missing.length) {
        this._notice(section, this.t("missing"), "warning");
        for (const row of summary.missing) {
          const wrapper = node("label", null, "missing-row");
          wrapper.append(node("span", `${this.day(row.date)} · ${row.symbol} · ${this.money(row.amount, summary.currency)}`));
          const input = node("input");
          input.type = "number"; input.min = "0.000000001"; input.step = "any"; input.placeholder = this.t("unitsInput");
          input.setAttribute("aria-label", `${row.symbol} ${this.day(row.date)}: ${this.t("unitsInput")}`);
          const item = this._document.deposits.flatMap(deposit => deposit.purchases || []).find(purchase => purchase.id === row.id);
          if (item.units != null) input.value = String(item.units);
          input.addEventListener("input", () => { if (input.value && Number(input.value) > 0) item.units = Number(input.value); else delete item.units; });
          wrapper.append(input); section.append(wrapper);
        }
      } else {
        section.append(node("p", this.t("previewExpires"), "hint"));
        const label = node("label", this.t("confirmCheck")), check = node("input");
        check.type = "checkbox";
        label.prepend(check); section.append(label);
        const confirm = button(this.t("confirm"), () => this._commitImport(), "primary");
        confirm.disabled = true;
        check.addEventListener("change", () => { confirm.disabled = !check.checked || this._busy; });
        const actions = node("div", null, "controls");
        actions.append(confirm); section.append(actions);
      }
    }
    const actions = node("div", null, "controls");
    if (this._document) { const preview = button(this.t("preview"), () => this._prepareImport()); preview.disabled = this._busy; actions.append(preview); }
    const cancel = button(this.t("cancel"), () => { this._document = null; this._preview = null; this._importOpen = false; this._error = null; this._render(); });
    cancel.disabled = this._busy; actions.append(cancel); section.append(actions);
    parent.append(section);
  }
  async _prepareImport() {
    if (this._busy) return;
    this._busy = this._importBusy = true; this._error = null; this._preview = null; this._render();
    try { this._preview = await this._call("import_preview", { document: this._document }); }
    catch (err) { this._error = this._errorText(err); }
    finally { this._busy = this._importBusy = false; this._render(); }
  }
  async _commitImport() {
    if (this._busy || !this._preview?.token) return;
    this._busy = this._importBusy = true; this._error = null; this._render();
    try {
      const result = await this._call("import_commit", { token: this._preview.token, confirm: true });
      this._selected = result.entry_id; this._document = this._preview = null; this._importOpen = false;
    } catch (err) { this._error = this._errorText(err); }
    finally { this._busy = this._importBusy = false; this._render(); }
    if (!this._importOpen) await this._refresh();
  }
}

if (!customElements.get("my-wallet-panel")) customElements.define("my-wallet-panel", MyWalletPanel);
