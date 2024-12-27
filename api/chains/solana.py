from common.metrics_handler import BaseVercelHandler, MetricsHandler
from metrics.solana import (
    HTTPGetBalanceLatencyMetric,
    HTTPGetBlockLatencyMetric,
    HTTPGetRecentBlockhashLatencyMetric,
    HTTPGetTxLatencyMetric,
    HTTPSimulateTxLatencyMetric,
)

METRICS = [
    (HTTPGetRecentBlockhashLatencyMetric, "response_latency_seconds"),
    (HTTPSimulateTxLatencyMetric, "response_latency_seconds"),
    (HTTPGetBalanceLatencyMetric, "response_latency_seconds"),
    (HTTPGetBlockLatencyMetric, "response_latency_seconds"),
    (HTTPGetTxLatencyMetric, "response_latency_seconds"),
]


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("Solana", METRICS)
