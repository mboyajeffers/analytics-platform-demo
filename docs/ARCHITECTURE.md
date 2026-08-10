# Platform Architecture

Deep-dive into the design decisions, data flow, and infrastructure behind the production analytics platform.

---

## Overview

The platform is an analytics engine that extracts data from multiple public APIs, transforms it into industry-specific dimensional models, computes 100+ KPIs, and delivers branded intelligence reports. It runs on GCP with PostgreSQL, Flask, Nginx, and systemd-managed services.

The architecture is structured around three concerns:

1. **Extraction** — pulling data from heterogeneous public APIs with different auth, rate limits, and pagination patterns
2. **Computation** — running industry-specific KPI engines on cleaned, validated data
3. **Delivery** — generating PDFs, triggering reports, and managing job state

---

## Data Flow

```
Step 1: INGEST
  Public API → Extractor (rate-limited, cached, retry)
  → ExtractionResult (records, warnings, metadata)

Step 2: STAGE
  ExtractionResult → Star Schema Transformer
  → dim_* and fact_* tables (Parquet + PostgreSQL)

Step 3: VALIDATE
  Input DataFrame → DataValidator (6 check types)
  → ValidationResult (pass / warn / fail)
  FAIL → job aborted, error logged, state → FAILED
  WARN → job continues, warning logged

Step 4: COMPUTE
  Validated DataFrame → Industry Engine
  → _compute_kpi_safe(name, fn) × N KPIs
  → EngineResult (kpis_computed, kpis_failed, metrics)

Step 5: DELIVER
  EngineResult + metadata → ReportGenerator
  → PDF (WeasyPrint, industry-branded)
  → Saved to GCS + delivered to client
```

---

## Extraction Layer

Each data source has a dedicated extractor that inherits from `BaseExtractor`:

```python
class BaseExtractor(ABC):
    def extract(self, **kwargs) -> ExtractionResult: ...
    def _get(self, url, params) -> dict: ...       # Rate-limited, cached, retried
    def _paginate(self, url, ...) -> Generator: ...
```

**Pagination patterns across 11 sources:**

| Pattern | Example Source | How It Works |
|---------|---------------|--------------|
| Symbol-by-symbol | Yahoo Finance | One request per ticker, no cursor |
| Offset-based | USGS, EIA | Increment offset by page_size until exhausted |
| Page-number | World Bank, CoinGecko | Increment page until empty response |
| Cursor-based | FRED | Pass `observation_start` / `observation_end` |
| Bulk response | SEC EDGAR | Single large JSON with all facts for a company |
| Array-style | Open-Meteo | Parallel time arrays `{time: [...], temp: [...]}` |

**Infrastructure per extractor:**
- Token bucket rate limiter (thread-safe, configurable RPM)
- MD5-keyed response cache (in-memory, TTL configurable)
- Exponential backoff retry (3 attempts, jitter)
- HTTP 429 Retry-After handling
- Structured telemetry (API calls, cache hits, errors, latency)

---

## Engine Layer

Industry engines inherit from `BaseEngine`:

```
BaseEngine.run()
├── _load()              Load DataFrame from file or memory
├── DataValidator.validate()  Pre-flight checks (required cols, null %, dates)
├── ColumnMapper.normalize()  Standardise column names (aliases, casing)
├── compute_kpis()       [subclass] — calls _compute_kpi_safe per KPI
└── save_results()       Persist JSON + PDF to GCS, update job state
```

**_compute_kpi_safe() design:**
```python
def _compute_kpi_safe(self, name: str, fn: Callable) -> Optional[Any]:
    try:
        value = fn()
        self.result.add_kpi_success(name, value)
        return value
    except Exception as exc:
        self.result.add_kpi_failure(name, str(exc))
        return None  # One KPI failure never aborts others
```

This pattern means a NaN edge case in one KPI computation never aborts the rest of the job. Each KPI is independently tracked and reported.

---

## Data Quality Framework

Six rule types run as pre-flight checks before any engine computes:

| Rule Type | Block or Warn | What It Checks |
|-----------|--------------|----------------|
| Required columns | FAIL | Each engine has a required column set |
| Critical null % | FAIL | >50% nulls in a critical column |
| Minimum rows | FAIL | Global minimum of 10 rows enforced |
| Date parseability | WARN | >10% unparseable dates in date columns |
| Currency codes | WARN | ISO 4217 validation on currency columns |
| Recommended columns | WARN | Non-critical but expected columns missing |

Validation results are saved to the job's staging folder for audit trail.

---

## Dimensional Model (Kimball Star Schema)

Each industry vertical has its own dimension and fact tables:

```
Universal dimensions (shared):
  dim_date    — date_key, year, quarter, month, week, day, is_holiday
  dim_client  — client_key, client_id, name, industry, region

Industry fact tables (examples):
  Finance:
    fact_economic_indicators  (date_key, series_key, value, extraction_id)

  Brokerage:
    fact_daily_prices         (date_key, security_key, open, high, low, close, volume)

  Crypto:
    fact_market_snapshot      (date_key, asset_key, price_usd, market_cap, volume_24h)

  Oil & Gas:
    fact_production           (date_key, geo_key, volume_mbbl_d, units)

  Gaming:
    fact_player_sessions      (date_key, game_key, player_key, session_length, wager)
```

Surrogate keys use SHA-256 hash of natural keys, ensuring idempotent upserts.

---

## ML Layer

Built on top of the extraction and transformation layers:

```
OHLCV fact tables → FeatureStore.compute(symbol, lookback)
  → 17 features (return, momentum, volatility, volume, trend)

FeatureStore → WalkForwardBacktester.run(model, n_folds=5)
  → BacktestResult (accuracy, F1, Sharpe per fold)

Trained model → SignalGenerator.predict_latest(symbol)
  → Signal (direction, confidence, feature_snapshot)

Signal → RiskManager.size_position(signal, account_balance)
  → PositionSizing (quantity, stop_loss, take_profit)

PositionSizing → BrokerClient.submit_bracket_order()
  → OrderResult (order_id, fill_price, status)
```

**Walk-forward guarantees:**
- `_assert_no_leakage()` runs before every fold: `assert max(train_idx) < min(test_idx)`
- Training window is always expanding (not sliding) to maximise history usage
- Models are retrained on Sundays using full available history

---

## Infrastructure

```
GCP us-central1-a
├── Compute Engine (e2-highmem-2, 16GB RAM, 50GB SSD)
│   ├── /opt/platform/         Application root
│   │   ├── engines/           Industry engines + extractors + ML
│   │   ├── services/          Systemd-managed background services
│   │   ├── integrations/      Drive, Sheets, email, rate limiter
│   │   └── api/               Flask API (30+ blueprints)
│   ├── PostgreSQL 15
│   │   ├── analytics DB       Production (time-series, model registry)
│   │   └── test DB            CI/CD (isolated)
│   └── Nginx                  Reverse proxy + SSL termination
│
├── Cloud Storage
│   └── gs://platform-backups/ GCS bucket (weekly automated backup)
│
└── Terraform
    ├── VM provisioning
    ├── Firewall rules (80, 443, 8080 ingress)
    ├── Service accounts (GCS, Drive)
    └── Static IP

Local development:
├── Docker + docker-compose    Full stack local environment
├── GitHub Actions CI          Lint (ruff) + test (pytest) + SBOM
└── Makefile                   Standard dev commands
```

---

## Job State Machine

Every pipeline run is tracked through a state machine:

```
SUBMITTED
    │
    ▼
VALIDATING  ──FAIL──> FAILED
    │
    ▼
PROCESSING
    │
    ├──SUCCESS──> COMPLETED
    └──ERROR───> FAILED
```

States are persisted to `state.json` in the job's GCS path. Distributed locking (TTL-based) prevents concurrent runs of the same job ID.

---

## Security Model

- **No credentials in code** — API keys loaded from `.env` via GCP Secret Manager
- **Rate limiting** — per-source token bucket (server-side) + per-route Flask limiter (client-facing)
- **Immutable audit trail** — every API call, KPI computation, and state transition is logged with timestamp and input hash
- **Data lineage** — each KPI in a report traces back to a specific API response with exact timestamp
- **Simulated data disclosure** — any generated/synthetic data is explicitly labelled; never mixed with live data silently
