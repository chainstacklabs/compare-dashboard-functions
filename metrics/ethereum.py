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


class HTTPGetLogsLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the eth_getLogs method."""

    @property
    def method(self) -> str:
        return "eth_getLogs"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters for USDC transfer logs from latest block."""
        return [
            {
                "fromBlock": "latest",
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
            logging.warning(
                "Subscription with False flag failed, retrying without flag"
            )

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


class WSLogLatencyMetric(WebSocketMetric):
    """Collects log latency using minimal-byte log events.

    Uses a very specific event that happens predictably but rarely,
    minimizing both frequency and byte count for cost optimization.
    """

    # WETH Deposit events - happen regularly but not too frequently
    WETH_CONTRACTS: dict[str, str] = {
        "ethereum": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
        "base": "0x4200000000000000000000000000000000000006",  # WETH on Base
        "arbitrum": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",  # WETH on Arbitrum
        "bnb": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
    }

    # Event signatures by chain (Arbitrum uses Transfer from zero address for WETH wrapping)
    EVENT_SIGNATURES: dict[str, tuple[str, list]] = {
        "ethereum": (
            "0xe1fffcc4923d04b559f4d29a8bfc6cda04eb5b0d3c460751c2402c5c5cc9109c",
            [],
        ),  # Deposit(address,uint256)
        "base": (
            "0xe1fffcc4923d04b559f4d29a8bfc6cda04eb5b0d3c460751c2402c5c5cc9109c",
            [],
        ),  # Deposit(address,uint256)
        "arbitrum": (
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            [  # Transfer(address,address,uint256)
                "0x0000000000000000000000000000000000000000000000000000000000000000",  # from: zero address (wrapping ETH)
                None,  # to: any address
            ],
        ),
        "bnb": (
            "0xe1fffcc4923d04b559f4d29a8bfc6cda04eb5b0d3c460751c2402c5c5cc9109c",
            [],
        ),  # Deposit(address,uint256)
    }

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

        # Get WETH contract and event signature for the specific blockchain
        blockchain: str | None = labels.get_label(MetricLabelKey.BLOCKCHAIN)
        if blockchain:
            self.weth_contract: str | None = self.WETH_CONTRACTS.get(blockchain.lower())
            self.event_signature, self.event_topics = self.EVENT_SIGNATURES.get(
                blockchain.lower(), self.EVENT_SIGNATURES["ethereum"]
            )
        else:
            self.weth_contract = self.WETH_CONTRACTS["ethereum"]
            self.event_signature, self.event_topics = self.EVENT_SIGNATURES["ethereum"]

        self.labels.update_label(MetricLabelKey.API_METHOD, "eth_subscribe_logs")

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
        """Subscribe to WETH events - Deposit for most chains, Transfer from zero for Arbitrum."""
        # Build topics array: [signature] + additional topics for filtering
        topics: list[str] = [self.event_signature] + self.event_topics

        subscription_msg: str = json.dumps(
            {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "eth_subscribe",
                "params": [
                    "logs",
                    {"address": self.weth_contract, "topics": topics},
                ],
            }
        )

        await self.send_with_timeout(websocket, subscription_msg, WS_DEFAULT_TIMEOUT)
        response: str = await self.recv_with_timeout(websocket, WS_DEFAULT_TIMEOUT)
        subscription_data = json.loads(response)

        if subscription_data.get("result") is None:
            raise ValueError(
                f"Subscription to WETH deposits failed: {subscription_data}"
            )

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
        """Listen for the FIRST WETH deposit event and immediately unsubscribe."""
        try:
            response: str = await self.recv_with_timeout(websocket, WS_DEFAULT_TIMEOUT)

            # Immediately unsubscribe as soon as we get ANY message
            try:
                await self.unsubscribe(websocket)
            except Exception as e:
                logging.warning(f"Failed to unsubscribe immediately: {e}")

            response_data = json.loads(response)

            if "params" in response_data and "result" in response_data["params"]:
                log_data = response_data["params"]["result"]
                return log_data

            return None

        except TimeoutError as e:
            # Timeout is expected when no events occur - log as warning but don't raise
            logging.warning(f"No WETH deposit events received within timeout: {e}")

            # Ensure we unsubscribe even on timeout
            try:
                await self.unsubscribe(websocket)
            except Exception as unsub_error:
                logging.warning(f"Failed to unsubscribe after timeout: {unsub_error}")

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
            else:
                # No event received (timeout) - this is acceptable, don't mark as failure
                logging.info(
                    "No WETH deposit event received - skipping metric collection"
                )
                return

        except Exception as e:
            # Only mark failure for actual errors, not timeouts
            if not isinstance(e, TimeoutError):
                self.mark_failure()
                self.handle_error(e)
            else:
                logging.warning(f"Timeout in collect_metric: {e}")

        finally:
            if websocket:
                try:
                    # Don't call unsubscribe here since it's already called in listen_for_data
                    await websocket.close()
                except Exception as e:
                    logging.error(f"Error closing websocket: {e!s}")

    async def calculate_timestamp_latency_http(self, log_data: dict) -> float:
        """Calculate latency between block timestamp and current time using HTTP."""
        current_time: datetime = datetime.now(timezone.utc)

        block_number = log_data.get("blockNumber")
        if not block_number:
            raise ValueError("No blockNumber in log data")

        # Use HTTP endpoint to fetch block timestamp
        block_request = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "eth_getBlockByNumber",
            "params": [block_number, False],  # False = don't include transactions
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
        return 0.0
