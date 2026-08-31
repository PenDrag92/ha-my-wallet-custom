"""Constants for the My Wallet integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "my_wallet"

PLATFORMS: Final = [Platform.SENSOR]

# Config entry keys
CONF_WALLET_NAME: Final = "wallet_name"
CONF_BASE_CURRENCY: Final = "base_currency"
CONF_SCAN_INTERVAL: Final = "scan_interval"  # minutes
CONF_VALORS: Final = "valors"
# Dated executions and recurring savings plans. ``CONF_INVESTED_AMOUNT`` is
# retained only for migrating config entries created by version 1.
CONF_CONTRIBUTIONS: Final = "contributions"
CONF_SAVINGS_PLANS: Final = "savings_plans"
CONF_DIVIDENDS: Final = "dividends"
CONF_INVESTED_AMOUNT: Final = "invested_amount"  # optional, in base currency

# Valor keys
VALOR_SYMBOL: Final = "symbol"
VALOR_AMOUNT: Final = "amount"
VALOR_TARGET_SHARE: Final = "target_share"  # optional, percent of the wallet

# Contribution keys
CONTRIBUTION_ID: Final = "id"
CONTRIBUTION_DATE: Final = "date"
CONTRIBUTION_AMOUNT: Final = "amount"
CONTRIBUTION_SOURCE: Final = "source"
CONTRIBUTION_PLAN_ID: Final = "plan_id"
CONTRIBUTION_SCHEDULED_DATE: Final = "scheduled_date"
CONTRIBUTION_LOTS: Final = "lots"

# Lot keys (one purchase tranche per symbol and execution)
LOT_ID: Final = "id"
LOT_SYMBOL: Final = "symbol"
LOT_DATE: Final = "date"
LOT_AMOUNT: Final = "amount"
LOT_UNIT_PRICE: Final = "unit_price"
LOT_QUOTE_CURRENCY: Final = "quote_currency"
LOT_FX_RATE: Final = "fx_rate"
LOT_UNITS: Final = "units"
LOT_INCLUDED_IN_OPENING: Final = "included_in_opening"
LOT_ESTIMATED: Final = "estimated"

# Dividend keys. Amounts are the net cash actually credited by the broker.
DIVIDEND_ID: Final = "id"
DIVIDEND_BOOKING_DATE: Final = "booking_date"
DIVIDEND_VALUE_DATE: Final = "value_date"
DIVIDEND_AMOUNT: Final = "amount"
DIVIDEND_SYMBOL: Final = "symbol"
DIVIDEND_NOTE: Final = "note"

# Savings-plan keys
PLAN_ID: Final = "id"
PLAN_NAME: Final = "name"
PLAN_ENABLED: Final = "enabled"
PLAN_FIRST_DATE: Final = "first_date"
PLAN_END_DATE: Final = "end_date"
PLAN_ALLOCATION_MODE: Final = "allocation_mode"
PLAN_AMOUNT: Final = "amount"
PLAN_ALLOCATIONS: Final = "allocations"
PLAN_USE_CASH_BALANCE: Final = "use_cash_balance"
PLAN_OPENING_CUTOFF_DATE: Final = "opening_cutoff_date"
PLAN_SKIPPED_PERIODS: Final = "skipped_periods"
ALLOCATION_SYMBOL: Final = "symbol"
ALLOCATION_VALUE: Final = "value"

ALLOCATION_MODE_PERCENTAGE: Final = "percentage"
ALLOCATION_MODE_FIXED: Final = "fixed"

CONTRIBUTION_SOURCE_MANUAL: Final = "manual"
CONTRIBUTION_SOURCE_PLAN: Final = "savings_plan"
CONTRIBUTION_SOURCE_LEGACY: Final = "legacy"

# Defaults
DEFAULT_BASE_CURRENCY: Final = "EUR"
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 1440

# Service names
SERVICE_REFRESH: Final = "refresh"

# Common currencies offered in the config flow
COMMON_CURRENCIES: Final = [
    "USD",
    "EUR",
    "PLN",
    "GBP",
    "CHF",
    "CAD",
    "AUD",
    "JPY",
    "CZK",
    "NOK",
    "SEK",
    "DKK",
    "HUF",
    "RON",
    "BGN",
    "TRY",
    "INR",
    "CNY",
]

ATTR_SYMBOL: Final = "symbol"
ATTR_AMOUNT: Final = "amount"
ATTR_UNIT_PRICE: Final = "unit_price"
ATTR_QUOTE_CURRENCY: Final = "quote_currency"
ATTR_FX_RATE: Final = "fx_rate"
ATTR_DAY_CHANGE: Final = "day_change"
ATTR_DAY_CHANGE_PCT: Final = "day_change_pct"
ATTR_PREVIOUS_CLOSE: Final = "previous_close"
ATTR_SHORT_NAME: Final = "short_name"
ATTR_VALORS: Final = "valors"
ATTR_INVESTED: Final = "invested"
ATTR_TOTAL: Final = "total"
ATTR_SECURITIES_TOTAL: Final = "securities_total"
ATTR_CASH_BALANCE: Final = "cash_balance"
ATTR_SHARE: Final = "share"
ATTR_TARGET_SHARE: Final = "target_share"
ATTR_SHARE_DEVIATION: Final = "share_deviation"
ATTR_REBALANCE_AMOUNT: Final = "rebalance_amount"
ATTR_VALUE: Final = "value"
ATTR_CONTRIBUTIONS: Final = "contributions"
ATTR_CONTRIBUTION_COUNT: Final = "contribution_count"
ATTR_FIRST_CONTRIBUTION_DATE: Final = "first_contribution_date"
ATTR_LAST_CONTRIBUTION_DATE: Final = "last_contribution_date"
ATTR_LOTS: Final = "lots"
ATTR_PROFIT: Final = "profit"
ATTR_PERFORMANCE_PCT: Final = "performance_pct"
ATTR_ANNUALIZED_PERFORMANCE_PCT: Final = "annualized_performance_pct"
ATTR_TRACKED_INVESTED: Final = "tracked_invested"
ATTR_TRACKED_VALUE: Final = "tracked_value"
ATTR_OPENING_UNITS: Final = "opening_units"
ATTR_TRACKED_UNITS: Final = "tracked_units"
ATTR_SAVINGS_PLANS: Final = "savings_plans"
ATTR_PENDING_EXECUTIONS: Final = "pending_executions"
ATTR_NEXT_EXECUTION_DATE: Final = "next_execution_date"
ATTR_DIVIDENDS: Final = "dividends"
ATTR_DIVIDEND_COUNT: Final = "dividend_count"
ATTR_DIVIDEND_TOTAL: Final = "dividend_total"

# Tolerance when validating the sum of target shares (floating point safety).
TARGET_SHARE_SUM_TOLERANCE: Final = 0.005

UPDATE_MIN_INTERVAL: Final = timedelta(minutes=MIN_SCAN_INTERVAL)
