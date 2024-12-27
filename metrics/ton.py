"""TON (The Open Network) metrics implementation for HTTP endpoints."""

from common.metric_config import MetricConfig, MetricLabels
from common.metric_types import HttpCallLatencyMetricBase


class HTTPRunGetMethodLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `runGetMethod` method.
    """

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs
    ):
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            method="runGetMethod",
            method_params={
                "address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
                "method": "get_wallet_address",
                "stack": [
                    [
                        "tvm.Slice",
                        "te6cckEBAQEAJAAAQ4AbUzrTQYTUv8s/I9ds2TSZgRjyrgl2S2LKcZMEFcxj6PARy3rF",
                    ]
                ],
            },
            **kwargs
        )


class HTTPGetBlockHeaderLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `getBlockHeader` method.
    """

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs
    ):
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            method="getBlockHeader",
            method_params={
                "workchain": -1,
                "shard": "-9223372036854775808",
                "seqno": 39064874,
            },
            **kwargs
        )


class HTTPGetWalletTxsLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `getWalletInformation` method.
    """

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs
    ):
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            method="getWalletInformation",
            method_params={
                "address": "EQDtFpEwcFAEcRe5mLVh2N6C0x-_hJEM7W61_JLnSF74p4q2"
            },
            **kwargs
        )


class HTTPGetAddressBalanceLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `getAddressBalance` method.
    """

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs
    ):
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            method="getAddressBalance",
            method_params={
                "address": "EQDtFpEwcFAEcRe5mLVh2N6C0x-_hJEM7W61_JLnSF74p4q2"
            },
            **kwargs
        )


class HTTPGetBlockTxsLatencyMetric(HttpCallLatencyMetricBase):
    """
    Collects call latency for the `getBlockTransactions` method.
    """

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs
    ):
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            method="getBlockTransactions",
            method_params={
                "workchain": -1,
                "shard": "-9223372036854775808",
                "seqno": 39064874,
                "count": 40,
            },
            **kwargs
        )
