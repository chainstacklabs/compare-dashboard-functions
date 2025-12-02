from common.metrics_handler import BaseVercelHandler, MetricsHandler
from config.defaults import MetricsServiceConfig
from metrics.ton import (
    HTTPGetAddressBalanceLatencyMetric,
    HTTPGetBlockHeaderLatencyMetric,
    HTTPGetBlockTxsLatencyMetric,
    HTTPGetWalletTxsLatencyMetric,
    HTTPRunGetMethodLatencyMetric,
)

METRIC_NAME = f"{MetricsServiceConfig.METRIC_PREFIX}response_latency_seconds"

METRICS = [
    (HTTPGetBlockHeaderLatencyMetric, METRIC_NAME),
    (HTTPRunGetMethodLatencyMetric, METRIC_NAME),
    (HTTPGetAddressBalanceLatencyMetric, METRIC_NAME),
    (HTTPGetBlockTxsLatencyMetric, METRIC_NAME),
    (HTTPGetWalletTxsLatencyMetric, METRIC_NAME),
]


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("TON", METRICS)
