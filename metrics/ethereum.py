"""Ethereum EVM metrics implementation for WebSocket and HTTP endpoints."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels
from common.metric_types import HttpCallLatencyMetricBase, WebSocketMetric

WS_DEFAULT_TIMEOUT = 20


class HTTPEthCallLatencyMetric(HttpCallLatencyMetricBase):
    """Collects transaction latency for eth_call simulation."""

    @property
    def method(self) -> str:
        return "eth_call"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Returns parameters for eth_call with fixed USDC token query."""
        return [
            {
                "to": "0xc2edad668740f1aa35e4d8f227fb8e17dca888cd",
                "data": "0x1526fe270000000000000000000000000000000000000000000000000000000000000001",  # noqa: E501
            },
            "latest",
        ]


class HTTPBlockNumberLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the eth_blockNumber method."""

    @property
    def method(self) -> str:
        return "eth_blockNumber"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Returns empty parameters list for eth_blockNumber."""
        return []


class HTTPTxReceiptLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the eth_getTransactionReceipt method."""

    @property
    def method(self) -> str:
        return "eth_getTransactionReceipt"

    @staticmethod
    def validate_state(state_data: dict) -> bool:
        """Validates that required transaction hash exists in state data."""
        return bool(state_data and state_data.get("tx"))

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Returns parameters using transaction hash from state."""
        return [state_data["tx"]]


class HTTPAccBalanceLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the eth_getBalance method."""

    @property
    def method(self) -> str:
        return "eth_getBalance"

    @staticmethod
    def validate_state(state_data: dict) -> bool:
        """Validates that required block number (hex) exists in state data."""
        return bool(state_data and state_data.get("old_block"))

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Returns parameters for balance check of monitoring address."""
        return ["0x690B9A9E9aa1C9dB991C7721a92d351Db4FaC990", state_data["old_block"]]


class HTTPDebugTraceBlockByNumberLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the debug_traceBlockByNumber method."""

    @property
    def method(self) -> str:
        return "debug_traceBlockByNumber"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Returns parameters for tracing latest block."""
        return ["latest", {"tracer": "callTracer"}]


class HTTPDebugTraceTxLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the debug_traceTransaction method."""

    @property
    def method(self) -> str:
        return "debug_traceTransaction"

    @staticmethod
    def validate_state(state_data: dict) -> bool:
        """Validates that required transaction hash exists in state data."""
        return bool(state_data and state_data.get("tx"))

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Returns parameters using transaction hash from state."""
        return [state_data["tx"], {"tracer": "callTracer"}]


class HTTPGetLogsLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the eth_getLogs method."""

    @property
    def method(self) -> str:
        return "eth_getLogs"

    @staticmethod
    def validate_state(state_data: dict) -> bool:
        """Validates that required block number exists in state data."""
        return bool(state_data and state_data.get("old_block"))

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters for USDC transfer logs from recent block range."""
        from_block_hex = state_data["old_block"]
        from_block_int = int(from_block_hex, 16)
        to_block_int: int = max(0, from_block_int + 100)
        to_block_hex: str = hex(to_block_int)

        return [
            {
                "fromBlock": from_block_hex,
                "toBlock": to_block_hex,
                "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
                "topics": [
                    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"  # Transfer event
                ],
            }
        ]


class WSBlockLatencyMetric(WebSocketMetric):
    """Collects block latency for EVM providers using a WebSocket connection.

    Suitable for serverless invocation: connects, subscribes, collects one message, and disconnects.
    """  # noqa: E501

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore  # noqa: F821
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs,
    ) -> None:
        """Initialize WebSocket block latency metric.

        Args:
            handler: Metrics handler instance
            metric_name: Name of the metric
            labels: Metric labels container
            config: Metric configuration
            **kwargs: Additional arguments including ws_endpoint
        """
        ws_endpoint = kwargs.pop("ws_endpoint", None)
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            ws_endpoint=ws_endpoint,
        )
        self.labels.update_label(MetricLabelKey.API_METHOD, "eth_subscribe")

    async def send_with_timeout(self, websocket, message: str, timeout: float) -> None:
        """Send a message with a timeout."""
        try:
            await asyncio.wait_for(websocket.send(message), timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"WebSocket message send timed out after {timeout} seconds"
            )

    async def recv_with_timeout(self, websocket, timeout: float) -> str:
        """Receive a message with a timeout."""
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout)
            # Log incoming message size in bytes
            message_size: int = len(message.encode("utf-8"))
            logging.info(
                f"WebSocket received {message_size} bytes from {self.labels.get_prometheus_labels()}"
            )
            return message
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"WebSocket message reception timed out after {timeout} seconds"
            )

    async def subscribe(self, websocket) -> None:
        """Subscribe to the newHeads event on the WebSocket endpoint.

        Args:
            websocket: WebSocket connection instance

        Raises:
            ValueError: If subscription to newHeads fails
        """
        # First attempt: with False flag, not all providers support this
        subscription_msg: str = json.dumps(
            {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "eth_subscribe",
                "params": ["newHeads", False],
            }
        )

        await self.send_with_timeout(websocket, subscription_msg, WS_DEFAULT_TIMEOUT)
        response: str = await self.recv_with_timeout(websocket, WS_DEFAULT_TIMEOUT)
        subscription_data = json.loads(response)

        # If subscription failed, try without the False flag
        if subscription_data.get("result") is None:
            logging.info("Subscription with False flag failed, retrying without flag")

            fallback_subscription_msg: str = json.dumps(
                {
                    "id": 1,
                    "jsonrpc": "2.0",
                    "method": "eth_subscribe",
                    "params": ["newHeads"],
                }
            )

            await self.send_with_timeout(
                websocket, fallback_subscription_msg, WS_DEFAULT_TIMEOUT
            )
            fallback_response: str = await self.recv_with_timeout(
                websocket, WS_DEFAULT_TIMEOUT
            )
            fallback_subscription_data = json.loads(fallback_response)

            if fallback_subscription_data.get("result") is None:
                raise ValueError("Subscription to newHeads failed even without flag")

            self.subscription_id = fallback_subscription_data["result"]
        else:
            self.subscription_id = subscription_data["result"]

    async def unsubscribe(self, websocket) -> None:
        """Unsubscribe from the WebSocket connection.

        Args:
            websocket: WebSocket connection instance
        """
        if self.subscription_id is None:
            logging.warning("No subscription ID available, skipping unsubscribe.")
            return

        unsubscribe_msg: str = json.dumps(
            {
                "id": 2,
                "jsonrpc": "2.0",
                "method": "eth_unsubscribe",
                "params": [self.subscription_id],
            }
        )
        await self.send_with_timeout(websocket, unsubscribe_msg, WS_DEFAULT_TIMEOUT)
        await self.recv_with_timeout(websocket, WS_DEFAULT_TIMEOUT)

    async def listen_for_data(self, websocket):
        """Listen for a single data message from the WebSocket and process block latency.

        Args:
            websocket: WebSocket connection instance

        Returns:
            dict: Block data if received successfully, None otherwise

        Raises:
            asyncio.TimeoutError: If no message received within timeout period
        """
        response: str = await self.recv_with_timeout(websocket, WS_DEFAULT_TIMEOUT)
        response_data = json.loads(response)
        if "params" in response_data:
            block = response_data["params"]["result"]
            return block
        return None

    def process_data(self, block) -> float:
        """Calculate block latency in seconds.

        Args:
            block (dict): Block data containing timestamp

        Returns:
            float: Latency in seconds between block timestamp and current time

        Raises:
            ValueError: If block timestamp is invalid or missing
        """
        block_timestamp_hex = block.get("timestamp", "0x0")
        block_timestamp = int(block_timestamp_hex, 16)
        block_time: datetime = datetime.fromtimestamp(block_timestamp, timezone.utc)
        current_time: datetime = datetime.now(timezone.utc)
        latency: float = (current_time - block_time).total_seconds()
        return latency
