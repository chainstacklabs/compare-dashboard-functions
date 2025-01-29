"""Base classes for WebSocket and HTTP metric collection."""

import logging
import time
from abc import abstractmethod
from typing import Any, Optional

import aiohttp
import websockets

from common.base_metric import BaseMetric
from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels
from common.metrics_handler import MetricsHandler


class WebSocketMetric(BaseMetric):
    """WebSocket metric for collecting real-time data."""

    def __init__(
        self,
        handler: "MetricsHandler",
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        ws_endpoint: Optional[str] = None,
        http_endpoint: Optional[str] = None,
    ) -> None:
        super().__init__(
            handler, metric_name, labels, config, ws_endpoint, http_endpoint
        )
        self.subscription_id: Optional[int] = None

    @abstractmethod
    async def subscribe(self, websocket: Any) -> None:
        """Sets up WebSocket subscription."""

    @abstractmethod
    async def unsubscribe(self, websocket: Any) -> None:
        """Cleans up WebSocket subscription."""

    @abstractmethod
    async def listen_for_data(self, websocket: Any) -> Optional[Any]:
        """Receives WebSocket data."""

    async def connect(self) -> Any:
        """Creates WebSocket connection."""
        websocket = await websockets.connect(
            self.ws_endpoint,
            ping_timeout=self.config.timeout,
            close_timeout=self.config.timeout,
        )
        return websocket

    async def collect_metric(self) -> None:
        """Collects single WebSocket message."""
        websocket = None

        try:
            websocket = await self.connect()
            await self.subscribe(websocket)
            data = await self.listen_for_data(websocket)

            if data is not None:
                latency = self.process_data(data)
                self.update_metric_value(latency)
                # if latency > self.config.max_latency:
                #     raise ValueError(f"Invalid latency: {latency}s")
                self.mark_success()
                return
            raise ValueError("No data in response")

        except Exception as e:
            self.mark_failure()
            self.handle_error(e)

        finally:
            if websocket:
                try:
                    await self.unsubscribe(websocket)
                    await websocket.close()
                except Exception as e:
                    logging.error(f"Error closing websocket: {e!s}")


class HttpMetric(BaseMetric):
    """HTTP metric for API data collection."""

    @abstractmethod
    async def fetch_data(self) -> Optional[Any]:
        """Fetches HTTP endpoint data."""

    def get_endpoint(self, method: str) -> str:
        """Returns appropriate endpoint based on method."""
        return self.config.endpoints.get_endpoint(method)  # type: ignore

    async def collect_metric(self) -> None:
        try:
            data = await self.fetch_data()
            if data is not None:
                latency = self.process_data(data)
                self.update_metric_value(latency)
                # if latency > self.config.max_latency:
                #     raise ValueError(f"Invalid latency: {latency}s")
                self.mark_success()
                return
            raise ValueError("No data in response")
        except Exception as e:
            self.mark_failure()
            self.handle_error(e)


class HttpCallLatencyMetricBase(HttpMetric):
    """Base class for JSON-RPC HTTP endpoint latency metrics."""

    def __init__(
        self,
        handler: "MetricsHandler",
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        method: str,
        method_params: dict = None,
        **kwargs,
    ):
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
        )
        self.method = method
        self.method_params = method_params or None
        self.labels.update_label(MetricLabelKey.API_METHOD, method)
        self._base_request = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": self.method,
        }
        if self.method_params:
            self._base_request["params"] = self.method_params

    async def fetch_data(self) -> float:
        """Measures single request latency."""
        start_time = time.monotonic()

        endpoint = self.config.endpoints.get_endpoint(self.method)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=self._base_request,
                timeout=self.config.timeout,
            ) as response:
                if response.status != 200:
                    raise ValueError(f"Status code: {response.status}")
                json_response = await response.json()
                if "error" in json_response:
                    raise ValueError(f"JSON-RPC error: {json_response['error']}")
                return time.monotonic() - start_time

    def process_data(self, value: float) -> float:
        return value
