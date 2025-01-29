from common.metrics_handler import BaseVercelHandler, MetricsHandler
from config.defaults import MetricsServiceConfig
from metrics.solana import (
    HTTPGetBalanceLatencyMetric,
    HTTPGetBlockLatencyMetric,
    HTTPGetProgramAccsLatencyMetric,
    HTTPGetRecentBlockhashLatencyMetric,
    HTTPGetTxLatencyMetric,
    HTTPSimulateTxLatencyMetric,
)

metric_name = f"{MetricsServiceConfig.METRIC_PREFIX}response_latency_seconds"

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
