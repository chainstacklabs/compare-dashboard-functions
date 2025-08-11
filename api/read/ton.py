import os  # noqa: D100

from common.metrics_handler import BaseVercelHandler, MetricsHandler
from config.defaults import MetricsServiceConfig
from metrics.ton import (
    HTTPGetAddressBalanceLatencyMetric,
    HTTPGetBlockHeaderLatencyMetric,
    HTTPGetBlockTxsLatencyMetric,
    HTTPGetWalletTxsLatencyMetric,
    HTTPRunGetMethodLatencyMetric,
)

METRIC_NAME = f"{MetricsServiceConfig.METRIC_PREFIX}response_latency_seconds"
ALLOWED_REGIONS: list[str] = [
    "fra1",  # Frankfurt (EU)
    "sfo1",  # San Francisco (US West)
    "sin1",  # Singapore
    # "kix1",  # Osaka (JP)
    # "hnd1", "Tokyo" (JP)
]

METRICS = (
    [
        (HTTPGetBlockHeaderLatencyMetric, METRIC_NAME),
        (HTTPRunGetMethodLatencyMetric, METRIC_NAME),
        (HTTPGetAddressBalanceLatencyMetric, METRIC_NAME),
        (HTTPGetBlockTxsLatencyMetric, METRIC_NAME),
        (HTTPGetWalletTxsLatencyMetric, METRIC_NAME),
    ]
    if os.getenv("VERCEL_REGION") in ALLOWED_REGIONS  # System env var, standard name
    else []
)


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("TON", METRICS)
