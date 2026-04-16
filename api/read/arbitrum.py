"""Vercel cron entry point for Arbitrum metrics collection."""

from common.metrics_handler import BaseVercelHandler, MetricsHandler
from config.defaults import MetricsServiceConfig
from metrics.arbitrum import (
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

METRIC_NAME = f"{MetricsServiceConfig.METRIC_PREFIX}response_latency_seconds"

METRICS = [
    (WSBlockLatencyMetric, METRIC_NAME),
    (HTTPBlockNumberLatencyMetric, METRIC_NAME),
    (HTTPEthCallLatencyMetric, METRIC_NAME),
    (HTTPAccBalanceLatencyMetric, METRIC_NAME),
    (HTTPDebugTraceBlockByNumberLatencyMetric, METRIC_NAME),
    (HTTPDebugTraceTxLatencyMetric, METRIC_NAME),
    (HTTPTxReceiptLatencyMetric, METRIC_NAME),
    (HTTPGetLogsLatencyMetric, METRIC_NAME),
]


class handler(BaseVercelHandler):
    """Vercel HTTP handler for Arbitrum metric collection."""

    metrics_handler = MetricsHandler("Arbitrum", METRICS)
