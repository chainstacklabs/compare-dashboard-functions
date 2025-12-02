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

METRIC_NAME = f"{MetricsServiceConfig.METRIC_PREFIX}response_latency_seconds"

METRICS = [
    (HTTPGetRecentBlockhashLatencyMetric, METRIC_NAME),
    (HTTPSimulateTxLatencyMetric, METRIC_NAME),
    (HTTPGetBalanceLatencyMetric, METRIC_NAME),
    (HTTPGetBlockLatencyMetric, METRIC_NAME),
    (HTTPGetTxLatencyMetric, METRIC_NAME),
    (HTTPGetProgramAccsLatencyMetric, METRIC_NAME),
]


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("Solana", METRICS)
