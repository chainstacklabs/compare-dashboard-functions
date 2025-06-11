"""Ethereum EVM metrics implementation for WebSocket and HTTP endpoints."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

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
            logging.warning(
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
        subscription_msg: str = json.dumps(
            {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "eth_subscribe",
                "params": ["newHeads"],
            }
        )
        await self.send_with_timeout(websocket, subscription_msg, WS_DEFAULT_TIMEOUT)
        response: str = await self.recv_with_timeout(websocket, WS_DEFAULT_TIMEOUT)
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


class WSLogLatencyMetric(WebSocketMetric):
    """Collects log latency for EVM providers using predictable log events.

    This metric subscribes to Transfer events from USDT contracts, which have
    predictable, consistent message sizes across all supported chains.
    """

    # Use USDT (Tether) which is available on all chains
    TOKEN_CONTRACTS: dict[str, str] = {
        "ethereum": "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
        "base": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",  # USDT
        "arbitrum": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",  # USDT
        "bnb": "0x55d398326f99059fF775485246999027B3197955",  # BSC-USD
    }

    # Transfer event signature: Transfer(address,address,uint256)
    TRANSFER_SIGNATURE = (
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    )

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore  # noqa: F821
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs,
    ) -> None:
        ws_endpoint = kwargs.pop("ws_endpoint", None)
        http_endpoint = kwargs.pop("http_endpoint", None)
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            ws_endpoint=ws_endpoint,
            http_endpoint=http_endpoint,
        )

        # Get blockchain name from labels and determine token contract
        blockchain: str | None = labels.get_label(MetricLabelKey.BLOCKCHAIN)
        if blockchain:
            self.token_contract = self.TOKEN_CONTRACTS.get(blockchain.lower())  # type: ignore
        else:
            # Fallback to Ethereum USDT if blockchain not specified
            self.token_contract: str = self.TOKEN_CONTRACTS["ethereum"]

        self.labels.update_label(MetricLabelKey.API_METHOD, "eth_subscribe_logs")
        self.first_event_received = False  # Flag to track first event

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
            logging.warning(
                f"WebSocket received {message_size} bytes from {self.labels.get_prometheus_labels()}"
            )
            return message
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"WebSocket message reception timed out after {timeout} seconds"
            )

    async def subscribe(self, websocket) -> None:
        """Subscribe to Transfer logs from USDT contract."""
        subscription_msg: str = json.dumps(
            {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "eth_subscribe",
                "params": [
                    "logs",
                    {
                        "address": self.token_contract,
                        "topics": [self.TRANSFER_SIGNATURE],
                    },
                ],
            }
        )

        await self.send_with_timeout(websocket, subscription_msg, WS_DEFAULT_TIMEOUT)
        response: str = await self.recv_with_timeout(websocket, WS_DEFAULT_TIMEOUT)
        subscription_data = json.loads(response)

        if subscription_data.get("result") is None:
            raise ValueError(f"Subscription to logs failed: {subscription_data}")

        self.subscription_id = subscription_data["result"]

    async def unsubscribe(self, websocket) -> None:
        """Unsubscribe from the WebSocket connection."""
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

        try:
            await self.send_with_timeout(websocket, unsubscribe_msg, WS_DEFAULT_TIMEOUT)
            await self.recv_with_timeout(websocket, WS_DEFAULT_TIMEOUT)
        except Exception as e:
            logging.warning(f"Error during unsubscribe: {e}")

    async def listen_for_data(self, websocket) -> Optional[Any]:
        """Listen for the FIRST log event only and extract block information."""
        while not self.first_event_received:
            response: str = await self.recv_with_timeout(websocket, WS_DEFAULT_TIMEOUT)
            response_data = json.loads(response)

            if "params" in response_data and "result" in response_data["params"]:
                log_data = response_data["params"]["result"]
                self.first_event_received = True  # Mark that we got the first event
                return log_data

        return None

    async def collect_metric(self) -> None:
        """Collects single WebSocket message and calculates timestamp-based latency."""
        websocket = None

        try:
            websocket = await self.connect()
            await self.subscribe(websocket)
            log_data = await self.listen_for_data(websocket)

            if log_data is not None:
                # Get block timestamp using HTTP and calculate latency
                latency: float = await self.calculate_timestamp_latency_http(log_data)
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

    async def calculate_timestamp_latency_http(self, log_data: dict) -> float:
        """Calculate latency between block timestamp and current time using HTTP."""
        current_time: datetime = datetime.now(
            timezone.utc
        )  # Get current time before making HTTP request

        block_number = log_data.get("blockNumber")
        if not block_number:
            raise ValueError("No blockNumber in log data")

        # Use HTTP endpoint to fetch block timestamp
        block_request = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "eth_getBlockByNumber",
            "params": [block_number, False],  # False = don't include full transactions
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.http_endpoint,  # type: ignore
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=block_request,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    raise ValueError(
                        f"HTTP request failed with status {response.status}"
                    )

                block_data = await response.json()

                if "error" in block_data:
                    raise ValueError(f"RPC error: {block_data['error']}")

                if not block_data.get("result") or not block_data["result"].get(
                    "timestamp"
                ):
                    raise ValueError("Failed to get block timestamp")

                block_timestamp_hex = block_data["result"]["timestamp"]
                block_timestamp = int(block_timestamp_hex, 16)
                block_time: datetime = datetime.fromtimestamp(
                    block_timestamp, timezone.utc
                )
                latency: float = (current_time - block_time).total_seconds()

                return latency

    def process_data(self, log_data: dict) -> float:
        """This method is not used in the updated flow."""
        # The latency calculation is now handled in calculate_timestamp_latency_http
        return 0.0
