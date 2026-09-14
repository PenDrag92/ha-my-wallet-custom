/* Stable domain codes have user-facing explanations; provider text stays plain text. */
const german = {
  missing_market_data: "Für die Gesamtbewertung fehlen Kurse oder Wechselkurse.",
  invalid_market_data: "Die vorhandenen Marktdaten sind nicht für eine Bewertung geeignet.",
  refresh_failed: "Der letzte Kursabruf ist fehlgeschlagen. Bitte die Kurse aktualisieren.",
  incomplete_opening_cost: "Für den Anfangsbestand fehlen Kaufdaten. Gesamtkosten und Gesamtgewinn dieser Position sind deshalb unbekannt.",
  allocation_deviation: "Der Depotanteil weicht um mindestens fünf Prozentpunkte von deinem Ziel ab.",
  large_quote_change: "Der Kurs weicht um mindestens 20 % vom vorherigen Schlusskurs ab. Prüfe den Kurs und mögliche Kapitalmaßnahmen.",
  opening_units_conflict: "Die als Anfangsbestand erfassten Käufe übersteigen die eingetragene Anfangsstückzahl.",
  historical_cash_deficit: "Im Buchungsverlauf fehlt zeitweise die Finanzierung. Prüfe die Einzahlungen und Buchungsdaten.",
  estimated_purchases: "Einige Käufe enthalten geschätzte Kurse oder Stückzahlen.",
  possible_duplicate_purchase: "Mehrere Käufe haben gleiche Daten, Beträge und Stückzahlen. Prüfe die Belege; es können eigenständige Käufe sein.",
  unassigned_dividends: "Einige Dividenden sind keiner Position zugeordnet. Sie zählen zum Depot, aber nicht zum Gewinn einer bestimmten Position.",
  targets_missing: "Trage zunächst Zielanteile für deine Positionen ein.",
  partial_targets: "Deine Ziele beschreiben nur einen Teil des Depots. Der übrige Anteil wird nicht automatisch anderen Positionen zugewiesen.",
  pending_plan_executions: "Sparplanausführungen warten noch auf vollständige Daten.",
  invalid_targets: "Die konfigurierten Zielanteile sind nicht gültig.",
  cash_deficit: "Das erfasste Verrechnungskonto hat einen Fehlbetrag. Prüfe zunächst die Buchungen.",
  invalid_number: "Bitte eine Zahl mit Komma oder Punkt als Dezimaltrennzeichen eingeben.",
  invalid_scenario_date: "Start- und Pausendatum müssen zwischen heute und dem Ende des Szenarios liegen.",
  invalid_scenario_years: "Der Zeitraum muss eine ganze Zahl zwischen 1 und 50 Jahren sein.",
  invalid_scenario_amount: "Bitte einen gültigen, nicht negativen Betrag eingeben.",
  invalid_scenario_return: "Die Renditeannahme liegt außerhalb des unterstützten Bereichs.",
  scenario_plan_required: "Wähle für eine neue Monatsrate zuerst einen Sparplan.",
  invalid_scenario_plan: "Der ausgewählte Sparplan ist nicht mehr vorhanden.",
  invalid_allocation_amount: "Bitte einen nicht negativen Geldbetrag mit höchstens zwei Nachkommastellen eingeben.",
  external_consent_required: "Bestätige zunächst die Übertragung an den ausgewählten Anbieter.",
  assistant_agent_not_configured: "Der Assistent ist für dieses Depot nicht passend eingerichtet. Aktualisiere die Auswahl und prüfe die Wallet-API.",
  assistant_provider_failed: "Der Gesprächsanbieter konnte die Anfrage nicht beantworten. Bitte erneut versuchen.",
  assistant_empty_response: "Der Gesprächsanbieter hat keine Antwort zurückgegeben.",
  assistant_session_expired: "Das Gespräch ist abgelaufen. Beginne ein neues Gespräch.",
  assistant_session_limit: "Es sind bereits mehrere Gespräche aktiv. Bitte später erneut versuchen.",
  assistant_busy: "Eine Antwort für dieses Gespräch wird noch erstellt.",
  entry_changed: "Das Depot wurde inzwischen geändert. Bitte die Vorschau erneut erstellen.",
  document_ai_consent_required: "Bestätige zunächst die Übertragung des Dokumenttexts zur Erkennung.",
  document_ai_task_required: "Wähle eine eingerichtete AI-Task-Entität für die PDF-Erkennung.",
  document_busy: "Ein Dokument wird bereits geprüft.",
  document_expired: "Die Dokumentvorschau ist abgelaufen. Bitte das Dokument erneut prüfen.",
  document_extraction_failed: "Das PDF konnte nicht erkannt werden. Prüfe die gewählte AI-Task-Entität.",
  document_too_large: "Das Dokument überschreitet die unterstützte Größe oder Seitenzahl.",
  document_ocr_required: "Mindestens eine PDF-Seite enthält keinen lesbaren Text. Für einen Scan wird zunächst OCR benötigt.",
  encrypted_document_pdf: "Das PDF ist verschlüsselt. Verwende eine unverschlüsselte Kopie.",
  document_source_required: "Gib ein Quellenlabel für diese und spätere Abrechnungen ein.",
  document_source_not_found: "Die angegebene Belegstelle wurde im Dokument nicht gefunden.",
  empty_document: "Das Dokument enthält keine erkennbaren Buchungen.",
  invalid_document: "Das Dokument konnte nicht geprüft werden.",
  invalid_document_pdf: "Die Datei ist kein unterstütztes PDF.",
  invalid_document_csv_columns: "Die CSV-Spalten passen nicht zum My-Wallet-Ereignisformat. Verwende die Beispieldatei aus der Dokumentation.",
  invalid_document_csv_row: "Eine CSV-Zeile enthält eine falsche Anzahl von Feldern.",
  invalid_document_csv: "Die CSV-Datei kann nicht gelesen werden.",
  duplicate_or_missing_document_id: "Mindestens eine Buchungsreferenz fehlt oder wird innerhalb der Datei mehrfach verwendet.",
  incomplete_extraction: "Die Erkennung ist unvollständig. Prüfe das Dokument und ergänze fehlende Buchungen über den üblichen Buchungsweg.",
  unsupported_event_type: "Diese Buchungsart wird vom Import noch nicht unterstützt.",
  future_date: "Eine tatsächliche Buchung darf kein zukünftiges Datum haben.",
  iso_date_required: "Das Datum muss im Format JJJJ-MM-TT vorliegen.",
  positive_decimal_required: "Ein positiver Betrag bzw. eine positive Stückzahl mit Dezimalpunkt ist erforderlich.",
  possible_duplicate_requires_choice: "Eine ähnliche Buchung existiert bereits. Wähle die Zuordnung oder kennzeichne diese als eigenen Vorgang.",
  source_record_conflicts_with_wallet: "Diese Referenz ist bereits erfasst, aber die Angaben weichen ab. Prüfe die vorhandene Buchung.",
  source_record_was_removed: "Die zuvor zugeordnete Buchung wurde entfernt. Prüfe den Vorgang vor einer erneuten Übernahme.",
  invalid_or_reused_match: "Diese Zuordnung ist ungültig oder wird bereits für eine andere Zeile verwendet.",
  value_not_in_source: "Dieser Wert ist in der Belegstelle nicht nachweisbar. Prüfe und korrigiere ihn anhand der Abrechnung.",
  wallet_currency_required: "Die Währung muss mit der Depotwährung übereinstimmen.",
  existing_wallet_symbol_required: "Wähle das technische Kürzel einer bereits im Depot angelegten Position.",
  only_dividends_supported: "Ein Valutadatum ist hier nur für Dividenden vorgesehen.",
  only_purchases_supported: "Stückzahlen sind hier nur für Käufe vorgesehen.",
  deposit_has_no_symbol: "Eine externe Einzahlung hat keine Wertpapierzuordnung.",
  insufficient_cash: "Die Buchungen sind im historischen Verlauf nicht vollständig durch Guthaben gedeckt.",
};

export function explain(code, lang, fallback = code) {
  if (lang === "de" && typeof code === "string" && code.includes(": ")) {
    const [field, detail] = code.split(": ", 2);
    const labels = { type: "Buchungsart", date: "Datum", amount: "Betrag", units: "Anteile", currency: "Währung", symbol: "Wertpapier", value_date: "Valutadatum" };
    return (labels[field] || field) + ": " + (german[detail] || detail);
  }
  return lang === "de" ? german[code] || fallback : fallback;
}

export function assumptionNotes(result, lang) {
  if (lang !== "de") return result.assumptions || [];
  if (result.method === "actual_value_with_dated_external_funding") return [
    "Ausgangspunkt sind der heutige Wert aller Positionen und das Verrechnungsguthaben.",
    "Die Basis berücksichtigt künftige Einzahlungen sowie die vorhandenen Sparpläne mit ihren Ausführungstagen, Änderungen und übersprungenen Monaten.",
    "Die konstante Rendite wird täglich auf den gesamten Betrag einschließlich Cash angewendet. Steuern, Gebühren, Inflation und zusätzliche Ausschüttungen sind nicht separat modelliert.",
    "Zusätzliche Monatszahlungen beginnen am gewählten Startdatum und wiederholen sich an diesem Kalendertag. In kurzen Monaten gilt der letzte passende Tag.",
    "Eine geänderte Rate oder Pause betrifft nur die gewählten künftigen Plantermine. Zusätzliche Monatszahlungen laufen auch während einer Planpause.",
    "Das Szenario verändert keine gespeicherten Buchungen oder Sparpläne.",
  ];
  if (result.method === "proportional_target_shortfall") return [
    "Ziele beziehen sich auf das gesamte Depot einschließlich Cash nach der neuen Einzahlung.",
    "Die neue Einzahlung wird zuerst verwendet. Vorhandenes Cash kommt nur bei aktivierter Auswahl hinzu.",
    "Fehlende Ziele und 0-%-Ziele erhalten keine Zuteilung. Teilziele werden nicht auf 100 % hochgerechnet.",
    "Das Budget wird anteilig auf die fehlenden Zielbeträge verteilt. Centreste werden eindeutig zugeteilt, ohne das Budget oder einen Zielbetrag zu überschreiten.",
    "Übriges Geld bleibt auf dem Verrechnungskonto. Die Berechnung ist keine Order; Gebühren und tatsächliche Ausführungskurse sind nicht enthalten.",
  ];
  return result.assumptions || [];
}
