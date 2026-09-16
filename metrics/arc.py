"""Arc EVM metrics implementation for HTTP endpoints."""

from typing import Any

from common.metric_types import (
    EVMAccBalanceLatencyMetric,
    EVMBlockNumberLatencyMetric,
    HttpCallLatencyMetricBase,
)

# Verified active contracts on Arc mainnet (chain 5042), 2026-09-16.
USDC = "0x3600000000000000000000000000000000000000"  # gas-token predeploy (6 dec)
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


class HTTPEthCallLatencyMetric(HttpCallLatencyMetricBase):
    """Collects response time for eth_call simulation."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "eth_call"

    @staticmethod
    def get_params_from_state(state_data: dict[str, Any]) -> list[Any]:
        """Get eth_call parameters for USDC balanceOf a known holder."""
        return [
            {
                "to": USDC,
                # balanceOf a known non-zero USDC holder (address in data below)
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
    def validate_state(state_data: dict[str, Any]) -> bool:
        """Validate blockchain state contains transaction hash."""
        return bool(state_data and state_data.get("tx"))

    @staticmethod
    def get_params_from_state(state_data: dict[str, Any]) -> list[Any]:
        """Get parameters using transaction hash from state."""
        return [state_data["tx"]]


class HTTPAccBalanceLatencyMetric(EVMAccBalanceLatencyMetric):
    """eth_getBalance latency for Arc."""

    # Largest active native-balance holder on Arc; the balance moves on
    # practically every block, so successive cron rounds sample different
    # values rather than a constant.
    probe_address = "0x8366a39cc670b4001a1121b8f6a443a643e40951"


class HTTPDebugTraceTxLatencyMetric(HttpCallLatencyMetricBase):
    """Collects latency for transaction tracing."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "debug_traceTransaction"

    @staticmethod
    def validate_state(state_data: dict[str, Any]) -> bool:
        """Validate blockchain state contains transaction hash."""
        return bool(state_data and state_data.get("tx"))

    @staticmethod
    def get_params_from_state(state_data: dict[str, Any]) -> list[Any]:
        """Get parameters using transaction hash from state."""
        return [state_data["tx"], {"tracer": "callTracer"}]


class HTTPDebugTraceBlockByNumberLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the `debug_traceBlockByNumber` method."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "debug_traceBlockByNumber"

    @staticmethod
    def get_params_from_state(state_data: dict[str, Any]) -> list[Any]:
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
    def validate_state(state_data: dict[str, Any]) -> bool:
        """Validates that required old block number exists in state data."""
        return bool(state_data and state_data.get("old_block"))

    @staticmethod
    def get_params_from_state(state_data: dict[str, Any]) -> list[Any]:
        """Get parameters for USDC transfer logs from a recent block range."""
        from_block_hex = state_data["old_block"]
        from_block_int = int(from_block_hex, 16)
        to_block_int: int = max(0, from_block_int + 100)
        to_block_hex: str = hex(to_block_int)

        return [
            {
                "fromBlock": from_block_hex,
                "toBlock": to_block_hex,
                "address": USDC,
                "topics": [TRANSFER_TOPIC],
            }
        ]
