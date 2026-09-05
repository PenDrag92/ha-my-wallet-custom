**Abschlussreview des Umbaus – My Wallet 1.11.1**

Geprüft am 4. September 2026: Änderungen von 1.10.2 (`f5da290`) auf 1.11.0
(`cbffaad`) und die unten beschriebenen Korrekturen für 1.11.1. Der Schwerpunkt
lag auf den neuen gemeinsamen Buchungs-, Speicher- und Bewertungsfunktionen
sowie ihren Aufrufern in Optionen, Panel, Importen und automatischen Sparplänen.

Das Review hat zwei reproduzierbare Regressionen des Umbaus gefunden. Beide sind
in 1.11.1 behoben und durch sechs zusätzliche Tests abgesichert. Im geprüften
Änderungsumfang wurden anschließend keine weiteren blockierenden Fehler gefunden.
Das ist eine Aussage über diesen Prüfumfang, keine Garantie vollständiger
Fehlerfreiheit.

| Befund | Priorität | Auswirkung in 1.11.0 | Status in 1.11.1 |
| --- | --- | --- | --- |
| R1: Importzuordnung nach Listenposition | P1 – hoch | Falsche Quellverknüpfungen, abgelehnte Folgeimporte oder ausgelassene neue Dividenden | Behoben |
| R2: Präzisionsverlust im Cash-Verlauf | P2 – mittel, numerischer Randfall | Ein vollständig gedeckter Kauf kann fälschlich als ungedeckt gelten | Behoben |

**R1: Normalisierung und Importzuordnung verwendeten unterschiedliche Reihenfolgen.**

Die neue Validierung in `history_import.async_prepare_import` sortiert Einzahlungen
und Dividenden nach Datum und ID. `followup_import.add_initial_import_metadata`
und `async_prepare_followup` verbanden diese Daten weiterhin mit der ursprünglichen
Datei über `zip`. Sobald beide Reihenfolgen abwichen, gehörten Quell-ID und
vorbereitete Buchung nicht mehr zusammen. Bei unterschiedlich vielen Käufen pro
Einzahlung konnte zusätzlich die Prüfung gleicher Listenlängen abbrechen.

Die Reproduktion umfasst eine Datei mit Februar vor Januar, alle sechs
Reihenfolgen dreier Buchungen am selben Tag und einen überlappenden Folgeimport,
der geschätzte Stückzahlen bestätigt. Besonders relevant: Bei einer bereits
bekannten Januar-Dividende von 1 EUR und einer neuen Februar-Dividende von 2 EUR
konnte ein rückwärts sortierter Folgeimport die neue Dividende auslassen. Der
resultierende Dividendensaldo blieb bei 1 EUR statt 3 EUR.

Die neue interne Funktion `_source_pairs` verbindet Quell- und vorbereitete
Datensätze über die bereits vorhandenen, aus Importcharge und Quell-ID erzeugten
IDs. Sie prüft die eindeutige und vollständige Zuordnung. Diese Verbindung gilt
für Sparpläne, Einzahlungen, Käufe und Dividenden. Die bestehende Abgleichlogik
behält frühere Buchungs-IDs und den Schutz bestätigter Stückzahlen bei.

Die Korrektur verhindert den Fehler bei neuen Importvorgängen. Bereits durch
1.11.0 falsch gespeicherte Verknüpfungen oder ausgelassene Buchungen werden nicht
automatisch rekonstruiert. Falls mit diesem Zwischenstand bereits importiert
wurde, müssen die betroffenen Ergebnisse mit der Quelldatei abgeglichen werden;
eine unveränderte Datei kann wegen der Import-Duplikaterkennung nicht einfach
erneut eingelesen werden.

**R2: Der laufende Cash-Saldo verlor kleine Restbeträge zwischen Buchungstagen.**

`dividends.cash_balance` summiert alle wirksamen Beträge mit `math.fsum`.
Der in 1.11.0 eingeführte `cash_timeline` reduzierte dagegen nach jedem Tag den
gesamten bisherigen Saldo auf einen einzelnen Float. Dadurch gingen bei stark
unterschiedlichen Betragsgrößen kleine Reste verloren, die ein späterer großer
Kauf sichtbar machte.

Reproduktion: 1.000.000.000 EUR Einzahlung, anschließend 100 Gutschriften von
je 0,01 EUR an verschiedenen Tagen und danach ein Kauf für 1.000.000.001 EUR.
Der vollständige Cash-Saldo beträgt 0 EUR. Der alte Verlauf ergab dagegen
-0,0000009537 EUR und die Buchungsprüfung meldete `cash_conflict`. Die absoluten
Beträge machen dies zu einem Randfall; die Ablehnung ist dennoch falsch.

Der Verlauf bewahrt nun die kleinen Summationsreste über Tagesgrenzen hinweg.
Er benötigt weiterhin einen chronologischen Durchlauf. Die bestehende
Defizittoleranz bleibt unverändert. Tests vergleichen jeden Tagesabschluss mit
der vollständigen Cash-Berechnung, bestätigen den gedeckten Kauf und prüfen,
dass eine fehlende Gutschrift von 0,01 EUR weiterhin zur Ablehnung führt.

**Prüfergebnisse für den korrigierten Stand**

| Prüfung | Ergebnis |
| --- | --- |
| Python-Unittests einschließlich der sechs neuen Regressionstests | 225 bestanden |
| Zusätzliche Tests mit echten Home-Assistant-Sensorklassen | 6 bestanden |
| JavaScript-Tests | 23 bestanden |
| Vergleich bisheriger und neuer Depot-/Sensorbewertungen | 140 synthetische Fälle ohne Abweichung innerhalb der Vergleichstoleranz |
| Echter Home-Assistant-Recorder: Startzustand, Poll-Updates, Buchungsbasis und Lücken | Bestanden |
| Echte Voluptuous-Formularvorgaben | Bestanden |
| Ruff und Formatprüfung | Bestanden |
| Bandit | Keine Befunde |
| JSON/YAML, Python-Kompilierung, reale HA-Imports, JavaScript-Syntax und Git-Whitespace | Bestanden |

Die Bewertungsvergleiche umfassen unterschiedliche Käufe, Bruchstücke, Kurse,
Währungsumrechnung, zugeordnete und unzugeordnete Dividenden, unvollständige
Anfangskosten und vorhandene/fehlende Inflationsdaten. Verglichen wurden
Panelwerte sowie Werte und Attribute von sechs Sensortypen mit einer relativen
Toleranz von `1e-10` und einer absoluten Toleranz von `1e-8`.

Die Tests liefen mit Python 3.14.6, Home Assistant 2026.8.3 und Node.js 24.19.0.
Die gezielten Reproduktionen stehen in `tests/test_refactor_review.py` und laufen
mit `python -m unittest tests.test_refactor_review -v`; die vollständigen
Prüfbefehle stehen in `ARCHITECTURE.md` und `.github/workflows/validate.yml`.

Konfigurationseintragsversion 7, Backupformat 1 und bestehende Entitätskennungen
bleiben erhalten. Die Tests verwendeten synthetische Depot- und Kursdaten; ein
Funktionstest in der persönlichen Home-Assistant-Installation ist noch offen.
Die GitHub-Jobs HACS/Hassfest wurden für diesen lokalen Stand nicht ausgeführt.
Die Änderungen wurden lokal vorbereitet und nicht auf GitHub veröffentlicht.
