"""
Data quality validator for pre-flight checks before engine processing.

Validates input DataFrames against engine-specific requirements:
- Required columns (with alias resolution)
- Critical column null rates
- Minimum row counts
- Date column parseability
- ISO 4217 currency code validity
- Recommended column completeness

Usage::

    validator = DataValidator()
    result = validator.validate(df, engine_type="finance")

    if result.status == ValidationStatus.FAIL:
        print(result.issues)   # Blocking errors
    elif result.status == ValidationStatus.WARN:
        print(result.warnings) # Non-blocking alerts
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import pandas as pd


# =============================================================================
# Validation Status
# =============================================================================

class ValidationStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class ValidationResult:
    """Result of a validation run."""

    status: ValidationStatus = ValidationStatus.PASS
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    row_count: int = 0
    column_count: int = 0
    validated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    engine_type: str = ""

    def add_issue(self, message: str) -> None:
        """Add a critical issue (causes FAIL)."""
        self.issues.append(message)
        self.status = ValidationStatus.FAIL

    def add_warning(self, message: str) -> None:
        """Add a warning (causes WARN if currently PASS)."""
        self.warnings.append(message)
        if self.status == ValidationStatus.PASS:
            self.status = ValidationStatus.WARN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "issues": self.issues,
            "warnings": self.warnings,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "validated_at": self.validated_at,
            "engine_type": self.engine_type,
        }


# =============================================================================
# Engine Requirements
# =============================================================================

@dataclass
class EngineRequirements:
    """Column and row requirements for a specific engine type."""

    required_columns: Set[str]
    critical_columns: Set[str] = field(default_factory=set)
    recommended_columns: Set[str] = field(default_factory=set)
    date_columns: Set[str] = field(default_factory=set)
    min_rows: int = 10


# Requirements per engine type
ENGINE_REQUIREMENTS: Dict[str, EngineRequirements] = {
    "finance": EngineRequirements(
        required_columns={"account_id", "transaction_date", "amount", "type"},
        critical_columns={"account_id", "amount", "type"},
        recommended_columns={"description", "category", "balance", "currency"},
        date_columns={"transaction_date", "value_date", "posting_date"},
        min_rows=10,
    ),
    "brokerage": EngineRequirements(
        required_columns={"trade_id", "account_id", "trade_date", "symbol", "quantity", "price"},
        critical_columns={"trade_id", "quantity", "price"},
        recommended_columns={"order_type", "commission", "currency", "execution_venue"},
        date_columns={"trade_date", "settlement_date"},
        min_rows=10,
    ),
    "crypto": EngineRequirements(
        required_columns={"timestamp", "asset", "amount"},
        critical_columns={"asset", "amount"},
        recommended_columns={"transaction_type", "price_usd", "fee", "chain"},
        date_columns={"timestamp", "time", "date"},
        min_rows=10,
    ),
    "ecommerce": EngineRequirements(
        required_columns={"transaction_id", "date", "amount", "customer_id"},
        critical_columns={"transaction_id", "amount"},
        recommended_columns={"product_id", "category", "quantity", "discount"},
        date_columns={"date", "order_date", "ship_date"},
        min_rows=10,
    ),
    "betting": EngineRequirements(
        required_columns={"bet_id", "event_date", "stake", "odds", "outcome"},
        critical_columns={"bet_id", "stake", "odds"},
        recommended_columns={"customer_id", "event_type", "sport", "market"},
        date_columns={"event_date", "placed_date", "settled_date"},
        min_rows=10,
    ),
    "gaming": EngineRequirements(
        required_columns={"session_id", "player_id", "game_date", "wager", "payout"},
        critical_columns={"session_id", "wager", "payout"},
        recommended_columns={"game_type", "duration", "platform", "bonus_amount"},
        date_columns={"game_date", "session_start", "session_end"},
        min_rows=10,
    ),
    "oilgas": EngineRequirements(
        required_columns={"date", "volume"},
        critical_columns={"volume"},
        recommended_columns={"well_id", "basin", "price", "unit"},
        date_columns={"date", "prod_date"},
        min_rows=10,
    ),
    "solar": EngineRequirements(
        required_columns={"site_id", "timestamp", "generation_kwh", "irradiance"},
        critical_columns={"site_id", "generation_kwh"},
        recommended_columns={"temperature", "panel_efficiency", "inverter_status"},
        date_columns={"timestamp", "reading_time"},
        min_rows=24,
    ),
    "compliance": EngineRequirements(
        required_columns={"entity_id", "check_date", "check_type", "result"},
        critical_columns={"entity_id", "check_type", "result"},
        recommended_columns={"risk_score", "notes", "reviewer"},
        date_columns={"check_date", "review_date"},
        min_rows=10,
    ),
    "media": EngineRequirements(
        required_columns={"content_id", "event_date", "impressions", "platform"},
        critical_columns={"content_id", "impressions"},
        recommended_columns={"clicks", "spend", "conversions", "campaign_id"},
        date_columns={"event_date", "publish_date"},
        min_rows=10,
    ),
    "weather": EngineRequirements(
        required_columns={"station_id", "observation_time", "temperature", "humidity"},
        critical_columns={"station_id", "temperature"},
        recommended_columns={"pressure", "wind_speed", "precipitation"},
        date_columns={"observation_time", "forecast_time"},
        min_rows=24,
    ),
}

# ISO 4217 currency codes (common subset)
VALID_CURRENCIES: Set[str] = {
    "USD", "EUR", "GBP", "CAD", "CHF", "JPY", "CNY", "AUD", "NZD",
    "HKD", "SGD", "INR", "MXN", "BRL", "ZAR", "SEK", "NOK", "DKK",
    "PLN", "CZK", "HUF", "TRY", "RUB", "KRW", "THB", "MYR", "IDR",
    "PHP", "VND", "AED", "SAR", "ILS", "TWD", "CLP", "COP", "PEN",
}

NULL_THRESHOLD = 0.50   # >50% nulls in critical column = FAIL
MIN_ROWS_ABSOLUTE = 10  # System-wide minimum


class DataValidator:
    """Pre-flight data quality validator.

    Runs engine-specific checks before any computation begins.
    Supports all 11 industry engine types.

    Usage::

        validator = DataValidator()
        result = validator.validate(df=my_dataframe, engine_type="finance")
        print(result.status)   # 'pass', 'warn', or 'fail'
        print(result.issues)   # list of blocking error strings
        print(result.warnings) # list of non-blocking alert strings
    """

    def validate(
        self,
        df: pd.DataFrame,
        engine_type: str,
        job_id: Optional[str] = None,
    ) -> ValidationResult:
        """Validate a DataFrame for a specific engine type.

        Args:
            df: Input DataFrame to validate.
            engine_type: Engine identifier (e.g. 'finance', 'crypto').
            job_id: Optional job identifier for logging.

        Returns:
            ValidationResult with status (pass/warn/fail) and details.
        """
        result = ValidationResult(engine_type=engine_type)
        result.row_count = len(df)
        result.column_count = len(df.columns)

        # Normalize column names for comparison
        norm_cols = set(
            col.lower().strip().replace(" ", "_") for col in df.columns
        )

        requirements = ENGINE_REQUIREMENTS.get(
            engine_type.lower(),
            EngineRequirements(required_columns=set()),
        )

        if engine_type.lower() not in ENGINE_REQUIREMENTS:
            result.add_warning(f"Unknown engine type '{engine_type}' — minimal validation applied")

        self._check_row_count(df, requirements, result)
        self._check_required_columns(norm_cols, requirements, result)
        self._check_recommended_columns(norm_cols, requirements, result)
        self._check_null_rates(df, requirements, result)
        self._check_date_columns(df, requirements, result)
        self._check_currency_column(df, result)

        return result

    # -------------------------------------------------------------------------

    def _check_row_count(
        self, df: pd.DataFrame, req: EngineRequirements, result: ValidationResult
    ) -> None:
        min_rows = max(req.min_rows, MIN_ROWS_ABSOLUTE)
        if len(df) < min_rows:
            result.add_issue(
                f"Insufficient rows: {len(df)} (minimum: {min_rows})"
            )
        elif len(df) < min_rows * 2:
            result.add_warning(
                f"Low row count: {len(df)} (recommended: {min_rows * 2}+)"
            )

    def _check_required_columns(
        self, norm_cols: Set[str], req: EngineRequirements, result: ValidationResult
    ) -> None:
        missing = [c for c in req.required_columns if c.lower() not in norm_cols]
        if missing:
            result.add_issue(f"Missing required columns: {sorted(missing)}")

    def _check_recommended_columns(
        self, norm_cols: Set[str], req: EngineRequirements, result: ValidationResult
    ) -> None:
        missing = [c for c in req.recommended_columns if c.lower() not in norm_cols]
        if missing:
            result.add_warning(f"Missing recommended columns: {sorted(missing)}")

    def _check_null_rates(
        self, df: pd.DataFrame, req: EngineRequirements, result: ValidationResult
    ) -> None:
        df_cols = set(df.columns)
        for col in req.critical_columns:
            if col not in df_cols:
                continue
            null_pct = df[col].isna().mean()
            if null_pct >= NULL_THRESHOLD:
                result.add_issue(
                    f"Column '{col}': {null_pct:.1%} nulls (threshold: {NULL_THRESHOLD:.0%})"
                )
            elif null_pct >= NULL_THRESHOLD / 2:
                result.add_warning(f"Column '{col}': {null_pct:.1%} nulls")

    def _check_date_columns(
        self, df: pd.DataFrame, req: EngineRequirements, result: ValidationResult
    ) -> None:
        df_cols = set(df.columns)
        for col in req.date_columns:
            if col not in df_cols:
                continue
            try:
                parsed = pd.to_datetime(df[col], errors="coerce")
                fail_rate = parsed.isna().mean() - df[col].isna().mean()
                if fail_rate > 0.10:
                    result.add_warning(
                        f"Column '{col}': {fail_rate:.1%} unparseable dates"
                    )
            except Exception:
                result.add_warning(f"Column '{col}': could not validate date format")

    def _check_currency_column(
        self, df: pd.DataFrame, result: ValidationResult
    ) -> None:
        currency_col_names = {
            "currency", "ccy", "currency_code", "transaction_currency",
            "base_currency", "original_currency",
        }
        for col in df.columns:
            if col.lower().strip() not in currency_col_names:
                continue
            unique = df[col].dropna().astype(str).str.upper().str.strip().unique()
            invalid = [v for v in unique if v not in VALID_CURRENCIES]
            if invalid:
                sample = invalid[:5]
                result.add_warning(
                    f"Column '{col}': unrecognised currency codes: {sample}"
                )
