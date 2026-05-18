"""Vercel cron entry point for the P2P Syncro Sender landing-rate metric.

Standalone from ``api/write/solana.py``: uses a custom ``MetricsHandler``
subclass that emits exactly one probe (not one per Solana provider in
``endpoints.json``). Reads the first Solana provider's ``http_endpoint``
from the ``ENDPOINTS`` env var to back the read RPC (``getLatestBlockhash``
/ ``getSlot`` / ``getSignatureStatuses``); the send endpoint is hardcoded
inside ``P2PSyncroLandingMetric``.
"""

import json
import logging
import os
from typing import Optional

from common.metric_config import EndpointConfig, MetricConfig, MetricLabels
from common.metrics_handler import BaseVercelHandler, MetricsHandler
from config.defaults import MetricsServiceConfig
from metrics.p2p_syncro_landing_rate import P2PSyncroLandingMetric

METRIC_NAME = f"{MetricsServiceConfig.METRIC_PREFIX}transaction_landing_latency"
ALLOWED_REGIONS = ["fra1"]
PROVIDER_LABEL = "P2P-Syncro"
BLOCKCHAIN = "Solana"


def _resolve_read_endpoint() -> Optional[str]:
    """Return the first Solana provider's http_endpoint from ENDPOINTS, or None."""
    raw = os.getenv("ENDPOINTS")
    if not raw:
        return None
    try:
        config = json.loads(raw)
    except json.JSONDecodeError:
        return None
    for provider in config.get("providers", []):
        if provider.get("blockchain") == BLOCKCHAIN and provider.get("http_endpoint"):
            return str(provider["http_endpoint"])
    return None


class SyncroMetricsHandler(MetricsHandler):
    """Custom handler that emits a single Syncro probe per invocation."""

    def __init__(self) -> None:
        """Initialise with empty metric registry; metric is built in handle()."""
        super().__init__(BLOCKCHAIN, [])

    async def handle(self) -> tuple[str, str]:
        """Build one Syncro probe, collect it, push to Grafana."""
        self._instances = []
        region = self.grafana_config["current_region"] or "default"
        if region not in ALLOWED_REGIONS:
            return "skipped", ""

        read_endpoint = _resolve_read_endpoint()
        if not read_endpoint:
            raise RuntimeError("No Solana http_endpoint found in ENDPOINTS env var")

        metric_config = MetricConfig(
            timeout=MetricsServiceConfig.METRIC_REQUEST_TIMEOUT,
            max_latency=MetricsServiceConfig.METRIC_MAX_LATENCY,
            endpoints=EndpointConfig(main_endpoint=read_endpoint),
        )
        labels = MetricLabels(
            source_region=region,
            target_region="default",
            blockchain=BLOCKCHAIN,
            provider=PROVIDER_LABEL,
        )
        metric = P2PSyncroLandingMetric(
            handler=self,
            metric_name=METRIC_NAME,
            labels=labels,
            config=metric_config,
            http_endpoint=read_endpoint,
        )

        await metric.collect_metric()

        metrics_text = self.get_metrics_text()
        if metrics_text:
            await self.push_to_grafana(metrics_text)
        else:
            logging.warning("Nothing to push to Grafana.")
        return "done", metrics_text


class handler(BaseVercelHandler):
    """Vercel HTTP handler for the Syncro landing-rate metric."""

    metrics_handler = SyncroMetricsHandler()
