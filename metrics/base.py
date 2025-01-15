"""Base EVM metrics implementation for WebSocket and HTTP endpoints."""

from common.metric_config import MetricConfig, MetricLabels
from common.metric_types import HttpCallLatencyMetricBase


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
                    "to": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
                    "data": "0x70a082310000000000000000000000001985ea6e9c68e1c272d8209f3b478ac2fdb25c87",
                },
                "latest",
            ],
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
                "0x1759c699e6e2b1f249fa0ed605c0de18998bc66556cd6ea3362f92f511aeb06a"
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
            method_params=["0xF977814e90dA44bFA03b6295A0616a897441aceC", "latest"],
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
                "0x317888c89fe0914c6d11be51acf758742afbe0cf1fdac11f19d35d6ed652ac29",
                {"tracer": "callTracer"},
            ],
            **kwargs,
        )
