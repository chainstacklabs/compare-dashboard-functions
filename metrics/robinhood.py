"""Robinhood (Arbitrum Orbit) EVM metrics implementation for HTTP endpoints."""

from common.metric_types import (
    EVMAccBalanceLatencyMetric,
    EVMBlockNumberLatencyMetric,
    HttpCallLatencyMetricBase,
)

# Verified active contracts on Robinhood mainnet (chain 4663), 2026-07-20.
USDG = "0x5fc5360d0400a0fd4f2af552add042d716f1d168"  # busiest stablecoin (6 dec)
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


class HTTPEthCallLatencyMetric(HttpCallLatencyMetricBase):
    """Collects response time for eth_call simulation."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "eth_call"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get eth_call parameters for USDG balanceOf a known holder."""
        return [
            {
                "to": USDG,
                # balanceOf a known non-zero USDG holder (address in data below)
                "data": "0x70a082310000000000000000000000008366a39cc670b4001a1121b8f6a443a643e40951",  # noqa: E501
            },
            "latest",
        ]


class HTTPTxReceiptLatencyMetric(HttpCallLatencyMetricBase):
    """Collects latency for transaction receipt retrieval."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "eth_getTransactionReceipt"

    @staticmethod
    def validate_state(state_data: dict) -> bool:
        """Validate blockchain state contains transaction hash."""
        return bool(state_data and state_data.get("tx"))

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters using transaction hash from state."""
        return [state_data["tx"]]


class HTTPAccBalanceLatencyMetric(EVMAccBalanceLatencyMetric):
    """eth_getBalance latency for Robinhood."""

    # WETH — most active contract on Robinhood; holds large native balance that
    # changes block to block, so successive cron rounds sample different values.
    probe_address = "0x0bd7d308f8e1639fab988df18a8011f41eacad73"


class HTTPDebugTraceTxLatencyMetric(HttpCallLatencyMetricBase):
    """Collects latency for transaction tracing."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
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
        """Return the RPC method name."""
        return "debug_traceBlockByNumber"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get fixed parameters for latest block tracing."""
        return ["latest", {"tracer": "callTracer"}]


class HTTPBlockNumberLatencyMetric(EVMBlockNumberLatencyMetric):
    """eth_blockNumber latency; captures raw block number for lag tracking."""


class HTTPGetLogsLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the eth_getLogs method."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "eth_getLogs"

    @staticmethod
    def validate_state(state_data: dict) -> bool:
        """Validates that required old block number exists in state data."""
        return bool(state_data and state_data.get("old_block"))

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters for USDG transfer logs from a recent block range."""
        from_block_hex = state_data["old_block"]
        from_block_int = int(from_block_hex, 16)
        to_block_int: int = max(0, from_block_int + 100)
        to_block_hex: str = hex(to_block_int)

        return [
            {
                "fromBlock": from_block_hex,
                "toBlock": to_block_hex,
                "address": USDG,
                "topics": [TRANSFER_TOPIC],
            }
        ]
