from common.metrics_handler import BaseVercelHandler, MetricsHandler
from config.defaults import MetricsServiceConfig
from metrics.ton import (
    HTTPGetAddressBalanceLatencyMetric,
    HTTPGetBlockHeaderLatencyMetric,
    HTTPGetBlockTxsLatencyMetric,
    HTTPGetWalletTxsLatencyMetric,
    HTTPRunGetMethodLatencyMetric,
)

metric_name = f"{MetricsServiceConfig.METRIC_PREFIX}response_latency_seconds"

METRICS = [
    (HTTPGetBlockHeaderLatencyMetric, metric_name),
    (HTTPRunGetMethodLatencyMetric, metric_name),
    (HTTPGetAddressBalanceLatencyMetric, metric_name),
    (HTTPGetBlockTxsLatencyMetric, metric_name),
    (HTTPGetWalletTxsLatencyMetric, metric_name),
]


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("TON", METRICS)
