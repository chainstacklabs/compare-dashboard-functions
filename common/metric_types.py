"""Base classes for WebSocket and HTTP metric collection."""

import asyncio
import logging
import time
from abc import abstractmethod
from typing import Any, Optional

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
        websocket: websockets.WebSocketClientProtocol = await websockets.connect(
            self.ws_endpoint,  # type: ignore
            ping_timeout=10,  # self.config.timeout,
            open_timeout=10,  # self.config.timeout,
            close_timeout=10,  # self.config.timeout,
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
                latency: int | float = self.process_data(data)
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

    def get_endpoint(self) -> str:
        """Returns appropriate endpoint based on method."""
        return str(self.config.endpoints.get_endpoint())

    async def collect_metric(self) -> None:
        try:
            data = await self.fetch_data()
            if data is not None:
                latency: int | float = self.process_data(data)
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
        method_params: Optional[dict[str, Any]] = None,
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

        self.method_params: dict[str, Any] = (
            self.get_params_from_state(state_data)
            if method_params is None
            else method_params
        )
        self.labels.update_label(MetricLabelKey.API_METHOD, self.method)
        self._base_request = self._build_base_request()

    def _build_base_request(self) -> dict[str, Any]:
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
    def validate_state(state_data: dict[str, Any]) -> bool:
        """Validate blockchain state data."""
        return True

    @staticmethod
    def get_params_from_state(state_data: dict[str, Any]) -> dict[str, Any]:
        """Get RPC method parameters from state data."""
        return {}

    async def fetch_data(self) -> float:
        """Measure single request latency with a retry on 429 error."""
        endpoint: str | None = self.config.endpoints.get_endpoint()

        async with aiohttp.ClientSession() as session:
            response_time = 0.0  # Do not include retried requests after 429 error
            response = None  # type: ignore

            for retry_count in range(MAX_RETRIES):
                start_time: float = time.monotonic()
                response: aiohttp.ClientResponse = await self._send_request(session, endpoint)  # type: ignore
                response_time: float = time.monotonic() - start_time

                if response.status == 429 and retry_count < MAX_RETRIES - 1:
                    wait_time = int(response.headers.get("Retry-After", 15))
                    await response.release()  # Release before retry
                    await asyncio.sleep(wait_time)
                    continue

                break

            if not response:
                raise ValueError("No response received")

            try:
                if response.status != 200:
                    # Let the error propagate with status code
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=(),
                        status=response.status,
                        message=f"Status code: {response.status}",
                        headers=response.headers,
                    )

                json_response = await response.json()
                if "error" in json_response:
                    raise ValueError(f"JSON-RPC error: {json_response['error']}")

                return response_time
            finally:
                await response.release()

    async def _send_request(
        self, session: aiohttp.ClientSession, endpoint: str
    ) -> aiohttp.ClientResponse:
        """Send the request without retry logic."""
        return await session.post(
            endpoint,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=self._base_request,
            timeout=self.config.timeout,  # type: ignore
        )

    def process_data(self, value: float) -> float:
        """Process raw latency measurement."""
        return value
