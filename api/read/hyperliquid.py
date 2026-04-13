"""Vercel cron entry point for Hyperliquid metrics collection."""

from common.metrics_handler import BaseVercelHandler, MetricsHandler
from config.defaults import MetricsServiceConfig
from metrics.hyperliquid import (
    HTTPAccBalanceLatencyMetric,
    HTTPBlockNumberLatencyMetric,
    HTTPEthCallLatencyMetric,
    HTTPGetLogsLatencyMetric,
    HTTPTxReceiptLatencyMetric,
)
from metrics.hyperliquid_info import (
    HTTPClearinghouseStateLatencyMetric,
    HTTPOpenOrdersLatencyMetric,
)

METRIC_NAME = f"{MetricsServiceConfig.METRIC_PREFIX}response_latency_seconds"

METRICS = [
    (HTTPBlockNumberLatencyMetric, METRIC_NAME),
    (HTTPEthCallLatencyMetric, METRIC_NAME),
    (HTTPAccBalanceLatencyMetric, METRIC_NAME),
    (HTTPTxReceiptLatencyMetric, METRIC_NAME),
    (HTTPGetLogsLatencyMetric, METRIC_NAME),
    (HTTPClearinghouseStateLatencyMetric, METRIC_NAME),
    (HTTPOpenOrdersLatencyMetric, METRIC_NAME),
]


class handler(BaseVercelHandler):
    """Vercel HTTP handler for Hyperliquid metric collection."""

    metrics_handler = MetricsHandler("Hyperliquid", METRICS)
