import os

from common.metrics_handler import BaseVercelHandler, MetricsHandler
from metrics.base import (
    HTTPAccBalanceLatencyMetric,
    HTTPDebugTraceTxLatencyMetric,
    HTTPEthCallLatencyMetric,
    HTTPTxReceiptLatencyMetric,
)
from metrics.ethereum import (
    HTTPBlockNumberLatencyMetric,
    HTTPDebugTraceBlockByNumberLatencyMetric,
    WSBlockLatencyMetric,
)


metric_name = os.getenv("METRIC_NAME", "test_response_latency_seconds")

METRICS = [
    (WSBlockLatencyMetric, metric_name),
    (HTTPBlockNumberLatencyMetric, metric_name),
    (HTTPEthCallLatencyMetric, metric_name),
    (HTTPAccBalanceLatencyMetric, metric_name),
    (HTTPDebugTraceBlockByNumberLatencyMetric, metric_name),
    (HTTPDebugTraceTxLatencyMetric, metric_name),
    (HTTPTxReceiptLatencyMetric, metric_name),
]


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("Base", METRICS)
