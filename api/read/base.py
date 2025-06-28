from common.metrics_handler import BaseVercelHandler, MetricsHandler
from config.defaults import MetricsServiceConfig
from metrics.base import (
    HTTPAccBalanceLatencyMetric,
    HTTPBlockNumberLatencyMetric,
    HTTPDebugTraceBlockByNumberLatencyMetric,
    HTTPDebugTraceTxLatencyMetric,
    HTTPEthCallLatencyMetric,
    HTTPGetLogsLatencyMetric,
    HTTPTxReceiptLatencyMetric,
)
from metrics.ethereum import (
    WSBlockLatencyMetric,
)

metric_name = f"{MetricsServiceConfig.METRIC_PREFIX}response_latency_seconds"

METRICS = [
    (WSBlockLatencyMetric, metric_name),
    (HTTPBlockNumberLatencyMetric, metric_name),
    (HTTPEthCallLatencyMetric, metric_name),
    (HTTPAccBalanceLatencyMetric, metric_name),
    (HTTPDebugTraceBlockByNumberLatencyMetric, metric_name),
    (HTTPDebugTraceTxLatencyMetric, metric_name),
    (HTTPTxReceiptLatencyMetric, metric_name),
    (HTTPGetLogsLatencyMetric, metric_name),
]


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("Base", METRICS)
