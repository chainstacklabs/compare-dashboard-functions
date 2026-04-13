"""Base classes for WebSocket and HTTP metric collection."""

import asyncio
import contextlib
import logging
import time
from abc import abstractmethod
from typing import Any, Optional, Union

import aiohttp
import websockets

from common.base_metric import BaseMetric
from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels
from common.metrics_handler import MetricsHandler

MAX_RETRIES = 2


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
        """Initialise WebSocket metric and set up subscription ID tracking."""
        super().__init__(
            handler, metric_name, labels, config, ws_endpoint, http_endpoint
        )
        self.subscription_id: Optional[int] = None

    @abstractmethod
    async def subscribe(self, websocket: websockets.WebSocketClientProtocol) -> None:
        """Sets up WebSocket subscription."""

    @abstractmethod
    async def unsubscribe(self, websocket: websockets.WebSocketClientProtocol) -> None:
        """Cleans up WebSocket subscription."""

    @abstractmethod
    async def listen_for_data(
        self, websocket: websockets.WebSocketClientProtocol
    ) -> Optional[dict[str, Any]]:
        """Receives WebSocket data."""

    async def connect(self) -> websockets.WebSocketClientProtocol:
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

        async def _collect_ws_data() -> Any:
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
                    f"WebSocket metric collection exceeded "
                    f"{self.config.timeout}s timeout"
                )
            )

        except Exception as e:
            self.mark_failure()
            self.handle_error(e)

        finally:
            if websocket:
                # Always attempt unsubscribe so provider knows to stop sending data
                try:
                    await asyncio.shield(self.unsubscribe(websocket))
                except asyncio.CancelledError:
                    logging.info("Unsubscribe completed despite cancellation")
                except Exception as e:
                    logging.debug(f"Unsubscribe attempt on closed connection: {e!s}")

                # Close can be called even on closed connections (it's idempotent)
                try:
                    await asyncio.shield(websocket.close())
                except asyncio.CancelledError:
                    logging.info("WebSocket close completed despite cancellation")
                except Exception as e:
                    logging.debug(f"WebSocket close attempt: {e!s}")


class HttpMetric(BaseMetric):
    """HTTP metric for API data collection."""

    @abstractmethod
    async def fetch_data(self) -> Optional[float]:
        """Fetches HTTP endpoint data."""

    def get_endpoint(self) -> str:
        """Returns appropriate endpoint based on method."""
        return str(self.config.endpoints.get_endpoint())

    async def collect_metric(self) -> None:
        """Collect a single HTTP metric, applying timeout and error handling."""
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
        method_params: Optional[Union[dict[str, Any], list[Any]]] = None,
        **kwargs: Any,
    ) -> None:
        """Initialise metric, validate state, and build the base JSON-RPC request."""
        state_data = kwargs.get("state_data", {})
        if not self.validate_state(state_data):
            raise ValueError(f"Invalid state data for {self.method}")

        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
        )

        self.method_params: Union[dict[str, Any], list[Any]] = (
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
    def get_params_from_state(
        state_data: dict[str, Any],
    ) -> Union[dict[str, Any], list[Any]]:
        """Get RPC method parameters from state data."""
        return {}

    async def _process_response(
        self,
        response: aiohttp.ClientResponse,
        response_time: float,
        conn_time: float,
    ) -> float:
        """Validate response and return RPC time excluding connection overhead."""
        try:
            if response.status != 200:
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

            try:
                self._on_json_response(json_response)
            except Exception:
                logging.debug(f"Block capture failed for {self.method}", exc_info=True)
                self._captured_block_number = None

            rpc_time = response_time - conn_time
            if rpc_time < 0:
                raise ValueError(
                    f"Negative RPC time: {rpc_time:.6f}s "
                    f"(response={response_time:.6f}s, conn={conn_time:.6f}s)"
                )
            return rpc_time
        finally:
            await response.release()

    async def fetch_data(self) -> float:
        """Measure single request latency with detailed timing."""
        endpoint: str | None = self.config.endpoints.get_endpoint()

        # Add trace config for detailed timing
        trace_config = aiohttp.TraceConfig()
        timing: dict[str, float] = {}

        async def on_connection_create_start(
            session: Any, context: Any, params: Any
        ) -> None:
            timing["conn_start"] = time.monotonic()

        async def on_connection_create_end(
            session: Any, context: Any, params: Any
        ) -> None:
            timing["conn_end"] = time.monotonic()

        trace_config.on_connection_create_start.append(on_connection_create_start)
        trace_config.on_connection_create_end.append(on_connection_create_end)

        async with aiohttp.ClientSession(
            trace_configs=[trace_config],
        ) as session:
            response_time = 0.0
            response = None

            for retry_count in range(MAX_RETRIES):
                start_time: float = time.monotonic()
                response = await self._send_request(session, endpoint)
                response_time = time.monotonic() - start_time

                if response.status == 429 and retry_count < MAX_RETRIES - 1:
                    wait_time = int(response.headers.get("Retry-After", 3))
                    await response.release()
                    await asyncio.sleep(wait_time)
                    continue

                break

            conn_time = (
                timing["conn_end"] - timing["conn_start"]
                if "conn_start" in timing and "conn_end" in timing
                else 0
            )

            if not response:
                raise ValueError("No response received")

            return await self._process_response(response, response_time, conn_time)

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
        )

    def _on_json_response(self, json_response: dict[str, Any]) -> None:
        """Hook called after a successful JSON-RPC response.

        Override in subclasses to capture response fields (e.g. block number).
        The default implementation does nothing.
        """

    def process_data(self, value: float) -> float:
        """Process raw latency measurement."""
        return value


class EVMBlockNumberLatencyMetric(HttpCallLatencyMetricBase):
    """Shared eth_blockNumber metric used by all EVM chains.

    Captures the returned block number for cross-provider lag computation.
    """

    @property
    def method(self) -> str:
        """Return the eth_blockNumber RPC method name."""
        return "eth_blockNumber"

    @staticmethod
    def get_params_from_state(state_data: dict[str, Any]) -> list[Any]:
        """Return empty params list for eth_blockNumber (JSON-RPC positional params)."""
        return []

    def _on_json_response(self, json_response: dict[str, Any]) -> None:
        """Parse hex block number from eth_blockNumber response."""
        result = json_response.get("result")
        if isinstance(result, str):
            with contextlib.suppress(ValueError):
                self._captured_block_number = int(result, 16)
