import os

from common.metrics_handler import BaseVercelHandler, MetricsHandler
from config.defaults import MetricsServiceConfig
from metrics.solana_landing_rate import SolanaLandingMetric

metric_name = f"{MetricsServiceConfig.METRIC_PREFIX}transaction_landing_latency"
target_region = "fra1"

# Run this metric only in EU (fra1)
METRICS = (
    []
    if os.getenv("VERCEL_REGION") != target_region  # System env var, standard name
    else [(SolanaLandingMetric, metric_name)]
)


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("Solana", METRICS)
