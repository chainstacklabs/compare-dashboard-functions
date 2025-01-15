import os

from common.metrics_handler import BaseVercelHandler, MetricsHandler
from metrics.solana import (
    HTTPGetBalanceLatencyMetric,
    HTTPGetBlockLatencyMetric,
    HTTPGetRecentBlockhashLatencyMetric,
    HTTPGetTxLatencyMetric,
    HTTPSimulateTxLatencyMetric,
    HTTPGetProgramAccsLatencyMetric,
)

metric_name = os.getenv("METRIC_NAME", "test_response_latency_seconds")

METRICS = [
    (HTTPGetRecentBlockhashLatencyMetric, metric_name),
    (HTTPSimulateTxLatencyMetric, metric_name),
    (HTTPGetBalanceLatencyMetric, metric_name),
    (HTTPGetBlockLatencyMetric, metric_name),
    (HTTPGetTxLatencyMetric, metric_name),
    (HTTPGetProgramAccsLatencyMetric, metric_name),
]


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("Solana", METRICS)
