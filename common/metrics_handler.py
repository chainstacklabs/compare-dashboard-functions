"""Handlers for serverless metric collection and pushing."""

import asyncio
import json
import logging
import os
import time
from http.server import BaseHTTPRequestHandler

import aiohttp

from common.base_metric import BaseMetric
from common.factory import MetricFactory
from common.metric_config import MetricConfig
from common.state.blockchain_state import BlockchainState
from config.defaults import MetricsServiceConfig


class MetricsHandler:
    """Manages collection and pushing of blockchain metrics."""

    def __init__(self, blockchain: str, metrics: list[tuple[type, str]]) -> None:
        self._instances: list[BaseMetric] = []
        self.blockchain: str = blockchain
        self.metrics: list[tuple[type, str]] = metrics
        self.grafana_config = {
            "current_region": os.getenv(
                "VERCEL_REGION"
            ),  # System env var, standard name
            "url": os.environ.get("GRAFANA_URL"),
            "user": os.environ.get("GRAFANA_USER"),
            "api_key": os.environ.get("GRAFANA_API_KEY"),
            "push_retries": MetricsServiceConfig.GRAFANA_PUSH_MAX_RETRIES,
            "push_retry_delay": MetricsServiceConfig.GRAFANA_PUSH_RETRY_DELAY,
            "push_timeout": MetricsServiceConfig.GRAFANA_PUSH_TIMEOUT,
            "metric_request_timeout": MetricsServiceConfig.METRIC_REQUEST_TIMEOUT,
            "metric_max_latency": MetricsServiceConfig.METRIC_MAX_LATENCY,
        }

    def get_metrics_influx_format(self) -> list[str]:
        """Returns all metric values in Influx format."""
        metrics = []
        for instance in self._instances:
            if instance.values:
                metrics.extend(instance.get_influx_format())
        return metrics

    def get_metrics_text(self) -> str:
        current_time = int(time.time_ns())
        metrics: list[str] = self.get_metrics_influx_format()
        return "\n".join(f"{metric} {current_time}" for metric in metrics)

    async def collect_metrics(
        self, provider: dict, config: dict, state_data: dict
    ) -> None:
        metric_config = MetricConfig(
            timeout=self.grafana_config["metric_request_timeout"],
            max_latency=self.grafana_config["metric_max_latency"],
            endpoints=None,  # Will be set in factory
            extra_params={"tx_data": provider.get("data")},
        )

        metrics: list[BaseMetric] = MetricFactory.create_metrics(
            blockchain_name=self.blockchain,
            metrics_handler=self,
            config=metric_config,
            provider=provider["name"],
            source_region=self.grafana_config["current_region"],
            target_region=config.get("region", "default"),
            ws_endpoint=provider.get("websocket_endpoint"),  # type: ignore
            http_endpoint=provider.get("http_endpoint"),  # type: ignore
            tx_endpoint=provider.get("tx_endpoint"),  # type: ignore
            state_data=state_data,
        )

        await asyncio.gather(*(m.collect_metric() for m in metrics))

    async def push_to_grafana(self, metrics_text: str) -> None:
        if not all(
            [
                self.grafana_config["url"],
                self.grafana_config["user"],
                self.grafana_config["api_key"],
            ]
        ):
            return

        for attempt in range(1, self.grafana_config["push_retries"] + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.grafana_config["url"],
                        headers={"Content-Type": "text/plain"},
                        data=metrics_text,
                        auth=aiohttp.BasicAuth(
                            self.grafana_config["user"], self.grafana_config["api_key"]
                        ),
                        timeout=self.grafana_config["push_timeout"],
                    ) as response:
                        if response.status in (200, 204):
                            return

            except Exception:
                if attempt < self.grafana_config["push_retries"]:
                    await asyncio.sleep(self.grafana_config["push_retry_delay"])

    async def handle(self) -> tuple[str, str]:
        """Main handler for metric collection and pushing."""
        self._instances = []
        try:
            config = json.loads(os.getenv("ENDPOINTS"))  # type: ignore
            MetricFactory._registry.clear()
            MetricFactory.register({self.blockchain: self.metrics})
            rpc_providers = [
                p
                for p in config.get("providers", [])
                if p["blockchain"] == self.blockchain
            ]

            state_data = await BlockchainState.get_data(self.blockchain)

            collection_tasks = [
                self.collect_metrics(provider, config, state_data)
                for provider in rpc_providers
            ]
            await asyncio.gather(*collection_tasks, return_exceptions=True)

            metrics_text: str = self.get_metrics_text()
            if metrics_text:
                await self.push_to_grafana(metrics_text)
            else:
                logging.warning("Nothing to push to Grafana.")

            return "done", metrics_text

        except Exception as e:
            logging.error(f"Error in {self.blockchain} metrics handler: {e!s}")
            raise


class BaseVercelHandler(BaseHTTPRequestHandler):
    """HTTP handler for Vercel serverless endpoint."""

    metrics_handler: MetricsHandler = None  # type: ignore

    def validate_token(self) -> bool:
        auth_token: str | None = self.headers.get("Authorization")
        expected_token: str | None = os.environ.get(
            "CRON_SECRET"
        )  # System env var, standard name
        return auth_token == f"Bearer {expected_token}"

    def do_GET(self) -> None:
        skip_auth: bool = os.environ.get("SKIP_AUTH", "false").lower() == "true"
        if not skip_auth and not self.validate_token():
            self.send_response(401)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return

        loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            _, metrics_text = loop.run_until_complete(self.metrics_handler.handle())
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            response: str = (
                f"{self.metrics_handler.blockchain} metrics collection "
                f"completed\n\nMetrics:\n{metrics_text}"
            )
            self.wfile.write(response.encode("utf-8"))

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))

        finally:
            loop.close()
