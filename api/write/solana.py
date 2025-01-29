import os

from common.metrics_handler import BaseVercelHandler, MetricsHandler
from metrics.solana_landing_rate import SolanaLandingMetric

metric_name = os.getenv("METRIC_NAME", "test_tx_landing_time_seconds")
target_region = "fra1"

# Run this metric only in EU (fra1)
METRICS = (
    []
    if os.getenv("VERCEL_REGION") != target_region
    else [(SolanaLandingMetric, metric_name)]
)


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("Solana", METRICS)
