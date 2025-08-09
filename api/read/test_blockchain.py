import os

from common.metrics_handler import BaseVercelHandler, MetricsHandler
from config.defaults import MetricsServiceConfig
from metrics.solana import (
    HTTPGetBalanceLatencyMetric,
    HTTPGetProgramAccsLatencyMetric,
    HTTPGetRecentBlockhashLatencyMetric,
    HTTPSimulateTxLatencyMetric,
)

METRIC_NAME = f"{MetricsServiceConfig.METRIC_PREFIX}response_latency_seconds"
ALLOWED_REGIONS: list[str] = [
    "fra1",  # Frankfurt (EU)
    "sfo1",  # San Francisco (US West)
    "sin1",  # Singapore
    # "kix1",  # Osaka (JP)
]

METRICS = (
    [
        (HTTPGetRecentBlockhashLatencyMetric, METRIC_NAME),
        (HTTPSimulateTxLatencyMetric, METRIC_NAME),
        (HTTPGetBalanceLatencyMetric, METRIC_NAME),
        (HTTPGetProgramAccsLatencyMetric, METRIC_NAME),
    ]
    if os.getenv("VERCEL_REGION") in ALLOWED_REGIONS  # System env var, standard name
    else []
)


class handler(BaseVercelHandler):
    metrics_handler = MetricsHandler("TEST_BLOCKCHAIN", METRICS)
