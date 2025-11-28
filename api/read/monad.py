import os  # noqa: D100

from common.metrics_handler import BaseVercelHandler, MetricsHandler
from config.defaults import MetricsServiceConfig
from metrics.ethereum import (
    WSBlockLatencyMetric,
)
from metrics.monad import (
    HTTPAccBalanceLatencyMetric,
    HTTPBlockNumberLatencyMetric,
    HTTPDebugTraceBlockByNumberLatencyMetric,
    HTTPDebugTraceTxLatencyMetric,
    HTTPEthCallLatencyMetric,
    HTTPGetLogsLatencyMetric,
    HTTPTxReceiptLatencyMetric,
)

METRIC_NAME = f"{MetricsServiceConfig.METRIC_PREFIX}response_latency_seconds"
ALLOWED_REGIONS: list[str] = [
    "fra1",  # Frankfurt (EU)
    "sfo1",  # San Francisco (US West)
    "sin1",  # Singapore
]

METRICS = (
    [
        (WSBlockLatencyMetric, METRIC_NAME),
        (HTTPBlockNumberLatencyMetric, METRIC_NAME),
        (HTTPEthCallLatencyMetric, METRIC_NAME),
        (HTTPAccBalanceLatencyMetric, METRIC_NAME),
        (HTTPDebugTraceBlockByNumberLatencyMetric, METRIC_NAME),
        (HTTPDebugTraceTxLatencyMetric, METRIC_NAME),
        (HTTPTxReceiptLatencyMetric, METRIC_NAME),
        (HTTPGetLogsLatencyMetric, METRIC_NAME),
    ]
    if os.getenv("VERCEL_REGION") in ALLOWED_REGIONS  # System env var, standard name
    else []
)


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("Monad", METRICS)
