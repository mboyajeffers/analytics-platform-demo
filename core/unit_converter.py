"""
Unit detection and normalisation for enterprise data processing.

Automatically detects mixed units in numeric columns (e.g. watts vs kilowatts,
cents vs dollars, satoshi vs BTC) and converts to a standard base unit.

Design principles:
- Detection-only by default — never mutates input DataFrame silently
- Original columns always preserved alongside normalised versions
- Full audit report before any conversion
- Supports 8 conversion categories covering common enterprise domains

Usage::

    from core.unit_converter import UnitConverter

    converter = UnitConverter()

    # Inspect what would be converted (no changes to df)
    report = converter.audit(df)
    print(report.conversions_needed)

    # Apply conversions (creates new columns, preserves originals)
    normalised = converter.convert(df, report)
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# =============================================================================
# Conversion Definitions
# =============================================================================

ConversionFn = Callable[[pd.Series], pd.Series]

@dataclass
class ConversionSpec:
    """A detected unit with its normalisation function."""

    column: str
    detected_unit: str
    target_unit: str
    category: str
    to_base: ConversionFn


# Supported unit categories with detection heuristics
# Each entry: (category, unit_name, to_base_fn, detection_fn)
#   detection_fn(series) -> bool: returns True if series looks like this unit

_UNIT_DEFINITIONS: List[Tuple[str, str, str, ConversionFn, Callable]] = [
    # Power: Watts (values typically > 1000 for kW-scale systems)
    ("power", "watts", "kilowatts",
     lambda s: s / 1000,
     lambda s: s.median() > 1000),

    # Currency: Cents (integer values around 1000–50000 for typical prices)
    ("currency_usd", "cents", "dollars",
     lambda s: s / 100,
     lambda s: (s % 1 == 0).mean() > 0.95 and s.median() > 500 and s.median() < 100_000),

    # Crypto: Satoshi (BTC smallest unit — very large integers)
    ("crypto_btc", "satoshi", "btc",
     lambda s: s / 1e8,
     lambda s: s.median() > 1_000_000),

    # Temperature: Fahrenheit (values typically 32–120 for US weather)
    ("temperature", "fahrenheit", "celsius",
     lambda s: (s - 32) * 5 / 9,
     lambda s: s.min() > 32 and s.max() < 130 and s.median() > 50),

    # Energy: Watt-hours (values typically > 1000 for kWh-scale)
    ("energy", "wh", "kwh",
     lambda s: s / 1000,
     lambda s: s.median() > 1000 and s.max() > 5000),
]

# Column name keywords for each category
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "power": ["power", "generation", "capacity", "output", "load", "watt"],
    "currency_usd": ["price", "amount", "cost", "revenue", "fee", "value", "spend"],
    "crypto_btc": ["btc", "bitcoin", "satoshi"],
    "temperature": ["temp", "temperature", "heat", "celsius", "fahrenheit"],
    "energy": ["energy", "kwh", "consumption", "usage"],
}


# =============================================================================
# Audit Report
# =============================================================================

@dataclass
class ConversionAudit:
    """Result of auditing a DataFrame for unit inconsistencies."""

    conversions_needed: List[ConversionSpec] = field(default_factory=list)
    columns_checked: List[str] = field(default_factory=list)
    columns_skipped: List[str] = field(default_factory=list)

    @property
    def needs_conversion(self) -> bool:
        return len(self.conversions_needed) > 0

    def summary(self) -> str:
        if not self.conversions_needed:
            return "No unit conversions needed."
        lines = ["Conversions detected:"]
        for spec in self.conversions_needed:
            lines.append(
                f"  {spec.column}: {spec.detected_unit} → {spec.target_unit} "
                f"[{spec.category}]"
            )
        return "\n".join(lines)


# =============================================================================
# Unit Converter
# =============================================================================

class UnitConverter:
    """Detect and normalise unit inconsistencies in enterprise DataFrames.

    Detection is heuristic-based — it uses column name keywords and
    statistical properties of the data (median, distribution) to identify
    likely unit mismatches. Always verify the audit report before applying.

    Usage::

        converter = UnitConverter()

        # Step 1: Inspect (no changes)
        audit = converter.audit(df)
        print(audit.summary())

        # Step 2: Apply (original columns preserved)
        normalised = converter.convert(df, audit)
        # new columns: 'power_kw' (converted), 'power_original' (original)
    """

    def audit(self, df: pd.DataFrame) -> ConversionAudit:
        """Analyse a DataFrame for potential unit mismatches.

        Args:
            df: DataFrame to inspect. Non-numeric columns are skipped.

        Returns:
            ConversionAudit listing detected conversions and checked columns.
        """
        report = ConversionAudit()

        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            report.columns_checked.append(col)
            series = df[col].dropna()
            if len(series) < 5:
                report.columns_skipped.append(col)
                continue

            col_lower = col.lower()

            # Find which category this column might belong to
            matched_category = None
            for category, keywords in _CATEGORY_KEYWORDS.items():
                if any(kw in col_lower for kw in keywords):
                    matched_category = category
                    break

            if matched_category is None:
                continue

            # Check each unit definition for this category
            for cat, unit_name, target, to_base, detect in _UNIT_DEFINITIONS:
                if cat != matched_category:
                    continue
                try:
                    if detect(series):
                        report.conversions_needed.append(ConversionSpec(
                            column=col,
                            detected_unit=unit_name,
                            target_unit=target,
                            category=cat,
                            to_base=to_base,
                        ))
                        break
                except Exception:
                    pass

        return report

    def convert(
        self,
        df: pd.DataFrame,
        audit: Optional[ConversionAudit] = None,
        inplace: bool = False,
    ) -> pd.DataFrame:
        """Apply unit conversions identified in an audit report.

        Args:
            df: DataFrame to normalise.
            audit: Audit result from ``audit()``. If None, runs audit first.
            inplace: If False (default), returns a copy. If True, modifies df.

        Returns:
            DataFrame with converted columns added (originals preserved as
            ``{column}_original``) and converted values in ``{column}``.
        """
        if audit is None:
            audit = self.audit(df)

        result = df if inplace else df.copy()

        for spec in audit.conversions_needed:
            col = spec.column
            if col not in result.columns:
                continue

            # Preserve original
            original_col = f"{col}_original"
            result[original_col] = result[col]

            # Apply conversion
            result[col] = spec.to_base(result[col])

        return result

    def convert_column(
        self,
        series: pd.Series,
        from_unit: str,
        to_unit: str,
    ) -> pd.Series:
        """Convert a single Series from one unit to another.

        Args:
            series: Numeric Series to convert.
            from_unit: Source unit name (e.g. 'watts', 'cents', 'fahrenheit').
            to_unit: Target unit name (must be the base unit for the category).

        Returns:
            Converted Series.

        Raises:
            ValueError: If the unit pair is not supported.
        """
        for _, unit_name, target, to_base, _ in _UNIT_DEFINITIONS:
            if unit_name == from_unit.lower() and target == to_unit.lower():
                return to_base(series)

        raise ValueError(
            f"No conversion defined from '{from_unit}' to '{to_unit}'. "
            f"Supported conversions: {[(u, t) for _, u, t, _, _ in _UNIT_DEFINITIONS]}"
        )
