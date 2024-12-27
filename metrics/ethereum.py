"""Ethereum EVM metrics implementation for WebSocket and HTTP endpoints."""

import asyncio
import json
from datetime import datetime, timezone

from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels
from common.metric_types import HttpCallLatencyMetricBase, WebSocketMetric


class WSBlockLatencyMetric(WebSocketMetric):
    """
    Collects block latency for EVM providers using a WebSocket connection.
    Suitable for serverless invocation: connects, subscribes, collects one message, and disconnects.
    """

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs,
    ):
        ws_endpoint = kwargs.pop("ws_endpoint", None)
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            ws_endpoint=ws_endpoint,
        )
        self.labels.update_label(MetricLabelKey.API_METHOD, "eth_subscribe")

    async def subscribe(self, websocket):
        """
        Subscribe to the newHeads event on the WebSocket endpoint.
        """
        subscription_msg = json.dumps(
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

    async def unsubscribe(self, websocket):
        # EVM blockchains have no unsubscribe logic; do nothing.
        pass

    async def listen_for_data(self, websocket):
        """
        Listen for a single data message from the WebSocket and process block latency.
        """
        response = await asyncio.wait_for(websocket.recv(), timeout=self.config.timeout)
        response_data = json.loads(response)

        if "params" in response_data:
            block = response_data["params"]["result"]
            return block

        return None

    def process_data(self, block):
        """
        Calculate block latency in seconds.
        """
        block_timestamp_hex = block.get("timestamp", "0x0")
        block_timestamp = int(block_timestamp_hex, 16)
        block_time = datetime.fromtimestamp(block_timestamp, timezone.utc)
        current_time = datetime.now(timezone.utc)
        latency = (current_time - block_time).total_seconds()
        return latency


class HTTPEthCallLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects transaction latency for endpoints using eth_call to simulate a transaction.
    This metric tracks the time taken for a simulated transaction (eth_call) to be processed by the RPC node.
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
            method="eth_call",
            method_params=[
                {
                    "to": "0xc2edad668740f1aa35e4d8f227fb8e17dca888cd",
                    "data": "0x1526fe270000000000000000000000000000000000000000000000000000000000000001",
                },
                "latest",
            ],
            **kwargs,
        )


class HTTPBlockNumberLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `eth_blockNumber` method.
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
            method="eth_blockNumber",
            method_params=None,
            **kwargs,
        )


class HTTPTxReceiptLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `eth_getTransactionReceipt` method.
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
            method="eth_getTransactionReceipt",
            method_params=[
                "0xf033310487c37a86db8099a738ffa2bb62bb06efeb486a65ff595d411b5321f4"
            ],
            **kwargs,
        )


class HTTPAccBalanceLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `eth_getBalance` method.
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
            method="eth_getBalance",
            method_params=["0x690B9A9E9aa1C9dB991C7721a92d351Db4FaC990", "pending"],
            **kwargs,
        )


class HTTPDebugTraceBlockByNumberLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `debug_traceBlockByNumber` method.
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
            method="debug_traceBlockByNumber",
            method_params=["latest", {"tracer": "callTracer"}],
            **kwargs,
        )


class HTTPDebugTraceTxLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `debug_traceTransaction` method.
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
            method="debug_traceTransaction",
            method_params=[
                "0x4fc2005859dccab5d9c73c543f533899fe50e25e8d6365c9c335f267d6d12541",
                {"tracer": "callTracer"},
            ],
            **kwargs,
        )
