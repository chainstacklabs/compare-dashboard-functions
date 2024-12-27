"""Solana metrics implementation for WebSocket and HTTP endpoints."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from websockets.client import WebSocketClientProtocol

from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels
from common.metric_types import HttpCallLatencyMetricBase, WebSocketMetric


class WSBlockLatencyMetric(WebSocketMetric):
    """
    Collects block latency for Solana providers using a WebSocket connection.
    Suitable for serverless invocation: connects, subscribes, collects one message, and disconnects.
    """

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs: Dict[str, Any],
    ):
        ws_endpoint: str = kwargs.get("ws_endpoint", "")
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            ws_endpoint=ws_endpoint,
        )
        self.labels.update_label(MetricLabelKey.API_METHOD, "blockSubscribe")
        self.last_block_hash: Optional[str] = None

    async def subscribe(self, websocket: WebSocketClientProtocol) -> None:
        """
        Subscribe to the newBlocks event on the WebSocket endpoint.
        """
        subscription_msg: str = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "blockSubscribe",
                "params": [
                    {
                        "commitment": "confirmed",
                        "encoding": "jsonParsed",
                    }
                ],
            }
        )
        await websocket.send(subscription_msg)
        response: str = await websocket.recv()
        subscription_data: Dict[str, Any] = json.loads(response)

        if subscription_data.get("result") is None:
            raise ValueError("Subscription to new blocks failed")

        self.subscription_id = subscription_data.get("result")

    async def unsubscribe(self, websocket: WebSocketClientProtocol) -> None:
        """
        Unsubscribe from the block subscription.
        """
        unsubscribe_msg: str = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "blockUnsubscribe",
                "params": [self.subscription_id],
            }
        )
        await websocket.send(unsubscribe_msg)
        response = await websocket.recv()
        response_data = json.loads(response)

        if not response_data.get("result", False):
            logging.warning("Unsubscribe call failed or returned false")
        else:
            logging.debug("Successfully unsubscribed from block subscription")

    async def listen_for_data(
        self, websocket: WebSocketClientProtocol
    ) -> Optional[Dict[str, Any]]:
        """
        Listen for a single data message from the WebSocket and process block latency.
        """
        response = await asyncio.wait_for(websocket.recv(), timeout=self.config.timeout)
        response_data: Dict[str, Any] = json.loads(response)

        if "params" in response_data:
            block = response_data["params"]["result"]
            return block

        return None

    def process_data(self, block_info: Dict[str, Any]) -> float:
        """
        Calculate block latency in seconds.
        """
        block_time: Optional[int] = block_info.get("blockTime")

        if block_time is None:
            raise ValueError("Block time missing in block data")

        block_datetime: datetime = datetime.fromtimestamp(block_time, timezone.utc)
        current_time: datetime = datetime.now(timezone.utc)
        latency: float = (current_time - block_datetime).total_seconds()
        return latency


class HTTPSimulateTxLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `simulateTransaction` method.
    """

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs,
    ):
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            method="simulateTransaction",
            method_params=[
                "AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAAEDArczbMia1tLmq7zz4DinMNN0pJ1JtLdqIJPUw3YrGCzYAMHBsgN27lcgB6H2WQvFgyZuJYHa46puOQo9yQ8CVQbd9uHXZaGT2cvhRs7reawctIXtX1s3kTqM9YV+/wCp20C7Wj2aiuk5TReAXo+VTVg8QTHjs0UjNMMKCvpzZ+ABAgEBARU=",
                {"encoding": "base64"},
            ],
            **kwargs,
        )


class HTTPGetRecentBlockhashLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `getLatestBlockhash` method.
    """

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs,
    ):
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            method="getLatestBlockhash",
            method_params=None,
            **kwargs,
        )


class HTTPGetTxLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `getTransaction` method.
    """

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs,
    ):
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            method="getTransaction",
            method_params=[
                "4VAGET7z5g7ogVGmbmZ6KBtF6DS8ftLWzD65BXZWQJjwASUqLod7LhGB6mqThcqo97QcC7r7uNmBY8GwsnLAA52n",
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
            ],
            **kwargs,
        )


class HTTPGetBalanceLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `getBalance` method.
    """

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs,
    ):
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            method="getBalance",
            method_params=["9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"],
            **kwargs,
        )


class HTTPGetBlockLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `getBlock` method.
    """

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs,
    ):
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            method="getBlock",
            method_params=[
                239462061,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
            ],
            **kwargs,
        )
