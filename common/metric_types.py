"""Base classes for WebSocket and HTTP metric collection."""

import asyncio
import logging
from abc import abstractmethod
from typing import Any, Optional

import aiohttp
import websockets

from common.base_metric import BaseMetric

# Import MAX_RETRIES from http_timing module for consistency
# (though it's not used directly in this module)
from common.http_timing import (
    MAX_RETRIES,  # noqa: F401
    make_json_rpc_request,
)
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

        async def _collect_ws_data():
            nonlocal websocket
            websocket = await self.connect()
            await self.subscribe(websocket)
            data = await self.listen_for_data(websocket)

            if data is not None:
                return data
            raise ValueError("No data in response")

        try:
            data = await asyncio.wait_for(
                _collect_ws_data(), timeout=self.config.timeout
            )
            latency: int | float = self.process_data(data)
            self.update_metric_value(latency)
            self.mark_success()

        except asyncio.TimeoutError:
            self.mark_failure()
            self.handle_error(
                TimeoutError(
                    f"WebSocket metric collection exceeded {self.config.timeout}s timeout"
                )
            )

        except Exception as e:
            self.mark_failure()
            self.handle_error(e)

        finally:
            if websocket:
                try:
                    # Shield cleanup from cancellation to ensure proper resource cleanup
                    await asyncio.shield(self.unsubscribe(websocket))
                    await asyncio.shield(websocket.close())
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
            data = await asyncio.wait_for(
                self.fetch_data(), timeout=self.config.timeout
            )
            if data is not None:
                latency: int | float = self.process_data(data)
                self.update_metric_value(latency)
                self.mark_success()
                return
            raise ValueError("No data in response")
        except asyncio.TimeoutError:
            self.mark_failure()
            self.handle_error(
                TimeoutError(
                    f"Metric collection exceeded {self.config.timeout}s timeout"
                )
            )
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
        """Measure single request latency using shared timing utilities."""
        endpoint = self.config.endpoints.get_endpoint()
        if endpoint is None:
            raise ValueError("No endpoint configured")

        async with aiohttp.ClientSession() as session:
            response_time, _json_response = await make_json_rpc_request(
                session=session,
                url=endpoint,
                request_payload=self._base_request,
                exclude_connection_time=True,
            )
            return response_time

    def process_data(self, value: float) -> float:
        """Process raw latency measurement."""
        return value
