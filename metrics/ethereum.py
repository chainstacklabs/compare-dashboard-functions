"""Ethereum EVM metrics implementation for WebSocket and HTTP endpoints."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels
from common.metric_types import HttpCallLatencyMetricBase, WebSocketMetric


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

    async def subscribe(self, websocket) -> None:
        """Subscribe to the newHeads event on the WebSocket endpoint.

        Args:
            websocket: WebSocket connection instance

        Raises:
            ValueError: If subscription to newHeads fails
        """
        subscription_msg: str = json.dumps(
            {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "eth_subscribe",
                "params": ["newHeads"],
            }
        )
        await websocket.send(subscription_msg)
        response = await websocket.recv()
        subscription_data = json.loads(response)
        if subscription_data.get("result") is None:
            raise ValueError("Subscription to newHeads failed")
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
        await websocket.send(unsubscribe_msg)

    async def listen_for_data(self, websocket):
        """Listen for a single data message from the WebSocket and process block latency.

        Args:
            websocket: WebSocket connection instance

        Returns:
            dict: Block data if received successfully, None otherwise

        Raises:
            asyncio.TimeoutError: If no message received within timeout period
        """
        response = await asyncio.wait_for(websocket.recv(), timeout=self.config.timeout)
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
