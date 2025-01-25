import os

from common.metrics_handler import BaseVercelHandler, MetricsHandler
from metrics.ton import (HTTPGetAddressBalanceLatencyMetric,
                         HTTPGetBlockHeaderLatencyMetric,
                         HTTPGetBlockTxsLatencyMetric,
                         HTTPGetWalletTxsLatencyMetric,
                         HTTPRunGetMethodLatencyMetric)

metric_name = os.getenv("METRIC_NAME", "test_response_latency_seconds")

METRICS = [
    (HTTPGetBlockHeaderLatencyMetric, metric_name),
    (HTTPRunGetMethodLatencyMetric, metric_name),
    (HTTPGetAddressBalanceLatencyMetric, metric_name),
    (HTTPGetBlockTxsLatencyMetric, metric_name),
    (HTTPGetWalletTxsLatencyMetric, metric_name),
]


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("TON", METRICS)
