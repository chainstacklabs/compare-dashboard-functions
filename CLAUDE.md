# CLAUDE.md

Python-based Vercel Functions that measure RPC node response times across multiple blockchains and push metrics to Grafana via Influx line protocol.

## Commands

```bash
# Code quality (run before completing any task)
uvx black .
uvx ruff check .
uvx ruff check . --fix
uvx mypy .

# Local testing
uv run python tests/test_api_read.py    # Read metrics (latency)
uv run python tests/test_api_write.py   # Write metrics (Solana landing rate)
uv run python tests/test_update_state.py  # State update via blob storage
```

## Environment Setup

Copy `endpoints.json.example` → `endpoints.json` (used by local tests; loaded into the `ENDPOINTS` env var by `tests/test_*.py`). In production, Vercel reads endpoints from the `ENDPOINTS` env var directly — see `common/metrics_handler.py` and `api/support/update_state.py`.

Create `.env.local` (gitignored). See `.env.local.example` for the full list. Required vars:
```
GRAFANA_URL=...
GRAFANA_USER=...
GRAFANA_API_KEY=...
CRON_SECRET=...
SKIP_AUTH=FALSE
VERCEL_BLOB_TOKEN=...
STORE_ID=...
SOLANA_PRIVATE_KEY=...   # only needed for Solana write/landing-rate
# VERCEL_ENV: leave unset locally to get the "dev_" metric prefix and "dev-rpc-dashboard" blob folder
```

## Architecture

```
api/read/      # Vercel cron entry points — one file per chain (every 3 min)
               # Plus test_blockchain.py (every 5 min) — sandbox for new metric work
api/write/     # solana.py — Solana landing rate (every 15 min, fra1 only)
api/support/   # update_state.py — fetches/caches blockchain state (every 15 min, fra1 only)
common/        # base_metric.py (BaseMetric, mark_failure), factory.py (MetricFactory),
               # metrics_handler.py (BaseVercelHandler, MetricsHandler),
               # metric_types.py (HttpCallLatencyMetricBase etc.), metric_config.py,
               # state/ (BlobStorageHandler, BlockchainDataFetcher, BlockchainState),
               # hyperliquid_info_base.py
metrics/       # Chain-specific metric implementations (one file per chain), plus
               # solana_landing_rate.py and hyperliquid_info.py
config/        # defaults.py — MetricsServiceConfig, BlobStorageConfig
tests/         # Local test scripts (not unit tests) — load endpoints.json into ENDPOINTS env
```

## Key Patterns

**Adding a new chain metric:**
1. Create `metrics/<chain>.py` subclassing `BaseMetric` (or `HttpCallLatencyMetricBase` from `common/metric_types.py`); implement `collect_metric()` and `process_data()`
2. Register with `MetricFactory.register({<chain>: [(MetricClass, "metric_name")]})`
3. Add `api/read/<chain>.py` entry point
4. Add function config + cron to `vercel.json` AND each region-specific `vercel.<region>.json` file the chain should run in
5. For new chains: also add to `SUPPORTED_BLOCKCHAINS` in `api/support/update_state.py` and to `BLOCK_OFFSET_RANGES` in `config/defaults.py`. EVM chains additionally need adding to the EVM tuple in `common/state/blockchain_fetcher.py:fetch_latest_data`

**Metric prefix:** `METRIC_PREFIX = "dev_"` when `VERCEL_ENV != "production"`. All metric names must use this prefix to avoid polluting production Grafana.

**Blob storage folders:** `dev-rpc-dashboard` (non-prod) vs `prod-rpc-dashboard` (prod) — same key `VERCEL_ENV` controls this.

**Solana landing rate:** `MetricFactory` creates two instances per endpoint when `tx_endpoint` is provided — one with the base provider name, one with `{provider}_tx`.

**Error handling:** HTTP 401/403/404/429 errors are silently ignored (plan restrictions / rate limits). Other errors zero the metric and log with `mark_failure()`.

**Metrics output:** Influx line protocol — `metric_name,tag1=v1,tag2=v2 value=X`

## Subprojects

**`dashboards/`** — isolated subproject for managing Grafana dashboard JSON definitions. Not deployed to Vercel (Vercel-ignored). Has its own `grafana_sync.py` CLI and `README.md`. Dependencies (`requests`, `python-dotenv`) are self-contained and not part of the main `pyproject.toml`. Do not modify this directory as part of Vercel function work.

## Gotchas

- **Do not deploy to Vercel during agent sessions** — crons run in production and could be disrupted.
- `endpoints.json` is gitignored; tests will fail without it.
- Each chain has its own `vercel.<region>.json` for multi-region deployments — changes to function config in `vercel.json` usually need to be mirrored there.
- `mypy` runs in strict mode (`strict = true`) — all new code needs full type annotations.
- Max cyclomatic complexity is 10 (Ruff C rule) — keep functions small.
- Python target is 3.9; avoid 3.10+ syntax (match statements, `X | Y` union types in runtime positions).

## Code Style

- PEP 8, Google-style docstrings, type hints on all functions
- Composition over inheritance for metric classes
- Functional programming preferred for utilities
