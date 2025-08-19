"""Hyperliquid EVM metrics implementation for HTTP endpoints."""

from common.metric_types import HttpCallLatencyMetricBase


class HTTPEthCallLatencyMetric(HttpCallLatencyMetricBase):
    """Collects response time for eth_call simulation."""

    @property
    def method(self) -> str:
        return "eth_call"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get eth_call parameters for Wrapped HYPE total supply query."""
        return [
            {
                "to": "0x5555555555555555555555555555555555555555",
                "data": "0x18160ddd",
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
        return ["0xFC1286EeddF81d6955eDAd5C8D99B8Aa32F3D2AA", state_data["old_block"]]


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


class HTTPGetLogsLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the eth_getLogs method."""

    @property
    def method(self) -> str:
        return "eth_getLogs"

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
                "address": "0x5555555555555555555555555555555555555555",  # Wrapped HYPE
                "topics": [
                    " 0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65"  # Withdrawal event
                ],
            }
        ]
