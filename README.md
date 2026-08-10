> **Archived — consolidated into [Data-Engineering-Portfolio](https://github.com/mboyajeffers/Data-Engineering-Portfolio/tree/main/pipelines/etl_framework).** The `pipelines/etl_framework/` directory there covers the same architecture patterns with production extractors, not just demo abstractions. This repo is kept for history only.

# Analytics Platform Demo

Architecture reference and core utilities from a production analytics platform covering **multiple industry verticals**, **multiple public data source integrations**, and **500+ automated tests**.

This repo demonstrates the platform's architectural patterns and core abstractions — the engine design, data quality framework, KPI utilities, unit conversion system, and pipeline orchestrator. It is intended for technical evaluators and data partners who want to understand what's under the hood.

---

## Platform Architecture

```
[Public APIs]──────────────────>[Extractor Layer]
  Yahoo Finance, FRED, EIA,       Rate-limited, cached,
  CoinGecko, SEC EDGAR, ESPN,     retry with backoff,
  NASA NREL, Open-Meteo,          symbol-by-symbol /
  Steam, CoinGecko, NOAA          offset / page-number /
                                  bulk response patterns
                │
                ▼
        [Transform / Validate]
          Kimball star schema
          Column normalisation
          6-rule quality gates
          Unit auto-detection
                │
         ┌──────┴──────┐
         ▼             ▼
  [Star Schema DB]  [Feature Store]
   dim_/fact_ tables  OHLCV → 17 features
   PostgreSQL         Lookahead-free
                           │
                  ┌────────┴────────┐
                  ▼                 ▼
           [ML / Signal]      [Report Engine]
            Walk-forward        PDF generation
            backtester          KPI dashboards
            Direction clf       Industry templates
                  │
                  ▼
          [Broker / Execution]
           Position sizing
           Risk limits
           Paper trading guard
```

---

## Industry Coverage

Multiple industry verticals are supported. Each vertical has its own engine with industry-specific KPIs, validation rules, and data source integrations.

| Vertical | Key KPIs | Primary Data Sources |
|----------|----------|---------------------|
| Finance | Net interest margin, yield curve slope, macro composite | FRED, Yahoo Finance |
| Brokerage | Sharpe ratio, max drawdown, sector rotation signal | Yahoo Finance |
| Crypto | Market cap dominance, volatility regime, DeFi TVL | CoinGecko |
| Oil & Gas | Production MBBL/D, rig count trend, crack spread | EIA |
| Solar | Capacity factor, LCOE estimate, irradiance forecast | NASA NREL, Open-Meteo |
| Gaming | Player retention, ARPU, session length distribution | Steam |
| Betting | Edge percentage, Kelly fraction, model accuracy | ESPN |
| Media | Content velocity, engagement rate, platform share | Custom |
| Ecommerce | Cart abandonment, CLV estimate, refund rate | Custom |
| Compliance | Alert accuracy, false positive rate, coverage ratio | SEC EDGAR |
| Weather | Forecast accuracy, anomaly detection, climate trend | Open-Meteo, NOAA |

---

## Core Utilities

These modules implement the platform's shared infrastructure. They are the same patterns used across all supported verticals.

### `core/engine_core.py` — Abstract Industry Engine

Abstract base class for all industry calculation engines. Implements the template method pattern: validate → load → normalize → compute → persist.

```python
from core.engine_core import BaseEngine, EngineResult

class FinanceEngine(BaseEngine):
    def compute_kpis(self) -> None:
        self._compute_kpi_safe("yield_curve_slope", self._yield_curve_slope)
        self._compute_kpi_safe("macro_composite", self._macro_composite)
        self._compute_kpi_safe("credit_spread", self._credit_spread)

    def get_kpi_definitions(self):
        return [
            {"name": "yield_curve_slope", "unit": "bps", "description": "10Y minus 2Y spread"},
        ]
```

Key design decisions:
- `_compute_kpi_safe()` wraps each KPI in try/except — one failed KPI never blocks the rest
- State machine tracks job lifecycle: VALIDATING → PROCESSING → COMPLETED / FAILED
- Distributed lock prevents duplicate concurrent runs
- Column mapper normalises variations in input column names

### `core/validator.py` — Data Quality Framework

Pre-flight validation before any engine processes data. Supports each industry type with type-specific column requirements.

```python
from core.validator import DataValidator, ValidationStatus

validator = DataValidator()
result = validator.validate(
    df=input_dataframe,
    engine_type="finance",
    job_id="job-001",
)

if result.status == ValidationStatus.FAIL:
    print(result.issues)   # Critical blockers
else:
    print(result.warnings) # Non-blocking alerts
```

| Check | What It Does |
|-------|-------------|
| Required columns | Each engine type has a required column set |
| Critical null % | >50% nulls in a critical column = FAIL |
| Minimum row count | System minimum of 10 rows enforced |
| Date parseability | Date columns validated for format consistency |
| Currency codes | ISO 4217 validation on currency columns |
| Recommended columns | Missing recommended columns = WARN |

### `core/kpi_utils.py` — KPI Calculation Framework

Shared calculation utilities used across all engines. Handles pandas Series safely — no silent NaN propagation, division-by-zero guards, and percentile-based anomaly flagging.

```python
from core.kpi_utils import KPICalculator

calc = KPICalculator(df)
revenue_growth = calc.growth_rate("revenue", periods=1)
volatility = calc.rolling_volatility("daily_return", window=21)
anomalies = calc.flag_anomalies("value", method="iqr", threshold=1.5)
```

### `core/unit_converter.py` — Auto Unit Detection

Detects and normalises unit inconsistencies in input data before engine processing. Detection-only by default — original columns always preserved.

```python
from core.unit_converter import UnitConverter

converter = UnitConverter()
report = converter.audit(df)

# report.conversions_needed:
#   [{'column': 'generation', 'detected_unit': 'watts', 'target_unit': 'kilowatts'}]

normalized_df = converter.convert(df, report)
```

Supported conversion categories:

| Category | Units | Base |
|----------|-------|------|
| Power | W, kW, MW | kW |
| Currency (USD) | cents, dollars | dollars |
| Crypto (BTC) | satoshi, BTC | BTC |
| Crypto (ETH) | wei, gwei, ETH | ETH |
| Temperature | °F, °C, K | Celsius |
| Odds | American +/-, decimal | decimal |
| Time | ms, s, min, hr | seconds |
| Energy | Wh, kWh, MWh | kWh |

### `core/etl_orchestrator.py` — Pipeline Coordinator

Registers engines and extractors, coordinates multi-source collection, and aggregates telemetry. Used to run multiple industry pipelines in sequence or parallel.

```python
from core.etl_orchestrator import ETLOrchestrator

orch = ETLOrchestrator()
orch.register("finance", FinanceEngine, source="fred")
orch.register("brokerage", BrokerageEngine, source="yahoo_finance")
orch.register("crypto", CryptoEngine, source="coingecko")

results = orch.run_all(job_date="2024-06-01")
# {finance: EngineResult(success=True, kpis_computed=22),
#  brokerage: EngineResult(success=True, kpis_computed=19),
#  crypto: EngineResult(success=True, kpis_computed=30)}
```

---

## Data Sources

Multiple public API integrations. Each uses the BaseExtractor pattern with rate limiting, caching, and retry-with-backoff built in.

| Source | Type | Auth | Rate Limit | Pagination |
|--------|------|------|-----------|------------|
| Yahoo Finance | Equity OHLCV + profiles | None | ~60/min | Symbol-by-symbol |
| FRED | Macroeconomic series (800K+) | Free key | 120/min | Cursor (date) |
| EIA API v2 | Energy production/prices | Free key | 60/min | Offset |
| CoinGecko | Crypto market data | None (free) | 20/min | Page-number |
| SEC EDGAR | XBRL financial facts | None | 10/sec | Bulk response |
| ESPN | Sports scores and standings | None | 60/min | Offset |
| NASA NREL | Solar irradiance, PVWatts | Free key | 60/min | Single response |
| Open-Meteo | Historical weather (global) | None | 60/min | Array (lat/lon) |
| Steam | Game market data | None | 60/min | Page-number |
| NOAA | Climate normals, weather | Free key | 60/min | Offset |
| Custom media | Platform content signals | Internal | N/A | Cursor |

---

## Infrastructure

```
GCP Compute Engine (e2-highmem-2, 16GB RAM, 50GB SSD)
├── PostgreSQL — time-series bars, model registry, audit trail
├── Flask API — 30+ endpoints across multiple verticals
├── Nginx — reverse proxy + SSL termination
├── systemd — 5 managed services with automatic restart
│   ├── job-orchestrator  — daily pipeline execution
│   ├── file-intake-watcher    — file drop trigger
│   ├── storage-sync       — GCS backup sync
│   ├── cloud-drive-sync   — Google Drive integration
│   └── report-scheduler   — demo generation scheduler
├── Cron — daily data fetch + weekly model retrain
├── GitHub Actions CI — lint, test, security scan, SBOM
├── Terraform — GCP resources (VM, storage, IAM, firewall)
└── Docker — local development environment
```

---

## Quality Standards

- **500+ automated tests** — pytest, unit + integration
- **6 validation rule types** — completeness, uniqueness, range, pattern, custom, composite
- **Immutable audit trail** — every pipeline run logged with input hash, output hash, row counts
- **Data lineage** — every KPI traces back to a source API call with timestamp
- **Simulated data always disclosed** — never mixed with live data without explicit labelling

---

## Project Structure

```
core/
├── engine_core.py       # Abstract engine with KPI lifecycle management
├── validator.py         # Pre-flight data quality validation
├── kpi_utils.py         # Shared KPI calculation utilities
├── unit_converter.py    # Auto unit detection and normalisation
└── etl_orchestrator.py  # Multi-engine pipeline coordinator

docs/
├── ARCHITECTURE.md      # Platform architecture deep-dive
├── INDUSTRIES.md        # Per-vertical KPI definitions
└── DATA_SOURCES.md      # API integration details

tests/
└── test_core.py         # Core utility tests
```

---

## Contact

**Mboya Jeffers** — Data & ML Engineer

- **Email:** MboyaJeffers9@gmail.com
- **LinkedIn:** linkedin.com/in/mboya-jeffers-6377ba325
- **GitHub:** github.com/mboyajeffers

**Related repositories:**

| Repo | Focus |
|------|-------|
| [financial-data-engineering](https://github.com/mboyajeffers/financial-data-engineering) | Runnable ETL pipeline code — 8 extractors, ML pipeline, 200+ tests |
| [financial-market-analysis](https://github.com/mboyajeffers/financial-market-analysis) | 89+ live intelligence reports (PDFs), 3 white glove demos |
| [Data-Engineering-Portfolio](https://github.com/mboyajeffers/Data-Engineering-Portfolio) | 8 projects, 4.3M+ rows, production platform infrastructure |

*Open to remote data engineering roles and analytics consulting. All code independently runnable.*
