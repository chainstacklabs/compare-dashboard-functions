from common.metrics_handler import BaseVercelHandler, MetricsHandler
from metrics.ethereum import (
    HTTPAccBalanceLatencyMetric,
    HTTPBlockNumberLatencyMetric,
    HTTPDebugTraceBlockByNumberLatencyMetric,
    HTTPDebugTraceTxLatencyMetric,
    HTTPEthCallLatencyMetric,
    HTTPTxReceiptLatencyMetric,
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
    metrics_handler = MetricsHandler("Ethereum", METRICS)
