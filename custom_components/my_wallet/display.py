"""Localized dynamic labels (form field names live in translations)."""

from collections.abc import Iterable, Mapping
from typing import Any

from . import const as c

MESSAGES = {
    "en": {
        "deposit": "Deposit",
        "purchase": "Purchase",
        "opening": "Opening balance",
        "corrected": "manually corrected",
        "future": "Future executions only",
        "recalculate": "Recalculate automatic executions",
        "historical_price_unavailable": "Waiting for a confirmed Yahoo close",
        "historical_fx_unavailable": "Waiting for a historical exchange rate",
        "included_units_exceeded": "Historical units exceed the entered opening "
        "balance; check the cutoff date and units",
        "allocation_too_small": "An allocation is smaller than one cent",
        "cash_conflict": "Recalculation would leave a later purchase unfunded",
        "entry_changed": "The wallet changed during calculation; please retry",
        "booking_failed": "Calculation failed; existing bookings were preserved",
        "rolled_back": "No bookings were changed because the recalculation could "
        "not be completed safely. Correct the listed issue and "
        "request recalculation again.",
        "cash_history_warning": "The cash history would become negative. Check "
        "whether the funding deposit is already recorded.",
        "estimated": "(estimated)",
        "new_plan": "Create due executions using this plan",
        "opening_balance_conflict": "Opening holdings and included purchase lots "
        "disagree. Automatic plan bookings are paused. Check the opening units "
        "under Edit a valor and the included units under Correct a purchase lot. "
        "Stored quantities were preserved; do not increase them without checking "
        "your statements.",
        "configured_units": "opening units",
        "included_units": "units marked included",
    },
    "de": {
        "deposit": "Einzahlung",
        "purchase": "Kauf",
        "opening": "Anfangsbestand",
        "corrected": "manuell korrigiert",
        "future": "Nur zukünftige Ausführungen",
        "recalculate": "Automatische Ausführungen neu berechnen",
        "historical_price_unavailable": "Bestätigter Yahoo-Schlusskurs fehlt noch",
        "historical_fx_unavailable": "Historischer Wechselkurs fehlt noch",
        "included_units_exceeded": "Historische Anteile übersteigen den "
        "Anfangsbestand; Stichtag und Stückzahlen "
        "prüfen",
        "allocation_too_small": "Ein Einzelbetrag ist kleiner als ein Cent",
        "cash_conflict": "Die Neuberechnung würde einen späteren Kauf ungedeckt lassen",
        "entry_changed": "Das Depot wurde während der Berechnung geändert; bitte "
        "erneut versuchen",
        "booking_failed": "Berechnung fehlgeschlagen; bestehende Buchungen bleiben "
        "erhalten",
        "rolled_back": "Es wurden keine Buchungen geändert, weil die Neuberechnung "
        "nicht sicher abgeschlossen werden konnte. Bitte den "
        "genannten Grund beheben und die Neuberechnung erneut "
        "wählen.",
        "cash_history_warning": "Der Kassenverlauf würde negativ. Prüfe, ob die "
        "zugehörige Einzahlung bereits erfasst ist.",
        "estimated": "(geschätzt)",
        "new_plan": "Fällige Ausführungen dieses neuen Plans nachholen",
        "opening_balance_conflict": "Anfangsbestand und enthaltene Kauftranchen "
        "passen nicht zusammen. Automatische Sparplanbuchungen sind pausiert. "
        "Prüfe die Stückzahlen unter Wertpapier bearbeiten und Kauftranche "
        "korrigieren anhand deiner Abrechnungen. Die gespeicherten Stückzahlen "
        "wurden beibehalten; bitte nicht ungeprüft erhöhen.",
        "configured_units": "Anfangsbestand",
        "included_units": "als enthalten markierte Anteile",
    },
    "pl": {
        "deposit": "Wpłata",
        "purchase": "Zakup",
        "opening": "Saldo początkowe",
        "corrected": "poprawiono ręcznie",
        "future": "Tylko przyszłe wykonania",
        "recalculate": "Przelicz automatyczne wykonania",
        "historical_price_unavailable": "Brak potwierdzonego kursu zamknięcia Yahoo",
        "historical_fx_unavailable": "Brak historycznego kursu walutowego",
        "included_units_exceeded": "Historyczne jednostki przekraczają saldo "
        "początkowe; sprawdź datę i liczbę jednostek",
        "allocation_too_small": "Kwota pozycji jest mniejsza niż jeden cent",
        "cash_conflict": "Przeliczenie pozostawiłoby późniejszy zakup bez pokrycia",
        "entry_changed": "Portfel zmieniono podczas obliczeń; spróbuj ponownie",
        "booking_failed": "Obliczenia nie powiodły się; zachowano dotychczasowe wpisy",
        "rolled_back": "Nie zmieniono wpisów, ponieważ przeliczenie nie mogło "
        "zostać bezpiecznie zakończone. Usuń wskazany problem i "
        "ponów przeliczenie.",
        "cash_history_warning": "Saldo historyczne byłoby ujemne. Sprawdź, czy "
        "wpłata finansująca została już zapisana.",
        "estimated": "(szacowane)",
        "new_plan": "Utwórz należne wykonania nowego planu",
        "opening_balance_conflict": "Saldo początkowe i zakupy oznaczone jako "
        "uwzględnione są niespójne. Automatyczne wykonania są wstrzymane. "
        "Sprawdź liczbę jednostek i transze zakupów na podstawie potwierdzeń. "
        "Zapisane ilości nie zostały zmienione.",
        "configured_units": "jednostki początkowe",
        "included_units": "jednostki oznaczone jako uwzględnione",
    },
    "cs": {
        "deposit": "Vklad",
        "purchase": "Nákup",
        "opening": "Počáteční zůstatek",
        "corrected": "ručně upraveno",
        "future": "Pouze budoucí provedení",
        "recalculate": "Přepočítat automatická provedení",
        "historical_price_unavailable": "Chybí potvrzený závěrečný kurz Yahoo",
        "historical_fx_unavailable": "Chybí historický směnný kurz",
        "included_units_exceeded": "Historické podíly překračují počáteční stav; "
        "ověřte datum a počty",
        "allocation_too_small": "Dílčí částka je menší než jeden cent",
        "cash_conflict": "Přepočet by ponechal pozdější nákup bez krytí",
        "entry_changed": "Portfolio se během výpočtu změnilo; zkuste to znovu",
        "booking_failed": "Výpočet selhal; stávající záznamy zůstaly zachovány",
        "rolled_back": "Žádné záznamy nebyly změněny, protože přepočet nemohl být "
        "bezpečně dokončen. Opravte uvedený problém a spusťte "
        "přepočet znovu.",
        "cash_history_warning": "Historický zůstatek by byl záporný. Ověřte, zda "
        "již byl zaznamenán příslušný vklad.",
        "estimated": "(odhad)",
        "new_plan": "Doplnit splatná provedení nového plánu",
        "opening_balance_conflict": "Počáteční stav a zahrnuté nákupy si "
        "odporují. Automatická provedení jsou pozastavena. Zkontrolujte "
        "počty podílů a nákupní tranše podle výpisů. Uložené počty "
        "zůstaly nezměněny.",
        "configured_units": "počáteční podíly",
        "included_units": "podíly označené jako zahrnuté",
    },
}


def text(key: str, language: str = "en") -> str:
    return MESSAGES.get(language.split("-")[0], MESSAGES["en"]).get(
        key, MESSAGES["en"].get(key, key)
    )


def position_label(valors: Iterable[Mapping[str, Any]], symbol: str) -> str:
    """Return a friendly label while retaining the stable technical symbol."""
    valor = next((item for item in valors if item.get(c.VALOR_SYMBOL) == symbol), None)
    alias = str((valor or {}).get(c.VALOR_ALIAS) or "").strip()
    return f"{alias} ({symbol})" if alias else symbol


def position_options(
    valors: Iterable[Mapping[str, Any]], symbols: Iterable[str] | None = None
) -> list[dict[str, str]]:
    """Build Home Assistant selector options with stable stored values."""
    rows = list(valors)
    selected = (
        list(symbols)
        if symbols is not None
        else [str(item[c.VALOR_SYMBOL]) for item in rows]
    )
    return [
        {"value": symbol, "label": position_label(rows, symbol)} for symbol in selected
    ]
