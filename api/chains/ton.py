from common.metrics_handler import BaseVercelHandler, MetricsHandler
from metrics.ton import (
    HTTPGetAddressBalanceLatencyMetric,
    HTTPGetBlockHeaderLatencyMetric,
    HTTPGetBlockTxsLatencyMetric,
    HTTPGetWalletTxsLatencyMetric,
    HTTPRunGetMethodLatencyMetric,
)

METRICS = [
    (HTTPGetBlockHeaderLatencyMetric, "response_latency_seconds"),
    (HTTPRunGetMethodLatencyMetric, "response_latency_seconds"),
    (HTTPGetAddressBalanceLatencyMetric, "response_latency_seconds"),
    (HTTPGetBlockTxsLatencyMetric, "response_latency_seconds"),
    (HTTPGetWalletTxsLatencyMetric, "response_latency_seconds"),
]


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("TON", METRICS)
