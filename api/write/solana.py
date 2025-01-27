import os

from common.metrics_handler import BaseVercelHandler, MetricsHandler
from metrics.solana_landing_rate import SolanaLandingMetric

metric_name = os.getenv("METRIC_NAME", "test_tx_landing_time_seconds")

METRICS = [
    (SolanaLandingMetric, metric_name),
]


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("Solana", METRICS)
