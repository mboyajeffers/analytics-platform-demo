"""
Abstract base class for industry calculation engines.

Implements the template method pattern for data pipeline execution:
  1. Validate input data (via DataValidator)
  2. Load and normalize columns
  3. Compute KPIs (subclass-specific)
  4. Persist results

Subclasses implement ``compute_kpis()`` and ``get_kpi_definitions()``.
All infrastructure (logging, state management, error isolation) is here.
"""

import logging
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from .validator import DataValidator, ValidationStatus


# =============================================================================
# Engine Result
# =============================================================================

@dataclass
class EngineResult:
    """Result of a single engine execution."""

    success: bool
    kpis_attempted: List[str] = field(default_factory=list)
    kpis_computed: List[str] = field(default_factory=list)
    kpis_failed: List[str] = field(default_factory=list)
    kpi_errors: Dict[str, str] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    completed_at: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "kpis_attempted": self.kpis_attempted,
            "kpis_computed": self.kpis_computed,
            "kpis_failed": self.kpis_failed,
            "kpi_errors": self.kpi_errors,
            "metrics": self.metrics,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "summary": {
                "total_kpis": len(self.kpis_attempted),
                "computed": len(self.kpis_computed),
                "failed": len(self.kpis_failed),
                "success_rate": (
                    len(self.kpis_computed) / len(self.kpis_attempted) * 100
                    if self.kpis_attempted else 0.0
                ),
            },
        }

    def add_kpi_success(self, name: str, value: Any) -> None:
        if name not in self.kpis_attempted:
            self.kpis_attempted.append(name)
        if name not in self.kpis_computed:
            self.kpis_computed.append(name)
        self.metrics[name] = value

    def add_kpi_failure(self, name: str, error: str) -> None:
        if name not in self.kpis_attempted:
            self.kpis_attempted.append(name)
        if name not in self.kpis_failed:
            self.kpis_failed.append(name)
        self.kpi_errors[name] = error


# =============================================================================
# Base Engine
# =============================================================================

class BaseEngine(ABC):
    """Abstract base class for all industry calculation engines.

    Provides:
    - Input validation via DataValidator
    - Column normalisation (lowercase, underscore-separated)
    - KPI computation with per-KPI error isolation
    - Structured result accumulation

    Subclasses must implement:
    - ``compute_kpis()``: call ``_compute_kpi_safe()`` for each KPI
    - ``get_kpi_definitions()``: return list of KPI metadata dicts

    Usage::

        class RevenueEngine(BaseEngine):
            engine_type = "ecommerce"

            def compute_kpis(self):
                self._compute_kpi_safe("total_revenue", self._calc_revenue)
                self._compute_kpi_safe("order_count", self._calc_orders)

            def get_kpi_definitions(self):
                return [
                    {"name": "total_revenue", "unit": "USD"},
                    {"name": "order_count", "unit": "count"},
                ]

            def _calc_revenue(self):
                return float(self.df["amount"].sum())

            def _calc_orders(self):
                return int(self.df["transaction_id"].nunique())

        engine = RevenueEngine(input_df=sales_df)
        result = engine.run()
        print(result.to_dict())
    """

    # Subclasses set this to register with the validator
    engine_type: str = "base"

    def __init__(
        self,
        input_df: Optional[pd.DataFrame] = None,
        input_path: Optional[str] = None,
        job_id: Optional[str] = None,
    ):
        """
        Args:
            input_df: Pre-loaded DataFrame (alternative to input_path).
            input_path: Path to input CSV/Parquet file.
            job_id: Optional identifier for this execution.
        """
        self.input_df = input_df
        self.input_path = input_path
        self.job_id = job_id or f"job-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        self.df: Optional[pd.DataFrame] = None
        self.result: Optional[EngineResult] = None
        self._validator = DataValidator()
        self._logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger(f"engine.{self.engine_type}.{self.job_id}")
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                f"[%(asctime)s] [{self.engine_type}] %(levelname)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    # =========================================================================
    # Template method — public entry point
    # =========================================================================

    def run(self) -> EngineResult:
        """Execute the full pipeline: validate → load → compute → return result.

        Returns:
            EngineResult with KPI values, success flag, and error details.
        """
        self.result = EngineResult(success=False)

        try:
            # Step 1: Load data
            self._logger.info("Loading input data")
            self.df = self._load()
            if self.df is None:
                self.result.error = "Failed to load input data"
                return self.result

            # Step 2: Validate
            self._logger.info(f"Validating {len(self.df)} rows for engine '{self.engine_type}'")
            val_result = self._validator.validate(self.df, self.engine_type)

            if val_result.status == ValidationStatus.FAIL:
                self.result.error = f"Validation failed: {val_result.issues}"
                self._logger.error(self.result.error)
                return self.result

            if val_result.warnings:
                self._logger.warning(f"Validation warnings: {val_result.warnings}")

            # Step 3: Normalize columns
            self.df.columns = (
                self.df.columns.str.lower().str.strip().str.replace(" ", "_", regex=False)
            )

            # Step 4: Compute KPIs
            self._logger.info("Computing KPIs")
            self.compute_kpis()

            self.result.success = len(self.result.kpis_failed) == 0
            self.result.completed_at = datetime.utcnow().isoformat() + "Z"

            self._logger.info(
                f"Completed: {len(self.result.kpis_computed)}/{len(self.result.kpis_attempted)} KPIs"
            )

        except Exception as exc:
            self.result.error = str(exc)
            self._logger.error(f"Engine failed: {exc}")
            self._logger.debug(traceback.format_exc())

        return self.result

    # =========================================================================
    # Abstract interface
    # =========================================================================

    @abstractmethod
    def compute_kpis(self) -> None:
        """Compute all KPIs for this engine.

        Call ``_compute_kpi_safe(name, func)`` for each KPI.
        Failures are isolated — one bad KPI will not abort others.
        """

    @abstractmethod
    def get_kpi_definitions(self) -> List[Dict[str, Any]]:
        """Return metadata for each KPI this engine produces.

        Returns:
            List of dicts with keys: name, description, unit, higher_is_better.
        """

    # =========================================================================
    # Protected helpers
    # =========================================================================

    def _compute_kpi_safe(self, name: str, func: Callable[[], Any]) -> Optional[Any]:
        """Compute a single KPI with full error isolation.

        Args:
            name: KPI identifier (used in results dict and logs).
            func: Zero-argument callable that returns the KPI value.

        Returns:
            Computed value on success, None on failure.
        """
        self._logger.debug(f"Computing: {name}")
        try:
            value = func()
            self.result.add_kpi_success(name, value)
            self._logger.info(f"  {name} = {value}")
            return value
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            self.result.add_kpi_failure(name, error_msg)
            self._logger.error(f"  {name} FAILED: {error_msg}")
            return None

    def _load(self) -> Optional[pd.DataFrame]:
        """Load input into a DataFrame (from df or path)."""
        if self.input_df is not None:
            return self.input_df.copy()

        if self.input_path:
            path = self.input_path
            try:
                if path.endswith(".csv"):
                    return pd.read_csv(path)
                elif path.endswith(".parquet"):
                    return pd.read_parquet(path)
                elif path.endswith((".xlsx", ".xls")):
                    return pd.read_excel(path)
                else:
                    self._logger.error(f"Unsupported format: {path}")
            except Exception as exc:
                self._logger.error(f"Load failed: {exc}")

        return None
