/* My Wallet: local-only UI. Financial data comes from authenticated HA WebSocket calls. */
import { axisLabels, currencyScale } from "./chart-scales.mjs?v=1.7.0";
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
    closeHint: "Reale Tageswerte beruhen auf bestätigten Schlusskursen; der heutige Depotwert oben stammt vom letzten Sensor-Update. Die gestrichelte Sollkurve verwendet die eingestellte Rendite und geplanten Sparraten.",
    import: "Verlauf importieren", importHint: "Wähle eine My-Wallet-JSON-Datei. Der Import erstellt nach deiner Bestätigung ein eigenes Depot. Bestehende Depots bleiben unverändert. Die Datei bleibt in deiner Home-Assistant-Installation; an Yahoo gehen nur Symbol- und Kursanfragen.",
    preview: "Import prüfen", preparing: "Buchungen werden geprüft und fehlende Stückzahlen aus historischen Kursen geschätzt …",
    confirm: "Als neues Depot importieren", cancel: "Abbrechen", confirmCheck: "Ich habe die Vorschau geprüft und möchte dieses neue Depot anlegen.",
    missing: "Für diese Käufe ist kein geeigneter Kurs verfügbar. Trage die tatsächlichen Stückzahlen aus der Abrechnung ein und prüfe erneut. Bisher wurde nichts gespeichert.",
    counts: "Einzahlungen / Käufe / Dividenden", spending: "Kaufsumme", newWallet: "Neues Depot",
    unitsInput: "Tatsächliche Stückzahl", previewExpires: "Die Vorschau ist zehn Minuten gültig. Eine bereits importierte Datei wird nicht erneut gebucht.",
    enabled: "aktiv", disabled: "pausiert", ended: "beendet", from: "ab", until: "bis", monthly: "monatlich",
    export: "Buchungen als CSV", selectDate: "Tag im Verlauf auswählen", allTypes: "Alle Buchungen",
    cashChart: "Verrechnungskonto separat anzeigen", cashScale: "Eigene Skala; derselbe Zeitraum wie oben",
    hideHint: "Hinweis ausblenden", showHint: "Hinweis zu geschätzten Anteilen anzeigen",
    performance: "Performance", profit: "Gewinn / Verlust", annualReturn: "Geldgewichtete Rendite p. a.",
    targetComparison: "Soll-Ist-Vergleich", expectedReturn: "Vorgaberendite p. a.", targetValue: "Zinseszins-Sollwert",
    targetDeviation: "Abweichung zum Soll", targetLine: "Sollkurve anzeigen", forecast: "Prognosehorizont",
    forecastToday: "heute", forecastYear: "Jahr", forecastYears: "Jahre", forecastCustom: "Benutzerdefiniert", forecastCustomYears: "Jahre (1–50)", apply: "Anwenden", perYear: "p. a.", forecastValue: "Prognostizierter Sollwert", forecastDate: "Prognosedatum",
    targetContributions: "Einzahlungen bis dahin", futureContributions: "Davon ab heute geplant", targetGrowth: "Erwarteter Wertzuwachs", currentTargetDeviation: "Aktuelle Abweichung zum Soll", portfolioForecast: "Depotprognose", forecastInvested: "Einzahlungen inkl. Planung",
    targetHint: "Die Einzahlungen kombinieren gebuchte Einmalzahlungen mit den jeweils vorgesehenen Sparraten. Der erwartete Wertzuwachs ist der Sollwert abzüglich dieser Einzahlungen.",
    targetUnavailable: "Der Sollwert ist nicht verfügbar, weil Depotstart oder Anfangsbestand nicht vollständig dokumentiert sind.",
    positions: "Positionen", position: "Position", allPositions: "Gesamtes Depot", currentPrice: "Aktueller Kurs",
    analysis: "Kennzahlen und Verlauf", analysisFor: "Auswahl", analysisHint: "Kennzahlen, Wertentwicklung, Monats-/Jahresübersicht und Buchungen folgen dieser Auswahl.",
    editAliases: "Namen bearbeiten", positionNames: "Anzeigenamen", aliasHint: "Vergib kurze, verständliche Namen. Das technische Kürzel bleibt zur eindeutigen Zuordnung sichtbar.",
    aliasPlaceholder: "z. B. Welt-ETF", saveAliases: "Namen speichern", invalid_alias: "Der Anzeigename ist ungültig oder länger als 80 Zeichen.",
    currentValue: "Aktueller Wert", purchaseCost: "Kaufbetrag", share: "Depotanteil", target: "Zielanteil",
    portfolioStart: "Depotstart", positionStart: "Positionsstart", allocation: "Depotaufteilung", forecastAllocation: "Prognostizierte Depotaufteilung", projectedValue: "Prognosewert",
    allocationHint: "Aktuelle Verteilung inklusive Verrechnungskonto; Zielanteile gelten nur für Wertpapiere.", forecastAllocationHint: "Mathematische Hochrechnung aus den heutigen Werten, der Vorgaberendite und den bis dahin geplanten Sparplan-Zuteilungen – keine Prognose einzelner Wertpapierkurse.", actualShare: "Ist-Anteil", forecastShare: "Prognose-Anteil", deviation: "Abweichung",
    purchaseLots: "Kauftranchen", purchasePrice: "Einstandskurs", annualizedPerformance: "Rendite p. a.",
    includedOpening: "im Anfangsbestand", lotDetailsHint: "Dividenden werden den am Auszahlungstag gehaltenen Kauftranchen anteilig zugerechnet.",
    noLots: "Für diese Position sind keine vollständig dokumentierten Kauftranchen vorhanden.",
    incompleteCost: "Kaufdaten unvollständig", correctUnits: "Anteile korrigieren", correction: "Anteilskorrektur",
    correctionHint: "Wähle den Anfangsbestand oder einen konkreten Kauf als Ursache der Abweichung. Zahlungsbetrag, Cash-Bestand und Einzahlungen ändern sich nicht.",
    correctionTarget: "Zu korrigierender Bestand", openingUnits: "Anfangsbestand", chosenLot: "Ausgewählter Kauf",
    totalPosition: "Gesamtbestand angleichen", onlyLot: "Nur diesen Bestand korrigieren", exactTotal: "Exakter Gesamtbestand",
    exactLot: "Exakte Anteile", reason: "Notiz (optional)", correctionPreview: "Korrektur prüfen",
    correctionConfirm: "Diese Stückzahl speichern", correctionCheck: "Ich habe Vorher und Nachher geprüft.",
    before: "Vorher", after: "Nachher", unchangedPayments: "Einzahlungen und Kaufbeträge bleiben unverändert.",
    correction_unchanged: "Die neue Stückzahl entspricht bereits dem gespeicherten Wert.",
    correction_negative_units: "Die Korrektur würde einen negativen oder leeren Kaufbestand erzeugen.",
    invalid_correction: "Die Anteilskorrektur ist ungültig. Es wurde nichts gespeichert.",
    entry_changed: "Das Depot wurde zwischenzeitlich geändert. Bitte die Vorschau neu erstellen.",
    overview: "Übersicht", navOverview: "Übersicht", navPositions: "Positionen", navHistory: "Verlauf", navData: "Buchungen & Daten", monthlyOverview: "Monate", yearlyOverview: "Jahre", period: "Zeitraum",
    endValue: "Endwert", returnLabel: "Rendite", summaryHint: "Renditen werden aus den Tageswerten nach Zu- und Abflüssen verkettet. Bei fehlenden Kursen oder einem unbekannten Anfangswert bleibt das Ergebnis leer.",
    positionValue: "Positionswert", followup: "Bestehendes Depot abgleichen", createNew: "Neues Depot erstellen", depositsLabel: "Einzahlungen",
    importMode: "Importziel", followupHint: "Der Folgeimport wird zuerst mit dem gewählten Depot abgeglichen. Bereits vorhandene Buchungen werden nicht doppelt angelegt; geschützte Abweichungen benötigen deine Entscheidung.",
    followupConfirm: "Abgleich in dieses Depot übernehmen", followupCheck: "Ich habe neue, unveränderte und abweichende Buchungen geprüft.",
    added: "Neu", updated: "Aktualisiert", unchanged: "Bereits vorhanden", protected: "Geschützt",
    depositsPlural: "Einzahlungen", purchasesPlural: "Käufe",
    assets: "Wertpapiere", decisions: "Abweichungen entscheiden", keepExisting: "Vorhandene Buchung behalten",
    dataExport: "Datenexport", dataExportHint: "CSV enthält die Buchungen zur Auswertung. Die JSON-Sicherung enthält die vollständige Depotkonfiguration und kann über „Verlauf importieren“ als neues Depot wiederhergestellt werden.",
    exportCsv: "Buchungen als CSV", exportBackup: "Vollständige JSON-Sicherung", backupRestore: "Sicherung als neues Depot wiederherstellen",
    backupImportHint: "Die Sicherung wird geprüft und anschließend als eigenständiges neues Depot wiederhergestellt. Das bestehende Depot bleibt unverändert.",
    backupCheck: "Ich habe die Sicherung geprüft und möchte daraus ein neues Depot anlegen.", backup_new_only: "Eine Sicherung kann nur als neues Depot wiederhergestellt werden.",
    invalid_backup: "Die Datei ist keine gültige My-Wallet-Sicherung. Es wurde nichts gespeichert.", backup_too_large: "Die Sicherung überschreitet 2 MB.",
    mergeIncoming: "Neue Angaben ausdrücklich übernehmen", addSeparate: "Als eigene Buchung hinzufügen",
    chooseMatch: "Passende vorhandene Buchung", import_currency_mismatch: "Die Währung der Datei passt nicht zu diesem Depot.",
    ambiguous_import_plan: "Ein Sparplan der Datei lässt sich nicht eindeutig zuordnen.",
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
    closeHint: "Actual daily values use confirmed closes; the current value above comes from the latest sensor update. The dashed target uses the configured return and planned savings rates.",
    import: "Import history", importHint: "Choose a My Wallet JSON file. After confirmation, the import creates a separate wallet and leaves existing wallets untouched. The file stays in your Home Assistant installation; only symbol and price requests go to Yahoo.",
    preview: "Preview import", preparing: "Checking transactions and estimating missing units from historical prices …",
    confirm: "Import as a new wallet", cancel: "Cancel", confirmCheck: "I have reviewed the preview and want to create this new wallet.",
    missing: "No suitable price was available for these purchases. Enter the actual units from your trade confirmations and preview again. Nothing has been saved.",
    counts: "Deposits / purchases / dividends", spending: "Purchase total", newWallet: "New wallet",
    unitsInput: "Actual units", previewExpires: "The preview expires after ten minutes. A previously imported file cannot be booked again.",
    enabled: "active", disabled: "paused", ended: "ended", from: "from", until: "until", monthly: "monthly",
    export: "Export transactions as CSV", selectDate: "Select a history date", allTypes: "All transactions",
    cashChart: "Show settlement cash separately", cashScale: "Independent scale; the same dates as above",
    hideHint: "Hide notice", showHint: "Show notice about estimated units",
    performance: "Performance", profit: "Gain / loss", annualReturn: "Money-weighted return p.a.",
    targetComparison: "Target comparison", expectedReturn: "Expected return p.a.", targetValue: "Compound target",
    targetDeviation: "Difference from target", targetLine: "Show target curve", forecast: "Forecast horizon",
    forecastToday: "today", forecastYear: "year", forecastYears: "years", forecastCustom: "Custom", forecastCustomYears: "Years (1–50)", apply: "Apply", perYear: "p.a.", forecastValue: "Forecast target", forecastDate: "Forecast date",
    targetContributions: "Contributions through this date", futureContributions: "Planned from today", targetGrowth: "Expected growth", currentTargetDeviation: "Current difference from target", portfolioForecast: "Portfolio forecast", forecastInvested: "Contributions including plan",
    targetHint: "Contributions combine booked one-off deposits with the applicable planned savings rates. Expected growth is the target value minus those contributions.",
    targetUnavailable: "The target is unavailable because the portfolio start or opening holdings are not fully documented.",
    positions: "Positions", position: "Position", allPositions: "Whole wallet", currentPrice: "Current price",
    analysis: "Metrics and history", analysisFor: "Selection", analysisHint: "Metrics, value history, monthly/yearly summaries and transactions follow this selection.",
    editAliases: "Edit names", positionNames: "Display names", aliasHint: "Add short, recognizable names. The technical symbol remains visible for unambiguous identification.",
    aliasPlaceholder: "e.g. World ETF", saveAliases: "Save names", invalid_alias: "The display name is invalid or longer than 80 characters.",
    currentValue: "Current value", purchaseCost: "Purchase cost", share: "Wallet share", target: "Target share",
    portfolioStart: "Portfolio start", positionStart: "Position start", allocation: "Portfolio allocation", forecastAllocation: "Projected portfolio allocation", projectedValue: "Projected value",
    allocationHint: "Current allocation including settlement cash; target shares apply to securities only.", forecastAllocationHint: "Mathematical projection from today's values, the expected return and scheduled savings-plan allocations through the selected date; it is not a forecast of individual security prices.", actualShare: "Actual share", forecastShare: "Projected share", deviation: "Deviation",
    purchaseLots: "Purchase lots", purchasePrice: "Entry price", annualizedPerformance: "Return p.a.",
    includedOpening: "included in opening balance", lotDetailsHint: "Dividends are attributed proportionally to purchase lots held on the payment date.",
    noLots: "No fully documented purchase lots are available for this position.",
    incompleteCost: "Incomplete purchase data", correctUnits: "Correct units", correction: "Unit correction",
    correctionHint: "Choose the opening holding or a specific purchase that explains the difference. Payment amount, cash and deposits do not change.",
    correctionTarget: "Holding to correct", openingUnits: "Opening holding", chosenLot: "Selected purchase",
    totalPosition: "Reconcile total position", onlyLot: "Correct only this holding", exactTotal: "Exact total position",
    exactLot: "Exact units", reason: "Note (optional)", correctionPreview: "Preview correction",
    correctionConfirm: "Save these units", correctionCheck: "I have checked the before and after values.",
    before: "Before", after: "After", unchangedPayments: "Deposits and purchase amounts remain unchanged.",
    correction_unchanged: "The new units already match the stored value.",
    correction_negative_units: "The correction would create a negative or empty purchase holding.",
    invalid_correction: "The unit correction is invalid. Nothing was saved.",
    entry_changed: "The wallet changed in the meantime. Prepare a fresh preview.",
    overview: "Overview", navOverview: "Overview", navPositions: "Positions", navHistory: "History", navData: "Transactions & data", monthlyOverview: "Months", yearlyOverview: "Years", period: "Period",
    endValue: "End value", returnLabel: "Return", summaryHint: "Returns link daily values after cash flows. Missing quotes or an unknown opening value leave the result unavailable.",
    positionValue: "Position value", followup: "Reconcile existing wallet", createNew: "Create new wallet", depositsLabel: "Deposits",
    importMode: "Import target", followupHint: "The follow-up import is reconciled with the selected wallet first. Existing transactions are not duplicated; protected differences require your decision.",
    followupConfirm: "Apply reconciliation to this wallet", followupCheck: "I have reviewed new, unchanged and differing transactions.",
    added: "New", updated: "Updated", unchanged: "Already present", protected: "Protected",
    depositsPlural: "Deposits", purchasesPlural: "Purchases",
    assets: "Assets", decisions: "Resolve differences", keepExisting: "Keep existing transaction",
    dataExport: "Data export", dataExportHint: "CSV contains transactions for analysis. The JSON backup contains the complete wallet configuration and can be restored as a new wallet through Import history.",
    exportCsv: "Export transactions as CSV", exportBackup: "Complete JSON backup", backupRestore: "Restore backup as a new wallet",
    backupImportHint: "The backup is validated and then restored as a separate new wallet. The existing wallet remains unchanged.",
    backupCheck: "I have reviewed the backup and want to create a new wallet from it.", backup_new_only: "A backup can only be restored as a new wallet.",
    invalid_backup: "This is not a valid My Wallet backup. Nothing was saved.", backup_too_large: "The backup exceeds 2 MB.",
    mergeIncoming: "Explicitly apply incoming details", addSeparate: "Add as a separate transaction",
    chooseMatch: "Matching existing transaction", import_currency_mismatch: "The file currency does not match this wallet.",
    ambiguous_import_plan: "A savings plan in the file cannot be matched unambiguously.",
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
  .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:14px;margin:18px 0}.target-stats{grid-template-columns:repeat(3,minmax(0,1fr))}.overview-stats{grid-template-columns:repeat(8,minmax(0,1fr))}.overview-stats .stat{padding:16px}.overview-stats .stat strong{font-size:21px;white-space:nowrap}.stat,.card{background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dce3eb);border-radius:12px;padding:20px}.stat{display:flex;flex-direction:column}.stat strong{display:block;font-size:24px;letter-spacing:-.5px;margin-top:4px;font-variant-numeric:tabular-nums}.stat>span{display:block;min-height:3em;color:var(--secondary-text-color,#57667a);font-size:13px}.card{margin-bottom:18px}
  .selection-card{display:flex;align-items:center;gap:24px}.selection-card h2{margin:0}.selection-copy{min-width:0}.selection-copy p{margin:4px 0 0}.selection-control{display:grid;gap:5px;min-width:min(100%,300px)}.selection-control span{font-size:13px;color:var(--secondary-text-color,#57667a)}
  .tabs{display:flex;gap:8px;overflow-x:auto;margin:0 0 18px;padding:4px 0}.tabs button{white-space:nowrap}.tabs button[aria-selected=true]{background:var(--primary-color,#1878b5);color:#fff;border-color:var(--primary-color,#1878b5)}.forecast-custom{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.forecast-custom input{width:125px}
  .alias-editor{margin:0 0 18px;padding:14px;border:1px solid var(--divider-color,#dce3eb);border-radius:9px;background:color-mix(in srgb,var(--primary-color,#1878b5) 4%,var(--card-background-color,#fff))}.alias-editor h3{margin:0}.alias-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px 18px;margin:12px 0}.alias-row{display:grid;grid-template-columns:minmax(90px,auto) minmax(120px,1fr);align-items:center;gap:10px}.alias-row input{width:100%;padding:9px;border:1px solid var(--divider-color,#cad3dd);border-radius:7px;background:var(--card-background-color,#fff)}tr.selected td{background:color-mix(in srgb,var(--primary-color,#1878b5) 8%,transparent)}
  .allocation-layout{display:grid;grid-template-columns:minmax(220px,300px) minmax(0,1fr);align-items:center;gap:24px}.donut{width:min(100%,280px);margin:auto}.allocation-name{display:inline-flex;align-items:center;gap:8px}.swatch{display:inline-block;width:11px;height:11px;border-radius:3px;flex:0 0 auto}.details-title{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}.details-title .hint{font-weight:400}
  .notice{padding:12px 16px;background:color-mix(in srgb,var(--primary-color,#1878b5) 9%,var(--card-background-color,#fff));border-left:3px solid var(--primary-color,#1878b5);border-radius:5px;margin:12px 0}.warning{border-color:#c4851b;background:color-mix(in srgb,#e6ac37 12%,var(--card-background-color,#fff))}.error{border-color:#c63c45;background:color-mix(in srgb,#c63c45 9%,var(--card-background-color,#fff))}
  svg{display:block;width:100%;height:auto;touch-action:pan-y;overflow:visible}.chart{min-width:260px}.legend{display:flex;gap:18px;flex-wrap:wrap;margin-bottom:8px}.legend span:before{content:'';display:inline-block;width:18px;height:3px;vertical-align:middle;margin-right:6px;background:var(--line)}.legend span.target:before{background:repeating-linear-gradient(90deg,var(--line) 0 7px,transparent 7px 11px)}.tip{font-variant-numeric:tabular-nums;min-height:30px;margin:10px 0}.scrub{width:100%;accent-color:#157bc0}
  .tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid var(--divider-color,#e4e9ef);white-space:nowrap}th{font-size:12px;color:var(--secondary-text-color,#57667a)}th.num,td.num{text-align:right}td .hint{display:block;font-size:12px;max-width:500px;overflow:hidden;text-overflow:ellipsis}.badge{font-size:11px;border-radius:4px;padding:2px 5px;background:color-mix(in srgb,#dfaa34 17%,transparent);margin-left:6px}.positive{color:var(--success-color,#208461)}.planlist{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}.plan{padding:12px;border:1px solid var(--divider-color,#dce3eb);border-radius:8px}.plan h3{margin-top:0}
  .loading:before{content:'';display:inline-block;width:14px;height:14px;border:2px solid #9daec0;border-top-color:#1878b5;border-radius:50%;animation:spin .8s linear infinite;margin-right:9px;vertical-align:middle}@keyframes spin{to{transform:rotate(360deg)}}
  .negative{color:var(--error-color,#c63c45)}.inline-action{padding:4px 8px;background:transparent}.field{display:grid;gap:5px;margin:12px 0;max-width:620px}.field label{font-size:13px;color:var(--secondary-text-color,#57667a)}.field input,.field select{width:100%}.decision{padding:12px 0;border-bottom:1px solid var(--divider-color,#e4e9ef)}.decision select{margin-top:7px;min-width:min(100%,360px)}
  input[type=file]{max-width:100%;margin:12px 0} .missing-row{display:flex;align-items:center;gap:12px;justify-content:space-between;border-bottom:1px solid var(--divider-color,#e4e9ef);padding:10px 0}.missing-row input{width:155px}
  @media(max-width:1100px){.overview-stats{grid-template-columns:repeat(4,minmax(0,1fr))}}
  @media(max-width:700px){header{padding:12px}main{padding:14px}.stats{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.stats>.stat:last-child:nth-child(odd){grid-column:1/-1}.stat,.card{padding:14px}.stat strong{font-size:20px}h1{font-size:20px}.toolbar{gap:8px}.toolbar label{width:100%}.toolbar select{flex:1}.tabs{margin-left:-2px;margin-right:-2px}.selection-card{align-items:stretch;flex-direction:column;gap:12px}.selection-control{width:100%}.selection-control select{width:100%}.allocation-layout{grid-template-columns:1fr;gap:14px}.donut{max-width:240px}.alias-grid{grid-template-columns:1fr}.missing-row{align-items:flex-start;flex-direction:column}.controls{gap:8px}th,td{padding:10px 7px}}
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
    this._targetLine = true;
    this._forecastYears = 0;
    this._customForecastYears = 25;
    this._customForecastOpen = false;
    this._section = "overview";
    this._position = "all";
    this._summaryPeriod = "monthly";
    this._busy = false;
    this._importOpen = false;
    this._aliasOpen = false;
    this._aliasDraft = null;
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
    try {
      const saved = localStorage.getItem(`my-wallet:section:${this._hass.user?.id || "admin"}`);
      if (["overview", "positions", "history", "data"].includes(saved)) this._section = saved;
    } catch { /* Browser storage may be disabled. */ }
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
  _positionItem(symbol) { return this._wallet()?.positions.find(item => item.symbol === symbol); }
  _positionAlias(symbol) { return this._positionItem(symbol)?.alias?.trim() || ""; }
  _positionLabel(symbol) {
    const alias = this._positionAlias(symbol);
    return alias ? `${alias} (${symbol})` : symbol;
  }
  _call(type, data = {}) { return this._hass.callWS({ type: `my_wallet/${type}`, ...data }); }
  _errorText(err) {
    const code = err?.code || "error";
    if (WORDS.en[code]) return this.t(code);
    if (code.startsWith("invalid_") || code.includes("import_items")) return this.t("invalid_import");
    return this.t("error");
  }
  async _refresh(quiet = false, forecastYears = this._forecastYears) {
    if (this._busy) return;
    this._busy = true;
    this._error = null;
    if (!quiet) this._render();
    try {
      const forecast = forecastYears > 0 ? { forecast_years: forecastYears } : {};
      const result = await this._call("wallets", forecast);
      this._wallets = result.wallets;
      if (!this._wallet()) this._selected = this._wallets[0]?.entry_id;
      this._history = this._selected ? await this._call("history", { entry_id: this._selected, ...forecast }) : null;
    } catch (err) { this._error = this._errorText(err); }
    finally { this._busy = false; this._render(); }
  }
  _notice(parent, text, kind = "") { parent.append(node("p", text, `notice ${kind}`)); }
  _stat(parent, label, value) {
    const card = node("div", null, "stat");
    card.append(node("span", label), node("strong", value));
    parent.append(card);
  }
  _setSection(section) {
    this._section = section;
    try { localStorage.setItem(`my-wallet:section:${this._hass.user?.id || "admin"}`, section); } catch { /* Keep the in-memory choice. */ }
    this._render();
  }
  _renderNavigation(parent) {
    const tabs = node("nav", null, "tabs");
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "My Wallet");
    for (const [section, label] of [["overview", "navOverview"], ["positions", "navPositions"], ["history", "navHistory"], ["data", "navData"]]) {
      const tab = button(this.t(label), () => this._setSection(section));
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", String(this._section === section));
      tabs.append(tab);
    }
    parent.append(tabs);
  }
  _renderStats(parent, wallet, position) {
    const stats = node("div", null, "stats");
    if (!position) stats.classList.add("overview-stats");
    const values = position ? [
      ["currentValue", this.money(position.value)], ["purchaseCost", this.money(position.cost)],
      ["positionStart", position.start_date ? this.day(position.start_date) : this.t("emptyValue")],
      ["units", this.units(position.units)], ["profit", this.money(position.profit)],
      ["performance", this.percent(position.performance)], ["dividends", this.money(position.dividends)],
    ] : [
      ["value", this.money(wallet.total)], ["invested", this.money(wallet.invested)],
      ["portfolioStart", wallet.start_date ? this.day(wallet.start_date) : this.t("emptyValue")],
      ["profit", this.money(wallet.profit)], ["performance", this.percent(wallet.performance)],
      ["annualReturn", this.percent(wallet.money_weighted_return)], ["cash", this.money(wallet.cash)],
      ["dividends", this.money(wallet.dividends)],
    ];
    for (const [key, value] of values) this._stat(stats, this.t(key), value);
    parent.append(stats);
  }
  async _setForecastYears(years) {
    this._forecastYears = years;
    this._customForecastOpen = years > 0 && ![1, 3, 5, 10, 20, 30].includes(years);
    if (years) this._period = "all";
    const wallet = this._wallet();
    const available = !years || (this._history?.target?.forecasts?.[String(years)] && wallet?.target?.allocation_forecasts?.[String(years)]);
    if (available) this._render();
    else await this._refresh(false, years);
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
    select.addEventListener("change", () => {
      this._selected = select.value;
      this._position = "all";
      this._forecastYears = 0;
      this._customForecastOpen = false;
      this._aliasOpen = false;
      this._aliasDraft = null;
      this._history = null;
      this._refresh();
    });
    selectLabel.append(select);
    const refresh = button(this.t("refresh"), () => this._refresh());
    refresh.disabled = this._busy;
    const settings = node("a", this.t("settings"), "button");
    settings.href = "/config/integrations/integration/my_wallet";
    const importButton = button(this.t("import"), () => { this._importOpen = !this._importOpen; if (this._importOpen && !this._importMode) this._importMode = this._wallet() ? "followup" : "new"; this._render(); });
    importButton.disabled = this._busy;
    toolbar.append(selectLabel, node("div", null, "grow"), refresh, settings, importButton);
    main.append(toolbar);
    if (this._error) this._notice(main, this._error, "error");
    if (this._busy) this._notice(main, this.t(this._importBusy ? "preparing" : "loading"), "loading");
    if (this._importOpen) this._renderImport(main);
    const wallet = this._wallet();
    if (!wallet) { this._notice(main, this.t("noWallet")); return; }
    if (this._position !== "all" && !wallet.positions.some(item => item.symbol === this._position)) this._position = "all";
    if (wallet.opening_conflicts?.length) {
      const warning = node("div", null, "notice warning");
      warning.setAttribute("role", "alert");
      warning.append(node("p", this.t("openingConflict")));
      const list = node("ul");
      const number = new Intl.NumberFormat(this._lang, { maximumFractionDigits: 12 });
      for (const item of wallet.opening_conflicts) list.append(node("li", `${this._positionLabel(item.symbol)}: ${this.t("configuredUnits")} ${number.format(item.configured_units)}; ${this.t("includedUnits")} ${number.format(item.included_units)}`));
      warning.append(list);
      main.append(warning);
    }
    this._renderNavigation(main);
    this._renderPositionSelection(main, wallet);
    const position = wallet.positions.find(item => item.symbol === this._position);
    if (wallet.pending?.length) this._notice(main, this.t("pending"), "warning");
    if (this._section === "overview") {
      this._renderStats(main, wallet, position);
      if (!position) this._renderTargetSummary(main, wallet);
      this._renderAllocation(main, wallet);
    } else if (this._section === "positions") {
      if (position) this._renderStats(main, wallet, position);
      this._renderPositions(main, wallet);
      if (position) this._renderPositionDetails(main, position, wallet.currency);
      if (this._correctionOpen) this._renderCorrection(main, wallet);
    } else if (this._section === "history" && this._history) {
      if (this._history.estimated) this._renderEstimateNotice(main);
      if (this._history.unknown_opening.length) this._notice(main, this.t("openingWarning"), "warning");
      if (this._history.missing_history.length) this._notice(main, this.t("quotesWarning"), "warning");
      if (this._history.range_limited) this._notice(main, this.t("limited"));
      this._renderChart(main);
      this._renderSummary(main);
    } else if (this._section === "data") {
      this._renderPlans(main, wallet.plans, wallet.currency);
      if (this._history) this._renderLedger(main);
      this._renderExport(main);
    }
  }
  _renderPositionSelection(parent, wallet) {
    const section = node("section", null, "card selection-card");
    const copy = node("div", null, "selection-copy");
    copy.append(node("h2", this.t("analysis")), node("p", this.t("analysisHint"), "hint"));
    const label = node("label", null, "selection-control");
    const select = node("select");
    select.setAttribute("aria-label", this.t("analysisFor"));
    for (const item of [{ symbol: "all" }, ...wallet.positions]) {
      const option = node("option", item.symbol === "all" ? this.t("allPositions") : this._positionLabel(item.symbol));
      option.value = item.symbol;
      option.selected = item.symbol === this._position;
      select.append(option);
    }
    select.addEventListener("change", () => {
      this._position = select.value;
      if (this._position !== "all") { this._cashLine = false; this._forecastYears = 0; this._customForecastOpen = false; }
      this._render();
    });
    label.append(node("span", this.t("analysisFor")), select);
    section.append(copy, node("div", null, "grow"), label);
    parent.append(section);
  }
  _renderTargetSummary(parent, wallet) {
    const section = node("section", null, "card");
    const controls = node("div", null, "controls");
    controls.append(node("h2", this.t("targetComparison")), node("div", null, "grow"));
    const forecast = node("label", this.t("forecast"));
    const select = node("select");
    const presets = [0, 1, 3, 5, 10, 20, 30];
    for (const years of presets) {
      const text = years ? `${years} ${this.t(years === 1 ? "forecastYear" : "forecastYears")}` : this.t("forecastToday");
      const option = node("option", text);
      option.value = String(years); option.selected = years === this._forecastYears; select.append(option);
    }
    const custom = node("option", this.t("forecastCustom"));
    custom.value = "custom"; custom.selected = this._customForecastOpen || (this._forecastYears > 0 && !presets.includes(this._forecastYears)); select.append(custom);
    select.disabled = wallet.target?.value == null;
    select.addEventListener("change", () => {
      if (select.value === "custom") { this._customForecastOpen = true; this._render(); }
      else this._setForecastYears(Number(select.value));
    });
    forecast.append(select); controls.append(forecast); section.append(controls);
    if (this._customForecastOpen) {
      const customControls = node("div", null, "forecast-custom");
      const input = node("input");
      input.type = "number"; input.min = "1"; input.max = "50"; input.step = "1"; input.value = String(this._customForecastYears);
      input.setAttribute("aria-label", this.t("forecastCustomYears"));
      const apply = button(this.t("apply"), () => {
        const years = Number(input.value);
        if (Number.isInteger(years) && years >= 1 && years <= 50) { this._customForecastYears = years; this._setForecastYears(years); }
      }, "primary");
      input.addEventListener("input", () => { const years = Number(input.value); apply.disabled = !Number.isInteger(years) || years < 1 || years > 50; });
      input.addEventListener("keydown", event => { if (event.key === "Enter") apply.click(); });
      customControls.append(input, apply); section.append(customControls);
    }
    const target = wallet.target || {};
    if (target.value == null) {
      this._notice(section, this.t("targetUnavailable"), "warning"); parent.append(section); return;
    }
    const historyTarget = this._history?.target || {};
    const forecastItem = this._forecastYears ? historyTarget.forecasts?.[String(this._forecastYears)] : { date: target.date, value: target.value, contributions: historyTarget.contributions, growth: historyTarget.growth };
    const stats = node("div", null, "stats target-stats");
    this._stat(stats, this.t("expectedReturn"), this.ratio(target.annual_return));
    this._stat(stats, this._forecastYears ? this.t("forecastValue") : this.t("targetValue"), this.money(forecastItem?.value));
    this._stat(stats, this.t("forecastDate"), this.day(forecastItem?.date));
    this._stat(stats, this.t("targetContributions"), this.money(forecastItem?.contributions));
    if (this._forecastYears) this._stat(stats, this.t("futureContributions"), this.money(forecastItem?.additional_contributions));
    this._stat(stats, this.t("targetGrowth"), this.money(forecastItem?.growth));
    if (!this._forecastYears) this._stat(stats, this.t("currentTargetDeviation"), `${this.money(target.absolute_deviation)} · ${this.percent(target.percentage_deviation)}`);
    section.append(stats, node("p", this.t("targetHint"), "hint")); parent.append(section);
  }
  _renderAllocation(parent, wallet) {
    const section = node("section", null, "card");
    const forecast = this._forecastYears ? wallet.target?.allocation_forecasts?.[String(this._forecastYears)] : null;
    const total = forecast?.total ?? wallet.total, cash = forecast?.cash ?? wallet.cash;
    const positionValue = item => forecast?.positions?.[item.symbol] ?? item.value;
    const title = forecast ? `${this.t("forecastAllocation")} · ${this.day(forecast.date)}` : this.t("allocation");
    section.append(node("h2", title), node("p", this.t(forecast ? "forecastAllocationHint" : "allocationHint"), "hint"));
    if (!Number.isFinite(total) || total <= 0 || !Number.isFinite(cash) || cash < 0 || wallet.positions.some(item => !Number.isFinite(positionValue(item)) || positionValue(item) < 0)) {
      this._notice(section, this.t("emptyValue"));
      parent.append(section);
      return;
    }
    const palette = ["#157bc0", "#269e81", "#8b67c8", "#d9822b", "#d34f68", "#4d9ca8", "#8d7445", "#6c83d5"];
    const segments = wallet.positions.filter(item => positionValue(item) > 0).map((item, index) => ({
      symbol: item.symbol,
      label: this._positionLabel(item.symbol),
      value: positionValue(item),
      target: item.target,
      color: palette[index % palette.length],
    }));
    if (cash > 0) segments.push({ symbol: null, label: this.t("cash"), value: cash, target: null, color: "#98a3af" });
    if (total <= 0) {
      this._notice(section, this.t("emptyValue"));
      parent.append(section);
      return;
    }
    const layout = node("div", null, "allocation-layout"), svg = svgNode("svg", { viewBox: "0 0 240 240", role: "img", "aria-label": this.t("allocation"), class: "donut" });
    const radius = 82, circumference = 2 * Math.PI * radius;
    svg.append(svgNode("circle", { cx: 120, cy: 120, r: radius, fill: "none", stroke: "var(--divider-color,#e4e9ef)", "stroke-width": 32 }));
    let offset = 0;
    for (const item of segments) {
      const length = item.value / total * circumference;
      const circle = svgNode("circle", { cx: 120, cy: 120, r: radius, fill: "none", stroke: item.color, "stroke-width": 32, "stroke-dasharray": `${length} ${circumference - length}`, "stroke-dashoffset": -offset, transform: "rotate(-90 120 120)" });
      const title = svgNode("title", {}); title.textContent = `${item.label}: ${this.money(item.value, wallet.currency)}`; circle.append(title); svg.append(circle); offset += length;
    }
    const centerValue = svgNode("text", { x: 120, y: 116, "text-anchor": "middle", fill: "var(--primary-text-color,#182b42)", "font-size": 17, "font-weight": 700 });
    centerValue.textContent = this.money(total, wallet.currency);
    const centerLabel = svgNode("text", { x: 120, y: 139, "text-anchor": "middle", fill: "var(--secondary-text-color,#57667a)", "font-size": 12 });
    centerLabel.textContent = this.t("all"); svg.append(centerValue, centerLabel);

    const wrap = node("div", null, "tablewrap"), table = node("table"), head = node("thead"), hr = node("tr");
    for (const key of ["position", forecast ? "projectedValue" : "currentValue", forecast ? "forecastShare" : "actualShare", "target", "deviation"]) hr.append(node("th", this.t(key), key === "position" ? "" : "num"));
    head.append(hr); table.append(head); const body = node("tbody");
    for (const item of segments) {
      const actual = item.value / total * 100, difference = item.target == null ? null : actual - item.target;
      const tr = node("tr"); if (item.symbol === this._position) tr.className = "selected";
      const first = node("td"), swatch = node("span", null, "swatch"); swatch.style.background = item.color;
      if (item.symbol) {
        const choose = button(item.label, () => { this._position = item.symbol; this._cashLine = false; this._forecastYears = 0; this._customForecastOpen = false; this._setSection("positions"); }, "inline-action allocation-name");
        choose.prepend(swatch); first.append(choose);
      } else {
        const label = node("span", item.label, "allocation-name"); label.prepend(swatch); first.append(label);
      }
      const cls = value => `num ${value > 0 ? "positive" : value < 0 ? "negative" : ""}`;
      tr.append(first, node("td", this.money(item.value, wallet.currency), "num"), node("td", this.ratio(actual), "num"), node("td", this.ratio(item.target), "num"), node("td", this.percent(difference), cls(difference)));
      body.append(tr);
    }
    table.append(body); wrap.append(table); layout.append(svg, wrap); section.append(layout); parent.append(section);
  }
  _renderPositionDetails(parent, position, currency) {
    const section = node("section", null, "card"), heading = node("h2", null, "details-title");
    heading.append(node("span", `${this.t("purchaseLots")} · ${this._positionAlias(position.symbol) || position.symbol}`));
    if (this._positionAlias(position.symbol)) heading.append(node("span", position.symbol, "hint"));
    section.append(heading);
    const rows = position.lots || [];
    if (!rows.length) {
      this._notice(section, this.t("noLots"));
      parent.append(section);
      return;
    }
    const wrap = node("div", null, "tablewrap"), table = node("table"), head = node("thead"), hr = node("tr");
    for (const key of ["date", "purchaseCost", "units", "purchasePrice", "currentValue", "dividends", "profit", "performance", "annualizedPerformance"]) hr.append(node("th", this.t(key), key === "date" ? "" : "num"));
    head.append(hr); table.append(head); const body = node("tbody");
    for (const row of rows) {
      const tr = node("tr"), dateCell = node("td", this.day(row.date));
      if (row.included_in_opening) dateCell.append(node("span", this.t("includedOpening"), "badge"));
      if (row.price_date && row.price_date !== row.date) dateCell.append(node("span", `${this.t("priceDate")}: ${this.day(row.price_date)}`, "hint"));
      const units = node("td", this.units(row.units), "num");
      if (row.estimated) units.append(node("span", this.t("estimate"), "badge"));
      const cls = value => `num ${value > 0 ? "positive" : value < 0 ? "negative" : ""}`;
      tr.append(dateCell, node("td", this.money(row.amount, currency), "num"), units, node("td", this.money(row.purchase_price, currency), "num"),
        node("td", this.money(row.current_value, currency), "num"), node("td", this.money(row.dividends, currency), "num"),
        node("td", this.money(row.profit, currency), cls(row.profit)), node("td", this.percent(row.performance), cls(row.performance)),
        node("td", this.percent(row.annualized_performance), cls(row.annualized_performance)));
      body.append(tr);
    }
    table.append(body); wrap.append(table); section.append(wrap, node("p", this.t("lotDetailsHint"), "hint")); parent.append(section);
  }
  _renderPositions(parent, wallet) {
    const section = node("section", null, "card"), controls = node("div", null, "controls");
    const forecast = this._forecastYears ? wallet.target?.allocation_forecasts?.[String(this._forecastYears)] : null;
    controls.append(node("h2", this.t("positions")), node("div", null, "grow"));
    controls.append(
      button(this.t("editAliases"), () => {
        this._aliasOpen = !this._aliasOpen;
        this._aliasDraft = this._aliasOpen ? Object.fromEntries(wallet.positions.map(item => [item.symbol, item.alias || ""])) : null;
        this._render();
      }, this._aliasOpen ? "active" : ""),
      button(this.t("correctUnits"), () => { this._correctionOpen = !this._correctionOpen; this._correctionPreview = null; this._render(); }),
    );
    section.append(controls);
    if (this._aliasOpen) this._renderAliasEditor(section, wallet);
    const wrap = node("div", null, "tablewrap"), table = node("table"), head = node("thead"), hr = node("tr");
    const columns = ["position", "units", "currentPrice", "currentValue", "purchaseCost", "profit", "performance", "share", ...(forecast ? ["projectedValue", "forecastShare"] : []), "target"];
    for (const key of columns) hr.append(node("th", this.t(key), key === "position" ? "" : "num"));
    head.append(hr); table.append(head); const body = node("tbody");
    for (const item of wallet.positions) {
      const tr = node("tr"), alias = item.alias?.trim() || "";
      if (item.symbol === this._position) tr.className = "selected";
      const choose = button(alias || item.symbol, () => { this._position = item.symbol; this._cashLine = false; this._forecastYears = 0; this._customForecastOpen = false; this._render(); }, "inline-action");
      choose.setAttribute("aria-label", this._positionLabel(item.symbol));
      const first = node("td"); first.append(choose);
      if (alias) first.append(node("span", item.symbol, "hint"));
      if (!item.cost_complete) first.append(node("span", this.t("incompleteCost"), "hint"));
      const cls = value => `num ${value > 0 ? "positive" : value < 0 ? "negative" : ""}`;
      const forecastValue = forecast?.positions?.[item.symbol], forecastShare = forecastValue != null && forecast.total ? forecastValue / forecast.total * 100 : null;
      tr.append(first, node("td", this.units(item.units), "num"), node("td", this.money(item.price), "num"),
        node("td", this.money(item.value), "num"), node("td", this.money(item.cost), "num"),
        node("td", this.money(item.profit), cls(item.profit)), node("td", this.percent(item.performance), cls(item.performance)),
        node("td", this.ratio(item.share), "num"));
      if (forecast) tr.append(node("td", this.money(forecastValue), "num"), node("td", this.ratio(forecastShare), "num"));
      tr.append(node("td", this.ratio(item.target), "num"));
      body.append(tr);
    }
    table.append(body); wrap.append(table); section.append(wrap); parent.append(section);
  }
  _renderAliasEditor(parent, wallet) {
    const editor = node("div", null, "alias-editor");
    editor.append(node("h3", this.t("positionNames")), node("p", this.t("aliasHint"), "hint"));
    const grid = node("div", null, "alias-grid");
    for (const item of wallet.positions) {
      const row = node("label", null, "alias-row"), symbol = node("strong", item.symbol), input = node("input");
      input.type = "text";
      input.maxLength = 80;
      input.placeholder = this.t("aliasPlaceholder");
      input.value = this._aliasDraft?.[item.symbol] || "";
      input.setAttribute("aria-label", `${this.t("positionNames")}: ${item.symbol}`);
      input.addEventListener("input", () => { this._aliasDraft = { ...this._aliasDraft, [item.symbol]: input.value }; });
      row.append(symbol, input);
      grid.append(row);
    }
    const actions = node("div", null, "controls"), save = button(this.t("saveAliases"), () => this._saveAliases(), "primary");
    save.disabled = this._busy;
    actions.append(save, button(this.t("cancel"), () => { this._aliasOpen = false; this._aliasDraft = null; this._render(); }));
    editor.append(grid, actions);
    parent.append(editor);
  }
  async _saveAliases() {
    if (this._busy || !this._aliasDraft) return;
    this._busy = true;
    this._error = null;
    this._render();
    let saved = false;
    try {
      await this._call("position_aliases", { entry_id: this._selected, aliases: this._aliasDraft });
      this._aliasOpen = false;
      this._aliasDraft = null;
      saved = true;
    } catch (err) { this._error = this._errorText(err); }
    finally { this._busy = false; }
    if (saved) await this._refresh();
    else this._render();
  }
  _renderCorrection(parent, wallet) {
    const section = node("section", null, "card");
    section.append(node("h2", this.t("correction")), node("p", this.t("correctionHint"), "hint"));
    const choices = wallet.correction_choices || [];
    if (!choices.length) { this._notice(section, this.t("noRows")); parent.append(section); return; }
    if (!this._correction || !choices.some(item => item.symbol === this._correction.symbol)) {
      const initial = choices.find(item => item.symbol === this._position) || choices[0];
      this._correction = { symbol: initial.symbol, target: initial.lots.at(-1)?.id || "opening", mode: "position", units: initial.units, note: "" };
    }
    const selected = () => choices.find(item => item.symbol === this._correction.symbol);
    const targetUnits = () => this._correction.target === "opening" ? selected().opening_units : selected().lots.find(item => item.id === this._correction.target)?.units;
    if (this._correction.units == null) this._correction.units = this._correction.mode === "position" ? selected().units : targetUnits();
    const field = (label, control) => { const wrapper = node("div", null, "field"); wrapper.append(node("label", label), control); section.append(wrapper); return control; };
    const symbol = field(this.t("position"), node("select"));
    for (const item of choices) { const option = node("option", this._positionLabel(item.symbol)); option.value = item.symbol; option.selected = item.symbol === this._correction.symbol; symbol.append(option); }
    symbol.addEventListener("change", () => { const next = choices.find(item => item.symbol === symbol.value); this._correction = { symbol: symbol.value, target: next.lots.at(-1)?.id || "opening", mode: "position", units: next.units, note: this._correction.note }; this._correctionPreview = null; this._render(); });
    const target = field(this.t("correctionTarget"), node("select"));
    const opening = node("option", `${this.t("openingUnits")}: ${this.units(selected().opening_units)}`); opening.value = "opening"; target.append(opening);
    for (const lot of selected().lots) {
      const option = node("option", `${this.day(lot.date)} · ${this.units(lot.units)} · ${this.money(lot.amount)}${lot.estimated ? ` · ${this.t("estimate")}` : ""}`);
      option.value = lot.id; option.selected = lot.id === this._correction.target; target.append(option);
    }
    target.value = this._correction.target;
    target.addEventListener("change", () => { this._correction.target = target.value; this._correction.units = this._correction.mode === "position" ? selected().units : targetUnits(); this._correctionPreview = null; this._render(); });
    const scope = field(this.t("correction"), node("select"));
    for (const [value, label] of [["position", "totalPosition"], ["lot", "onlyLot"]]) { const option = node("option", this.t(label)); option.value = value; option.selected = value === this._correction.mode; scope.append(option); }
    scope.addEventListener("change", () => { this._correction.mode = scope.value; this._correction.units = scope.value === "position" ? selected().units : targetUnits(); this._correctionPreview = null; this._render(); });
    const units = field(this.t(this._correction.mode === "position" ? "exactTotal" : "exactLot"), node("input"));
    units.type = "number"; units.min = "0"; units.step = "any"; units.value = String(this._correction.units);
    units.addEventListener("input", () => { this._correction.units = units.value; this._correctionPreview = null; });
    const note = field(this.t("reason"), node("input")); note.maxLength = 500; note.value = this._correction.note;
    note.addEventListener("input", () => { this._correction.note = note.value; });
    section.append(node("p", this.t("unchangedPayments"), "notice"));
    const actions = node("div", null, "controls"), preview = button(this.t("correctionPreview"), () => this._prepareCorrection());
    preview.disabled = this._busy; actions.append(preview, button(this.t("cancel"), () => { this._correctionOpen = false; this._correctionPreview = null; this._render(); })); section.append(actions);
    if (this._correctionPreview?.summary) {
      const summary = this._correctionPreview.summary, result = node("div", null, "notice");
      result.append(node("strong", `${this._positionLabel(summary.symbol)}: ${this.t("before")} ${this.units(summary.before_total)} → ${this.t("after")} ${this.units(summary.after_total)}`));
      result.append(node("p", `${this.t(summary.target === "opening" ? "openingUnits" : "chosenLot")}: ${this.units(summary.before_units)} → ${this.units(summary.after_units)}`));
      section.append(result);
      const label = node("label", this.t("correctionCheck")), check = node("input"); check.type = "checkbox"; label.prepend(check); section.append(label);
      const confirm = button(this.t("correctionConfirm"), () => this._commitCorrection(), "primary"); confirm.disabled = true;
      check.addEventListener("change", () => { confirm.disabled = !check.checked || this._busy; });
      const confirmActions = node("div", null, "controls"); confirmActions.append(confirm); section.append(confirmActions);
    }
    parent.append(section);
  }
  async _prepareCorrection() {
    if (this._busy) return;
    this._busy = true; this._error = null; this._correctionPreview = null; this._render();
    try { this._correctionPreview = await this._call("correction_preview", { entry_id: this._selected, correction: this._correction }); }
    catch (err) { this._error = this._errorText(err); }
    finally { this._busy = false; this._render(); }
  }
  async _commitCorrection() {
    if (this._busy || !this._correctionPreview?.token) return;
    this._busy = true; this._error = null; this._render();
    try { await this._call("correction_commit", { token: this._correctionPreview.token, confirm: true }); this._correctionOpen = false; this._correctionPreview = null; }
    catch (err) { this._error = this._errorText(err); }
    finally { this._busy = false; }
    await this._refresh();
  }
  percent(value) { return value == null ? "—" : new Intl.NumberFormat(this._lang, { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "exceptZero" }).format(value) + " %"; }
  ratio(value) { return value == null ? "—" : new Intl.NumberFormat(this._lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value) + " %"; }
  units(value) { return value == null ? "—" : new Intl.NumberFormat(this._lang, { maximumFractionDigits: 12 }).format(value); }
  _renderEstimateNotice(parent) {
    const key = `my-wallet:estimate-notice:${this._hass.user?.id || "admin"}:${this._selected}`;
    let hidden = this._noticeHidden?.[key] || false;
    try { hidden = localStorage.getItem(key) === "hidden"; } catch { /* Browser storage may be disabled. */ }
    const toggle = () => {
      this._noticeHidden = { ...this._noticeHidden, [key]: !hidden };
      try { localStorage.setItem(key, hidden ? "visible" : "hidden"); } catch { /* Keep the in-memory choice. */ }
      this._render();
    };
    if (hidden) parent.append(button(this.t("showHint"), toggle));
    else {
      const notice = node("div", null, "notice");
      notice.append(node("p", this.t("estimated")), button(this.t("hideHint"), toggle));
      parent.append(notice);
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
      for (const row of plan.allocations) item.append(node("div", `${this._positionLabel(row.symbol)}: ${plan.allocation_mode === "percentage" ? `${row.value} %` : this.money(row.value, currency)}`, "hint"));
      list.append(item);
    }
    card.append(list);
    parent.append(card);
  }
  _renderChart(parent) {
    const section = node("section", null, "card chart");
    section.append(node("h2", this._position === "all" ? this.t("history") : `${this.t("history")} · ${this._positionLabel(this._position)}`));
    const controls = node("div", null, "controls");
    for (const key of ["all", "year", "six", "three"]) controls.append(button(this.t(key), () => { this._period = key; if (key !== "all") { this._forecastYears = 0; this._customForecastOpen = false; } this._render(); }, this._period === key ? "active" : ""));
    if (this._position === "all") {
      const cashLabel = node("label", this.t("cashChart")), cashCheck = node("input");
      cashCheck.type = "checkbox"; cashCheck.checked = this._cashLine;
      cashCheck.addEventListener("change", () => { this._cashLine = cashCheck.checked; this._render(); });
      cashLabel.prepend(cashCheck); controls.append(cashLabel);
      if (this._history.target?.current_value != null) {
        const targetLabel = node("label", this.t("targetLine")), targetCheck = node("input");
        targetCheck.type = "checkbox"; targetCheck.checked = this._targetLine;
        targetCheck.addEventListener("change", () => { this._targetLine = targetCheck.checked; this._render(); });
        targetLabel.prepend(targetCheck); controls.append(targetLabel);
      }
    }
    section.append(controls);
    const limit = { year: 366, six: 184, three: 93 }[this._period];
    let source = limit ? this._history.points.slice(-limit) : this._history.points;
    let showProjection = false;
    if (this._position === "all" && this._forecastYears && !limit && this._targetLine) {
      const cutoff = this._history.target?.forecasts?.[String(this._forecastYears)]?.date;
      const target = this._history.target || {}, wallet = this._wallet();
      const canProject = Number.isFinite(wallet?.total) && Number.isFinite(target.current_value) && Number.isFinite(target.annual_return) && target.date;
      const project = point => {
        const days = (Date.parse(`${point.date}T00:00:00Z`) - Date.parse(`${target.date}T00:00:00Z`)) / 86400000;
        return point.target + (wallet.total - target.current_value) * Math.pow(1 + target.annual_return / 100, days / 365.2425);
      };
      const projectInvested = point => Number.isFinite(wallet?.invested) && Number.isFinite(target.contributions) && Number.isFinite(point.invested) ? wallet.invested + point.invested - target.contributions : point.invested;
      if (canProject && source.length) {
        source = source.map((point, index) => index === source.length - 1 ? { ...point, projected: wallet.total } : point);
        showProjection = true;
      }
      source = [...source, ...(this._history.target_forecast || []).filter(point => !cutoff || point.date <= cutoff).map(point => ({ ...point, value: null, projected: canProject ? project(point) : null, invested: projectInvested(point), cash: null }))];
    }
    const points = this._position === "all" ? source : source.map(point => ({
      ...point,
      value: Object.hasOwn(point.positions || {}, this._position) ? point.positions[this._position] : 0,
      invested: point.position_costs?.[this._position] || 0,
      cash: null,
    }));
    const showCash = this._cashLine && this._position === "all";
    const showTarget = this._targetLine && this._position === "all" && source.some(point => Number.isFinite(point.target));
    const keys = ["value", ...(showProjection ? ["projected"] : []), "invested", ...(showTarget ? ["target"] : []), ...(showCash ? ["cash"] : [])];
    const keyLabel = key => key === "target" ? `${this.t("targetValue")} · ${this.ratio(this._history.target?.annual_return)} ${this.t("perYear")}` : key === "projected" ? this.t("portfolioForecast") : key === "invested" && showProjection ? this.t("forecastInvested") : this._position === "all" ? this.t(key) : this.t(key === "value" ? "positionValue" : "purchaseCost");
    const colors = { value: "#157bc0", projected: "#55a2d9", invested: "#269e81", target: "#8b67c8", cash: "#c48925" };
    const legend = node("div", null, "legend");
    for (const key of ["value", ...(showProjection ? ["projected"] : []), "invested", ...(showTarget ? ["target"] : [])]) { const item = node("span", keyLabel(key), ["projected", "target"].includes(key) ? "target" : ""); item.style.setProperty("--line", colors[key]); legend.append(item); }
    section.append(legend);
    if (!points.length) { this._notice(section, this.t("noRows")); parent.append(section); return; }
    parent.append(section);
    const padding = parseFloat(getComputedStyle(section).paddingLeft) * 2;
    const width = Math.max(240, Math.min(1000, section.clientWidth - padding));
    const currency = this._wallet().currency;
    const groups = [{ keys: ["value", ...(showProjection ? ["projected"] : []), "invested", ...(showTarget ? ["target"] : [])], height: width < 500 ? 260 : 310 }];
    if (showCash) groups.push({ keys: ["cash"], height: width < 500 ? 155 : 175 });
    for (const group of groups) {
      group.scale = currencyScale(points.flatMap(point => group.keys.map(key => point[key])), currency);
      group.labels = axisLabels(group.scale, this._lang, currency);
    }
    const canvas = document.createElement("canvas").getContext("2d");
    canvas.font = "12px system-ui";
    const labelWidth = Math.max(...groups.flatMap(group => group.labels.map(label => canvas.measureText(label).width)));
    const left = Math.min(width * .43, Math.max(60, labelWidth + 14)), right = width - 12;
    const times = points.map(point => Date.parse(`${point.date}T00:00:00Z`));
    const firstTime = times[0], lastTime = times[times.length - 1];
    const x = index => left + (times[index] - firstTime) / Math.max(1, lastTime - firstTime) * (right - left);
    const cursors = [], svgs = [];
    groups.forEach((group, groupIndex) => {
      const { scale, height } = group, top = 14, bottom = height - 36;
      if (groupIndex) {
        const label = node("div", null, "legend");
        const item = node("span", this.t("cash")); item.style.setProperty("--line", colors.cash);
        label.append(item, node("small", this.t("cashScale"), "hint")); section.append(label);
      }
      const y = value => bottom - (value - scale.min) / (scale.max - scale.min) * (bottom - top);
      const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": this.t(groupIndex ? "cash" : "history") });
      scale.ticks.forEach((value, index) => {
        svg.append(svgNode("line", { x1: left, x2: right, y1: y(value), y2: y(value), stroke: "var(--divider-color,#e0e6ed)", "stroke-width": 1 }));
        const label = svgNode("text", { x: left - 10, y: y(value) + 4, fill: "var(--secondary-text-color,#57667a)", "font-size": 12, "text-anchor": "end" });
        label.textContent = group.labels[index]; svg.append(label);
      });
      const indices = width < 500 ? [0, points.length - 1] : [0, Math.floor((points.length - 1) / 2), points.length - 1];
      for (const index of [...new Set(indices)]) {
        const label = svgNode("text", { x: x(index), y: bottom + 26, fill: "var(--secondary-text-color,#57667a)", "font-size": 12, "text-anchor": index === 0 ? "start" : index === points.length - 1 ? "end" : "middle" });
        label.textContent = this.day(points[index].date); svg.append(label);
      }
      for (const key of group.keys) {
        let path = "", active = false;
        points.forEach((point, index) => {
          if (!Number.isFinite(point[key])) { active = false; return; }
          path += !active ? `M${x(index)} ${y(point[key])}` : ["value", "projected", "target"].includes(key) ? `L${x(index)} ${y(point[key])}` : `H${x(index)}V${y(point[key])}`;
          active = true;
          if (!Number.isFinite(points[index - 1]?.[key]) && !Number.isFinite(points[index + 1]?.[key])) {
            svg.append(svgNode("circle", { cx: x(index), cy: y(point[key]), r: 3, fill: colors[key] }));
          }
        });
        svg.append(svgNode("path", { d: path, fill: "none", stroke: colors[key], "stroke-width": 2.5, "stroke-linejoin": "round", "vector-effect": "non-scaling-stroke", ...(key === "target" ? { "stroke-dasharray": "7 5" } : key === "projected" ? { "stroke-dasharray": "3 4" } : {}) }));
      }
      const cursor = svgNode("line", { x1: right, x2: right, y1: top, y2: bottom, stroke: "var(--secondary-text-color,#66788a)", "stroke-dasharray": "4 5" });
      svg.append(cursor); cursors.push(cursor); svgs.push(svg); section.append(svg);
    });
    const output = node("output", null, "tip");
    const scrub = node("input", null, "scrub");
    scrub.type = "range"; scrub.min = "0"; scrub.max = String(points.length - 1); scrub.value = scrub.max;
    scrub.setAttribute("aria-label", this.t("selectDate"));
    const show = index => {
      const point = points[index];
      this._chartDate = point.date;
      output.textContent = `${this.day(point.date)} · ${keys.filter(key => Number.isFinite(point[key])).map(key => `${keyLabel(key)}: ${this.money(point[key])}`).join(" · ")}`;
      for (const cursor of cursors) { cursor.setAttribute("x1", x(index)); cursor.setAttribute("x2", x(index)); }
      scrub.value = String(index); scrub.setAttribute("aria-valuetext", output.textContent);
    };
    scrub.addEventListener("input", () => show(Number(scrub.value)));
    for (const svg of svgs) svg.addEventListener("pointermove", event => {
      const rectangle = svg.getBoundingClientRect();
      const fraction = ((event.clientX - rectangle.left) / rectangle.width * width - left) / (right - left);
      const targetTime = firstTime + Math.max(0, Math.min(1, fraction)) * (lastTime - firstTime);
      let low = 0, high = times.length - 1;
      while (low < high) { const middle = Math.floor((low + high) / 2); if (times[middle] < targetTime) low = middle + 1; else high = middle; }
      const previous = Math.max(0, low - 1), nearest = Math.abs(times[low] - targetTime) < Math.abs(times[previous] - targetTime) ? low : previous;
      show(nearest);
    });
    const selected = points.findIndex(point => point.date === this._chartDate);
    show(selected < 0 ? points.length - 1 : selected);
    section.append(output, scrub, node("p", this.t("closeHint"), "hint"));
  }
  _renderSummary(parent) {
    const section = node("section", null, "card"), controls = node("div", null, "controls");
    controls.append(node("h2", this.t("overview")), node("div", null, "grow"));
    for (const [key, label] of [["monthly", "monthlyOverview"], ["yearly", "yearlyOverview"]]) controls.append(button(this.t(label), () => { this._summaryPeriod = key; this._render(); }, this._summaryPeriod === key ? "active" : ""));
    section.append(controls);
    const source = this._position === "all" ? this._history.summaries?.wallet : this._history.summaries?.positions?.[this._position];
    const rows = [...(source?.[this._summaryPeriod] || [])].reverse();
    const wrap = node("div", null, "tablewrap"), table = node("table"), head = node("thead"), hr = node("tr");
    const flowKey = this._position === "all" ? "depositsLabel" : "purchaseCost";
    for (const key of ["period", flowKey, "dividends", "profit", "returnLabel", "endValue"]) hr.append(node("th", this.t(key), key === "period" ? "" : "num"));
    head.append(hr); table.append(head); const body = node("tbody");
    for (const row of rows) {
      let label;
      if (row.period.length === 4) label = row.period;
      else label = new Intl.DateTimeFormat(this._lang, { month: "long", year: "numeric" }).format(new Date(`${row.period}-15T12:00:00`));
      const flow = this._position === "all" ? row.deposits : row.purchases;
      const tr = node("tr"), cls = value => `num ${value > 0 ? "positive" : value < 0 ? "negative" : ""}`;
      tr.append(node("td", label), node("td", this.money(flow), "num"), node("td", this.money(row.dividends), "num"),
        node("td", this.money(row.gain), cls(row.gain)), node("td", this.percent(row.return), cls(row.return)), node("td", this.money(row.end_value), "num"));
      body.append(tr);
    }
    table.append(body); wrap.append(table); section.append(wrap, node("p", this.t("summaryHint"), "hint"));
    if (!rows.length) this._notice(section, this.t("noRows"));
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
    controls.append(filter);
    section.append(controls);
    const wrap = node("div", null, "tablewrap"), table = node("table"), head = node("thead"), hr = node("tr");
    for (const key of ["date", "type", "symbol", "amount", "units"]) hr.append(node("th", this.t(key), ["amount", "units"].includes(key) ? "num" : ""));
    head.append(hr); table.append(head);
    const body = node("tbody");
    const rows = [...this._history.ledger].reverse().filter(row => (this._type === "all" || row.type === this._type) && (this._position === "all" || row.symbol === this._position));
    for (const row of rows) {
      const tr = node("tr"), dateCell = node("td", this.day(row.date));
      if (row.booking_date && row.booking_date !== row.date) dateCell.append(node("span", `${this.t("booked")}: ${this.day(row.booking_date)}`, "hint"));
      const alias = row.symbol ? this._positionAlias(row.symbol) : "";
      const asset = node("td", alias || row.symbol || row.plan || "—");
      if (alias) asset.append(node("span", row.symbol, "hint"));
      if (row.symbol && row.plan) asset.append(node("span", row.plan, "hint"));
      if (row.note) asset.append(node("span", row.note, "hint"));
      const units = node("td", this.units(row.units), "num");
      if (row.estimated) units.append(node("span", this.t("estimate"), "badge"));
      if (row.price_date && row.price_date !== row.date) units.append(node("span", `${this.t("priceDate")}: ${this.day(row.price_date)}`, "hint"));
      tr.append(dateCell, node("td", this.t(row.type)), asset, node("td", this.money(row.amount), `num ${row.amount > 0 ? "positive" : ""}`), units);
      body.append(tr);
    }
    table.append(body); wrap.append(table); section.append(wrap);
    if (!rows.length) this._notice(section, this.t("noRows"));
    parent.append(section);
  }
  _renderExport(parent) {
    const section = node("section", null, "card");
    section.append(node("h2", this.t("dataExport")), node("p", this.t("dataExportHint"), "hint"));
    const actions = node("div", null, "controls");
    const csv = button(this.t("exportCsv"), () => this._exportCsv());
    csv.disabled = !this._history || this._busy;
    const backup = button(this.t("exportBackup"), () => this._exportBackup(), "primary");
    backup.disabled = this._busy;
    actions.append(csv, backup); section.append(actions); parent.append(section);
  }
  _safeFileName(suffix) {
    const wallet = (this._wallet()?.name || "my-wallet").normalize("NFKD").replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "my-wallet";
    return `${wallet}-${new Date().toLocaleDateString("sv-SE")}.${suffix}`;
  }
  _download(content, type, name) {
    const blob = new Blob([content], { type }), url = URL.createObjectURL(blob), anchor = node("a");
    anchor.href = url; anchor.download = name; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  _exportCsv() {
    const cell = value => {
      let text = String(value ?? "");
      if (typeof value === "string" && /^[=+\-@\t\r]/.test(text)) text = `'${text}`;
      return `"${text.replaceAll('"', '""')}"`;
    };
    const rows = [["date", "type", "symbol", "alias", "plan", "amount", "currency", "units", "estimated", "price_date", "note"], ...this._history.ledger.map(row => [row.date, row.type, row.symbol, row.symbol ? this._positionAlias(row.symbol) : "", row.plan, row.amount, this._wallet().currency, row.units, row.estimated ?? false, row.price_date, row.note])];
    this._download("\uFEFF" + rows.map(row => row.map(cell).join(";")).join("\r\n"), "text/csv;charset=utf-8", this._safeFileName("csv"));
  }
  async _exportBackup() {
    if (this._busy || !this._selected) return;
    this._busy = true; this._error = null; this._render();
    try {
      const result = await this._call("backup", { entry_id: this._selected });
      this._download(JSON.stringify(result.document, null, 2), "application/json;charset=utf-8", this._safeFileName("json"));
    } catch (err) { this._error = this._errorText(err); }
    finally { this._busy = false; this._render(); }
  }
  _renderImport(parent) {
    const section = node("section", null, "card");
    section.append(node("h2", this.t("import")));
    const mode = node("select");
    for (const [value, key] of [["followup", "followup"], ["new", "createNew"]]) {
      if (value === "followup" && (!this._wallet() || this._document?.format === "my_wallet_backup")) continue;
      const option = node("option", this.t(key)); option.value = value; option.selected = value === this._importMode; mode.append(option);
    }
    mode.addEventListener("change", () => { this._importMode = mode.value; this._preview = null; this._importDecisions = {}; this._render(); });
    const field = node("div", null, "field"); field.append(node("label", this.t("importMode")), mode); section.append(field);
    section.append(node("p", this.t(this._document?.format === "my_wallet_backup" ? "backupImportHint" : this._importMode === "followup" ? "followupHint" : "importHint"), "hint"));
    const file = node("input");
    file.type = "file"; file.accept = ".json,application/json"; file.disabled = this._busy;
    file.setAttribute("aria-label", this.t("import"));
    file.addEventListener("change", async () => {
      const selected = file.files[0];
      if (!selected) return;
      try {
        if (selected.size > 2000000) throw new Error("size");
        this._document = JSON.parse(await selected.text());
        if (this._document?.format === "my_wallet_backup") this._importMode = "new";
        this._preview = null;
        this._importDecisions = {};
        await this._prepareImport();
      } catch { this._error = this.t("invalid_import"); this._render(); }
    });
    section.append(file);
    if (this._preview) {
      const summary = this._preview.summary;
      section.append(node("h3", summary.backup ? `${this.t("backupRestore")}: ${summary.wallet_name}` : this._importMode === "followup" ? `${this.t("followup")}: ${this._wallet().name}` : `${this.t("newWallet")}: ${summary.wallet_name}`));
      section.append(node("p", `${this.t("counts")}: ${summary.deposits} / ${summary.purchases} / ${summary.dividends}`));
      const stats = node("div", null, "stats");
      for (const [key, value] of [["invested", summary.capital], ["spending", summary.spending], ["dividends", summary.dividend_total], ["cash", summary.cash]]) this._stat(stats, this.t(key), this.money(value, summary.currency));
      section.append(stats);
      if (summary.mode === "followup") {
        const added = summary.added;
        const result = node("div", null, "notice");
        result.append(node("strong", `${this.t("added")}: ${this.t("depositsPlural")} ${added.deposits} · ${this.t("purchasesPlural")} ${added.purchases} · ${this.t("dividends")} ${added.dividends}`));
        result.append(node("p", `${this.t("updated")}: ${summary.updated} · ${this.t("unchanged")}: ${summary.unchanged} · ${this.t("protected")}: ${summary.protected.length} · ${this.t("assets")}: +${added.assets} · ${this.t("plans")}: +${added.plans}`));
        section.append(result);
      }
      if (summary.estimated) this._notice(section, this.t("estimated"));
      this._renderPlans(section, summary.plans, summary.currency);
      if (summary.choices?.length) {
        section.append(node("h3", this.t("decisions")));
        for (const choice of summary.choices) {
          const wrapper = node("div", null, "decision"); wrapper.append(node("strong", choice.id));
          const select = node("select"), prompt = node("option", this.t(choice.kind === "protected" ? "protected" : "chooseMatch"));
          prompt.value = ""; prompt.disabled = true; prompt.selected = !this._importDecisions?.[choice.id]; select.append(prompt);
          if (choice.kind === "protected") {
            for (const [value, key] of [["keep", "keepExisting"], ["merge", "mergeIncoming"]]) { const option = node("option", this.t(key)); option.value = value; option.selected = this._importDecisions?.[choice.id] === value; select.append(option); }
          } else {
            for (const optionData of choice.options) { const option = node("option", typeof optionData === "string" ? optionData : `${this.day(optionData.date)} · ${this.money(optionData.amount)}`); option.value = typeof optionData === "string" ? optionData : optionData.id; option.selected = this._importDecisions?.[choice.id] === option.value; select.append(option); }
            const add = node("option", this.t("addSeparate")); add.value = "add"; select.append(add);
          }
          select.addEventListener("change", () => { this._importDecisions = { ...this._importDecisions, [choice.id]: select.value }; });
          wrapper.append(select); section.append(wrapper);
        }
        const retry = button(this.t("preview"), () => this._prepareImport(), "primary"); retry.disabled = this._busy; section.append(retry);
      } else if (summary.missing.length) {
        this._notice(section, this.t("missing"), "warning");
        for (const row of summary.missing) {
          const wrapper = node("label", null, "missing-row");
          wrapper.append(node("span", `${this.day(row.date)} · ${this._positionLabel(row.symbol)} · ${this.money(row.amount, summary.currency)}`));
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
        const label = node("label", this.t(summary.backup ? "backupCheck" : this._importMode === "followup" ? "followupCheck" : "confirmCheck")), check = node("input");
        check.type = "checkbox";
        label.prepend(check); section.append(label);
        const confirm = button(this.t(summary.backup ? "backupRestore" : this._importMode === "followup" ? "followupConfirm" : "confirm"), () => this._commitImport(), "primary");
        confirm.disabled = true;
        check.addEventListener("change", () => { confirm.disabled = !check.checked || this._busy; });
        const actions = node("div", null, "controls");
        actions.append(confirm); section.append(actions);
      }
    }
    const actions = node("div", null, "controls");
    if (this._document && !this._preview?.summary?.choices?.length) { const preview = button(this.t("preview"), () => this._prepareImport()); preview.disabled = this._busy; actions.append(preview); }
    const cancel = button(this.t("cancel"), () => { this._document = null; this._preview = null; this._importDecisions = {}; this._importOpen = false; this._error = null; this._render(); });
    cancel.disabled = this._busy; actions.append(cancel); section.append(actions);
    parent.append(section);
  }
  async _prepareImport() {
    if (this._busy) return;
    this._busy = this._importBusy = true; this._error = null; this._preview = null; this._render();
    try { this._preview = await this._call("import_preview", { document: this._document, ...(this._importMode === "followup" ? { entry_id: this._selected } : {}), decisions: this._importDecisions || {} }); }
    catch (err) { this._error = this._errorText(err); }
    finally { this._busy = this._importBusy = false; this._render(); }
  }
  async _commitImport() {
    if (this._busy || !this._preview?.token) return;
    this._busy = this._importBusy = true; this._error = null; this._render();
    try {
      const result = await this._call("import_commit", { token: this._preview.token, confirm: true });
      this._selected = result.entry_id; this._document = this._preview = null; this._importDecisions = {}; this._importOpen = false;
    } catch (err) { this._error = this._errorText(err); }
    finally { this._busy = this._importBusy = false; this._render(); }
    if (!this._importOpen) await this._refresh();
  }
}

if (!customElements.get("my-wallet-panel")) customElements.define("my-wallet-panel", MyWalletPanel);
