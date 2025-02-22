"""Base classes for WebSocket and HTTP metric collection."""

import asyncio
import logging
import time
from abc import abstractmethod
from typing import Any, Dict, Optional

import aiohttp
import websockets

from common.base_metric import BaseMetric
from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels
from common.metrics_handler import MetricsHandler

MAX_RETRIES = 3


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
                self.mark_success()
                return
            raise ValueError("No data in response")
        except Exception as e:
            self.mark_failure()
            self.handle_error(e)


class HttpCallLatencyMetricBase(HttpMetric):
    """Base class for JSON-RPC HTTP endpoint latency metrics.

    Handles request configuration, state validation, and response time measurement
    for blockchain RPC endpoints.
    """

    @property
    @abstractmethod
    def method(self) -> str:
        """RPC method name to be implemented by subclasses."""
        pass

    def __init__(
        self,
        handler: "MetricsHandler",
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        method_params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        state_data = kwargs.get("state_data", {})
        if not self.validate_state(state_data):
            raise ValueError(f"Invalid state data for {self.method}")

        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
        )

        self.method_params = (
            self.get_params_from_state(state_data)
            if method_params is None
            else method_params
        )
        self.labels.update_label(MetricLabelKey.API_METHOD, self.method)
        self._base_request = self._build_base_request()

    def _build_base_request(self) -> Dict[str, Any]:
        """Build the base JSON-RPC request object."""
        request = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": self.method,
        }
        if self.method_params:
            request["params"] = self.method_params
        return request

    @staticmethod
    def validate_state(state_data: Dict[str, Any]) -> bool:
        """Validate blockchain state data."""
        return True

    @staticmethod
    def get_params_from_state(state_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get RPC method parameters from state data."""
        return {}

    async def fetch_data(self) -> float:
        """Measure single request latency with a retry on 429 error."""
        endpoint = self.config.endpoints.get_endpoint(self.method)

        async with aiohttp.ClientSession() as session:
            start_time = time.monotonic()
            async with await self._send_request(session, endpoint, 0) as response:  # type: ignore
                if response.status != 200:
                    raise ValueError(f"Status code: {response.status}")
                json_response = await response.json()
                if "error" in json_response:
                    raise ValueError(f"JSON-RPC error: {json_response['error']}")
                return time.monotonic() - start_time

    async def _send_request(
        self, session: aiohttp.ClientSession, endpoint: str, retry_count: int
    ) -> aiohttp.ClientResponse:
        """Send the request and handle rate limiting with retries."""
        if retry_count >= MAX_RETRIES:
            raise ValueError("Status code: 429. Max retries exceeded")

        response = await session.post(
            endpoint,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=self._base_request,
            timeout=self.config.timeout,  # type: ignore
        )

        if response.status == 429 and retry_count < MAX_RETRIES:
            wait_time = int(response.headers.get("Retry-After", 10))
            await response.release()
            await asyncio.sleep(wait_time)
            return await self._send_request(session, endpoint, retry_count + 1)

        return response

    def process_data(self, value: float) -> float:
        """Process raw latency measurement."""
        return value
