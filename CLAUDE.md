# CLAUDE.md

Python-based Vercel Functions that measure RPC node response times across multiple blockchains and push metrics to Grafana via Influx line protocol.

## Commands

```bash
# Code quality (run before completing any task)
black .
ruff check .
ruff check . --fix
mypy .

# Local testing
python tests/test_api_read.py    # Read metrics (latency)
python tests/test_api_write.py   # Write metrics (Solana landing rate)
python tests/test_update_state.py  # State update via blob storage
```

## Environment Setup

Copy `endpoints.json.example` → `endpoints.json` and populate with RPC endpoints.

Create `.env.local` (gitignored) with:
```
GRAFANA_URL=...
GRAFANA_TOKEN=...
BLOB_READ_WRITE_TOKEN=...
CRON_SECRET=...
# VERCEL_ENV is auto-set by Vercel; omit locally to get "dev_" metric prefix
```

## Architecture

```
api/read/      # Vercel cron entry points — one file per chain (every 3 min)
api/write/     # Write metrics (Solana landing rate, every 15 min)
api/support/   # update_state.py — fetches/caches blockchain state (every 15 min)
common/        # Shared: BaseMetric, MetricFactory, MetricsHandler, state/
metrics/       # Chain-specific metric implementations (subclass BaseMetric)
config/        # defaults.py — MetricsServiceConfig, BlobStorageConfig
tests/         # Local test scripts (not unit tests)
```

## Key Patterns

**Adding a new chain metric:**
1. Create `metrics/<chain>.py` subclassing `BaseMetric`, implement `collect_metric()` and `process_data()`
2. Register with `MetricFactory.register({<chain>: [(MetricClass, "metric_name")]})`
3. Add `api/read/<chain>.py` entry point
4. Add function config + cron to `vercel.json` (and region-specific `vercel.*.json` files)

**Metric prefix:** `METRIC_PREFIX = "dev_"` when `VERCEL_ENV != "production"`. All metric names must use this prefix to avoid polluting production Grafana.

**Blob storage folders:** `dev-rpc-dashboard` (non-prod) vs `prod-rpc-dashboard` (prod) — same key `VERCEL_ENV` controls this.

**Solana landing rate:** `MetricFactory` creates two instances per endpoint when `tx_endpoint` is provided — one with the base provider name, one with `{provider}_tx`.

**Error handling:** HTTP 401/403/404/429 errors are silently ignored (plan restrictions / rate limits). Other errors zero the metric and log with `mark_failure()`.

**Metrics output:** Influx line protocol — `metric_name,tag1=v1,tag2=v2 value=X`

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
