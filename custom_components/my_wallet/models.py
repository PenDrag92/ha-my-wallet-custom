"""Computed wallet state shared by the coordinator and sensor platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .yahoo import Quote


@dataclass
class ValorData:
    """Computed state for a single market instrument inside the wallet."""

    symbol: str
    amount: float
    opening_amount: float
    quote: Quote | None = None
    fx_rate: float | None = None
    error: str | None = None
    target_share: float | None = None

    @property
    def available(self) -> bool:
        """Return whether both quote and currency conversion are available."""
        return self.quote is not None and self.fx_rate is not None

    @property
    def value(self) -> float | None:
        """Return the position value converted to the wallet base currency."""
        if not self.available:
            return None
        return self.amount * self.quote.price * self.fx_rate

    @property
    def has_target(self) -> bool:
        """Return whether a positive target allocation is configured."""
        return self.target_share is not None and self.target_share > 0


@dataclass
class WalletData:
    """Result of one coordinator update.

    Aggregate portfolio values are deliberately unavailable when any configured
    position is missing.  Returning a partial total would turn a temporary Yahoo
    failure into a false portfolio loss and corrupt profit/XIRR statistics.
    Individual position sensors remain available independently.
    """

    valors: dict[str, ValorData] = field(default_factory=dict)
    pending_executions: list[dict[str, Any]] = field(default_factory=list)
    cash_balance: float = 0.0

    @property
    def all_available(self) -> bool:
        """Return whether at least one position exists and all are available."""
        return bool(self.valors) and all(
            valor.available for valor in self.valors.values()
        )

    @property
    def securities_total(self) -> float | None:
        """Return the complete securities total, never a partial total."""
        if not self.all_available:
            return None
        return sum(valor.value or 0.0 for valor in self.valors.values())

    @property
    def total(self) -> float | None:
        """Return complete securities plus settlement cash."""
        securities = self.securities_total
        return securities + self.cash_balance if securities is not None else None
