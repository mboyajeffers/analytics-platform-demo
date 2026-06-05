"""
Multi-engine pipeline orchestrator.

Registers multiple industry engines, runs them in sequence or parallel,
and aggregates telemetry across all executions.

Each engine is registered by name with its class and optional configuration.
The orchestrator handles execution order, error isolation between engines,
and result collection.

Usage::

    from core.etl_orchestrator import ETLOrchestrator
    from engines.finance import FinanceEngine
    from engines.crypto import CryptoEngine

    orch = ETLOrchestrator()
    orch.register("finance", FinanceEngine, input_df=finance_df)
    orch.register("crypto", CryptoEngine, input_df=crypto_df)

    results = orch.run_all()
    for name, result in results.items():
        print(f"{name}: {result.success} — {len(result.kpis_computed)} KPIs")

    summary = orch.summary()
    print(summary)
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Type

from .base_engine import BaseEngine, EngineResult


logger = logging.getLogger("etl.orchestrator")


# =============================================================================
# Orchestration Result
# =============================================================================

@dataclass
class EngineRegistration:
    """A registered engine with its constructor arguments."""
    name: str
    engine_class: Type[BaseEngine]
    kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestrationResult:
    """Aggregated result of running all registered engines."""
    results: Dict[str, EngineResult] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    completed_at: Optional[str] = None
    total_kpis: int = 0
    successful_engines: int = 0
    failed_engines: int = 0

    def summary(self) -> str:
        """Return a concise run summary."""
        lines = [
            f"Orchestration: {self.successful_engines}/{self.successful_engines + self.failed_engines} engines succeeded",
            f"Total KPIs computed: {self.total_kpis}",
        ]
        for name, result in self.results.items():
            status = "OK" if result.success else "FAIL"
            kpis = len(result.kpis_computed)
            lines.append(f"  {name}: [{status}] {kpis} KPIs")
            if result.error:
                lines.append(f"    Error: {result.error}")
        return "\n".join(lines)


# =============================================================================
# ETL Orchestrator
# =============================================================================

class ETLOrchestrator:
    """Coordinate execution of multiple industry engines.

    Engines are registered with a name and their constructor arguments.
    ``run_all()`` executes each engine in registration order, isolating
    failures so a broken engine doesn't abort the others.

    Usage::

        orch = ETLOrchestrator()
        orch.register("finance", FinanceEngine, input_df=df1)
        orch.register("crypto", CryptoEngine, input_df=df2)
        result = orch.run_all()
        print(result.summary())
    """

    def __init__(self):
        self._registry: Dict[str, EngineRegistration] = {}
        self._execution_order: List[str] = []

    def register(
        self,
        name: str,
        engine_class: Type[BaseEngine],
        **kwargs,
    ) -> "ETLOrchestrator":
        """Register an engine for execution.

        Args:
            name: Unique name for this engine run (e.g. 'finance_q1').
            engine_class: BaseEngine subclass to instantiate.
            **kwargs: Constructor arguments passed to engine_class().

        Returns:
            self (for method chaining).

        Raises:
            ValueError: If name is already registered.
        """
        if name in self._registry:
            raise ValueError(f"Engine '{name}' is already registered. Use a unique name.")

        self._registry[name] = EngineRegistration(
            name=name, engine_class=engine_class, kwargs=kwargs
        )
        self._execution_order.append(name)
        logger.info(f"Registered: {name} ({engine_class.__name__})")
        return self

    def unregister(self, name: str) -> "ETLOrchestrator":
        """Remove a registered engine."""
        self._registry.pop(name, None)
        if name in self._execution_order:
            self._execution_order.remove(name)
        return self

    def run_all(
        self,
        stop_on_failure: bool = False,
    ) -> OrchestrationResult:
        """Execute all registered engines in registration order.

        Args:
            stop_on_failure: If True, abort on the first engine failure.
                If False (default), continue and collect all results.

        Returns:
            OrchestrationResult with per-engine results and aggregate stats.
        """
        orch_result = OrchestrationResult()
        total_kpis = 0

        for name in self._execution_order:
            reg = self._registry[name]
            logger.info(f"Starting engine: {name}")
            t0 = time.monotonic()

            try:
                engine = reg.engine_class(**reg.kwargs)
                result = engine.run()

            except Exception as exc:
                logger.error(f"Engine '{name}' failed to initialise: {exc}")
                result = EngineResult(success=False, error=str(exc))

            elapsed = time.monotonic() - t0
            logger.info(
                f"Engine '{name}' finished in {elapsed:.1f}s — "
                f"{'OK' if result.success else 'FAIL'}, "
                f"{len(result.kpis_computed)} KPIs"
            )

            orch_result.results[name] = result
            total_kpis += len(result.kpis_computed)

            if result.success:
                orch_result.successful_engines += 1
            else:
                orch_result.failed_engines += 1
                if stop_on_failure:
                    logger.warning(f"Stopping after failure in '{name}'")
                    break

        orch_result.total_kpis = total_kpis
        orch_result.completed_at = datetime.utcnow().isoformat() + "Z"
        return orch_result

    def run_one(self, name: str) -> EngineResult:
        """Run a single registered engine by name.

        Args:
            name: Engine name as registered.

        Returns:
            EngineResult for that engine.

        Raises:
            KeyError: If name is not registered.
        """
        if name not in self._registry:
            raise KeyError(f"Engine '{name}' not registered. Call register() first.")

        reg = self._registry[name]
        engine = reg.engine_class(**reg.kwargs)
        return engine.run()

    @property
    def registered_engines(self) -> List[str]:
        """Names of all registered engines in execution order."""
        return list(self._execution_order)

    def __repr__(self) -> str:
        names = ", ".join(self._execution_order) or "none"
        return f"ETLOrchestrator([{names}])"
