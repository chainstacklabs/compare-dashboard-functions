"""Base EVM metrics implementation for HTTP endpoints."""

from common.metric_types import HttpCallLatencyMetricBase


class HTTPEthCallLatencyMetric(HttpCallLatencyMetricBase):
    """Collects response time for eth_call simulation."""

    @property
    def method(self) -> str:
        return "eth_call"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get eth_call parameters for USDC token balance query."""
        return [
            {
                "to": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
                "data": "0x70a082310000000000000000000000001985ea6e9c68e1c272d8209f3b478ac2fdb25c87",
            },
            "latest",
        ]


class HTTPTxReceiptLatencyMetric(HttpCallLatencyMetricBase):
    """Collects latency for transaction receipt retrieval."""

    @property
    def method(self) -> str:
        return "eth_getTransactionReceipt"

    @staticmethod
    def validate_state(state_data: dict) -> bool:
        """Validate blockchain state contains transaction hash."""
        return bool(state_data and state_data.get("tx"))

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters using transaction hash from state."""
        return [state_data["tx"]]


class HTTPAccBalanceLatencyMetric(HttpCallLatencyMetricBase):
    """Collects latency for account balance queries."""

    @property
    def method(self) -> str:
        return "eth_getBalance"

    @staticmethod
    def validate_state(state_data: dict) -> bool:
        """Validates that required block number (hex) exists in state data."""
        return bool(state_data and state_data.get("old_block"))

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters with fixed monitoring address."""
        return ["0xF977814e90dA44bFA03b6295A0616a897441aceC", state_data["old_block"]]


class HTTPDebugTraceTxLatencyMetric(HttpCallLatencyMetricBase):
    """Collects latency for transaction tracing."""

    @property
    def method(self) -> str:
        return "debug_traceTransaction"

    @staticmethod
    def validate_state(state_data: dict) -> bool:
        """Validate blockchain state contains transaction hash."""
        return bool(state_data and state_data.get("tx"))

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters using transaction hash from state."""
        return [state_data["tx"], {"tracer": "callTracer"}]


class HTTPDebugTraceBlockByNumberLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the `debug_traceBlockByNumber` method."""

    @property
    def method(self) -> str:
        return "debug_traceBlockByNumber"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get fixed parameters for latest block tracing."""
        return ["latest", {"tracer": "callTracer"}]


class HTTPBlockNumberLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the `eth_blockNumber` method."""

    @property
    def method(self) -> str:
        return "eth_blockNumber"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get empty parameter list for block number query."""
        return []
