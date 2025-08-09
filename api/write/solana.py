import os  # noqa: D100

from common.metrics_handler import BaseVercelHandler, MetricsHandler
from config.defaults import MetricsServiceConfig
from metrics.solana_landing_rate import SolanaLandingMetric

METRIC_NAME = f"{MetricsServiceConfig.METRIC_PREFIX}transaction_landing_latency"
ALLOWED_REGIONS = ["fra1"]

# Run this metric only in allowed regions
METRICS: list[tuple[type[SolanaLandingMetric], str]] = (
    [(SolanaLandingMetric, METRIC_NAME)]
    if os.getenv("VERCEL_REGION") in ALLOWED_REGIONS  # System env var, standard name
    else []
)


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("Solana", METRICS)
