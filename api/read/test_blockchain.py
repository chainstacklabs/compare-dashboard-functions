from common.factory import MetricSpec
from common.metrics_handler import BaseVercelHandler, MetricsHandler
from config.defaults import MetricsServiceConfig
from metrics.solana import (
    HTTPGetBalanceLatencyMetric,
    HTTPGetProgramAccsLatencyMetric,
    HTTPGetRecentBlockhashLatencyMetric,
    HTTPSimulateTxLatencyMetric,
)

METRIC_NAME = f"{MetricsServiceConfig.METRIC_PREFIX}response_latency_seconds"

METRICS: list[MetricSpec] = [
    (HTTPGetRecentBlockhashLatencyMetric, METRIC_NAME),
    (HTTPSimulateTxLatencyMetric, METRIC_NAME),
    (HTTPGetBalanceLatencyMetric, METRIC_NAME),
    (HTTPGetProgramAccsLatencyMetric, METRIC_NAME),
]


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("TEST_BLOCKCHAIN", METRICS)
