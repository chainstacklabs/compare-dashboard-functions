from common.metrics_handler import BaseVercelHandler, MetricsHandler
from config.defaults import MetricsServiceConfig
from metrics.solana import (
    HTTPGetBalanceLatencyMetric,
    HTTPGetProgramAccsLatencyMetric,
    HTTPGetRecentBlockhashLatencyMetric,
    HTTPSimulateTxLatencyMetric,
)

metric_name = f"{MetricsServiceConfig.METRIC_PREFIX}response_latency_seconds"

METRICS = [
    (HTTPGetRecentBlockhashLatencyMetric, metric_name),
    (HTTPSimulateTxLatencyMetric, metric_name),
    (HTTPGetBalanceLatencyMetric, metric_name),
    (HTTPGetProgramAccsLatencyMetric, metric_name),
]


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("TEST_BLOCKCHAIN", METRICS)
