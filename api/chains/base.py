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

METRICS = [
    (WSBlockLatencyMetric, "response_latency_seconds"),
    (HTTPBlockNumberLatencyMetric, "response_latency_seconds"),
    (HTTPEthCallLatencyMetric, "response_latency_seconds"),
    (HTTPAccBalanceLatencyMetric, "response_latency_seconds"),
    (HTTPDebugTraceBlockByNumberLatencyMetric, "response_latency_seconds"),
    (HTTPDebugTraceTxLatencyMetric, "response_latency_seconds"),
    (HTTPTxReceiptLatencyMetric, "response_latency_seconds"),
]


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("Base", METRICS)
