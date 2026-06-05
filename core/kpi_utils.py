"""
Shared KPI calculation utilities.

Provides pandas-safe calculation helpers used across all industry engines.
All methods handle edge cases (empty series, division by zero, all-NaN)
and return typed scalars rather than Series objects.

Usage::

    calc = KPICalculator(df)

    total = calc.sum("revenue")              # → float
    growth = calc.growth_rate("revenue")     # → float (period-over-period %)
    vol = calc.rolling_volatility("return")  # → float (latest rolling std)
    anomalies = calc.flag_anomalies("value") # → Series[bool]
"""

from typing import List, Optional

import numpy as np
import pandas as pd


class KPICalculator:
    """Shared KPI computation utilities for industry engines.

    Wraps a DataFrame and provides safe calculation methods that:
    - Return None (not NaN) when computation is impossible
    - Guard against zero-division
    - Round outputs to a configurable number of decimal places

    Usage::

        calc = KPICalculator(df, decimals=4)
        revenue = calc.sum("amount")
        growth = calc.growth_rate("revenue", periods=1)
        vol = calc.rolling_volatility("daily_return", window=21)
    """

    def __init__(self, df: pd.DataFrame, decimals: int = 4):
        self._df = df
        self._decimals = decimals

    def sum(self, column: str) -> Optional[float]:
        """Sum of a numeric column, ignoring NaN."""
        return self._safe_scalar(self._df[column].sum() if column in self._df.columns else None)

    def mean(self, column: str) -> Optional[float]:
        """Mean of a numeric column."""
        return self._safe_scalar(self._df[column].mean() if column in self._df.columns else None)

    def median(self, column: str) -> Optional[float]:
        """Median of a numeric column."""
        return self._safe_scalar(self._df[column].median() if column in self._df.columns else None)

    def count_distinct(self, column: str) -> Optional[int]:
        """Count of unique non-null values."""
        if column not in self._df.columns:
            return None
        return int(self._df[column].nunique())

    def null_rate(self, column: str) -> Optional[float]:
        """Fraction of null values in a column."""
        if column not in self._df.columns:
            return None
        return round(float(self._df[column].isna().mean()), self._decimals)

    def growth_rate(self, column: str, periods: int = 1) -> Optional[float]:
        """Period-over-period percentage growth.

        Compares the most recent non-null value to ``periods`` rows ago.
        Returns None if insufficient data or prior value is zero.

        Args:
            column: Column name.
            periods: Number of rows to look back.

        Returns:
            Growth rate as a decimal (0.05 = 5% growth), or None.
        """
        if column not in self._df.columns:
            return None
        series = self._df[column].dropna()
        if len(series) <= periods:
            return None
        current = series.iloc[-1]
        prior = series.iloc[-(periods + 1)]
        if prior == 0:
            return None
        return self._safe_scalar((current - prior) / abs(prior))

    def rolling_volatility(
        self,
        column: str,
        window: int = 21,
        annualise: bool = False,
        trading_days: int = 252,
    ) -> Optional[float]:
        """Rolling standard deviation of a column (latest value).

        Args:
            column: Column name (typically log returns).
            window: Rolling window in rows.
            annualise: Multiply by sqrt(trading_days) if True.
            trading_days: Number of trading days per year.

        Returns:
            Latest rolling std dev value, or None.
        """
        if column not in self._df.columns:
            return None
        series = self._df[column].dropna()
        if len(series) < window:
            return None
        vol = float(series.rolling(window).std().iloc[-1])
        if annualise:
            vol *= np.sqrt(trading_days)
        return self._safe_scalar(vol)

    def sharpe_ratio(
        self,
        return_col: str,
        risk_free_rate: float = 0.05,
        window: int = 252,
    ) -> Optional[float]:
        """Annualised Sharpe ratio over the most recent ``window`` rows.

        Args:
            return_col: Column of daily returns (as decimals, e.g. 0.01 = 1%).
            risk_free_rate: Annual risk-free rate.
            window: Rolling window in trading days.

        Returns:
            Sharpe ratio, or None if insufficient data.
        """
        if return_col not in self._df.columns:
            return None
        returns = self._df[return_col].dropna().tail(window)
        if len(returns) < 2:
            return None
        daily_rf = risk_free_rate / 252
        excess = returns - daily_rf
        vol = excess.std()
        if vol == 0 or np.isnan(vol):
            return None
        return self._safe_scalar((excess.mean() / vol) * np.sqrt(252))

    def max_drawdown(self, price_col: str) -> Optional[float]:
        """Maximum drawdown from peak for a price series.

        Returns:
            Maximum drawdown as a negative decimal (-0.20 = -20%), or None.
        """
        if price_col not in self._df.columns:
            return None
        prices = self._df[price_col].dropna()
        if len(prices) < 2:
            return None
        rolling_max = prices.cummax()
        drawdown = (prices - rolling_max) / rolling_max
        return self._safe_scalar(float(drawdown.min()))

    def percentile(self, column: str, q: float) -> Optional[float]:
        """Return the q-th percentile (0–100) of a column."""
        if column not in self._df.columns:
            return None
        return self._safe_scalar(float(np.nanpercentile(self._df[column].dropna(), q)))

    def flag_anomalies(
        self,
        column: str,
        method: str = "iqr",
        threshold: float = 1.5,
    ) -> pd.Series:
        """Flag statistical anomalies in a column.

        Args:
            column: Column to analyse.
            method: 'iqr' (interquartile range) or 'zscore'.
            threshold: IQR multiplier or z-score cutoff.

        Returns:
            Boolean Series (True = anomaly). Empty Series if column missing.
        """
        if column not in self._df.columns:
            return pd.Series(dtype=bool)

        series = self._df[column]

        if method == "iqr":
            q25, q75 = series.quantile(0.25), series.quantile(0.75)
            iqr = q75 - q25
            lower, upper = q25 - threshold * iqr, q75 + threshold * iqr
            return (series < lower) | (series > upper)

        elif method == "zscore":
            mean, std = series.mean(), series.std()
            if std == 0:
                return pd.Series(False, index=self._df.index)
            z = (series - mean) / std
            return z.abs() > threshold

        raise ValueError(f"Unknown method: {method}. Use 'iqr' or 'zscore'.")

    def compound_growth_rate(
        self,
        column: str,
        periods: Optional[int] = None,
    ) -> Optional[float]:
        """Compound annual growth rate (CAGR).

        Args:
            column: Column of values (must be positive).
            periods: Number of periods. Defaults to full series length.

        Returns:
            CAGR as a decimal (0.12 = 12% per period), or None.
        """
        if column not in self._df.columns:
            return None
        series = self._df[column].dropna()
        n = periods or len(series) - 1
        if n <= 0 or len(series) < n + 1:
            return None
        start = series.iloc[-(n + 1)]
        end = series.iloc[-1]
        if start <= 0:
            return None
        return self._safe_scalar((end / start) ** (1 / n) - 1)

    # -------------------------------------------------------------------------

    def _safe_scalar(self, value) -> Optional[float]:
        """Round and guard against NaN/inf."""
        if value is None:
            return None
        try:
            v = float(value)
            if np.isnan(v) or np.isinf(v):
                return None
            return round(v, self._decimals)
        except (TypeError, ValueError):
            return None
