"""Monad EVM metrics implementation for HTTP endpoints."""

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
                "to": "0x754704Bc059F8C67012fEd69BC8A327a5aafb603",
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
        """Get parameters with USDC contract address for monitoring."""
        return ["0x754704Bc059F8C67012fEd69BC8A327a5aafb603", state_data["old_block"]]


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
                "address": "0x754704Bc059F8C67012fEd69BC8A327a5aafb603",  # USDC on Monad
                "topics": [
                    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"  # Transfer event
                ],
            }
        ]
