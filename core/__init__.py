"""
Analytics platform core utilities.

Modules:
    base_engine     - Abstract industry engine (template method pattern)
    validator       - Pre-flight data quality validation (6 check types)
    kpi_utils       - Shared KPI calculation helpers
    unit_converter  - Auto unit detection and normalisation
    etl_orchestrator - Multi-engine pipeline coordinator
"""

from .base_engine import BaseEngine, EngineResult
from .validator import DataValidator, ValidationResult, ValidationStatus
from .kpi_utils import KPICalculator
from .unit_converter import UnitConverter
from .etl_orchestrator import ETLOrchestrator, OrchestrationResult

__all__ = [
    "BaseEngine",
    "EngineResult",
    "DataValidator",
    "ValidationResult",
    "ValidationStatus",
    "KPICalculator",
    "UnitConverter",
    "ETLOrchestrator",
    "OrchestrationResult",
]
