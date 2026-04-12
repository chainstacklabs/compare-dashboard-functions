"""Solana metrics implementation for HTTP endpoints."""

from typing import Any

from common.metric_types import HttpCallLatencyMetricBase


class HTTPSimulateTxLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the simulateTransaction method."""

    @property
    def method(self) -> str:
        return "simulateTransaction"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters for simulating a token transfer."""
        return [
            "AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAAEDArczbMia1tLmq7zz4DinMNN0pJ1JtLdqIJPUw3YrGCzYAMHBsgN27lcgB6H2WQvFgyZuJYHa46puOQo9yQ8CVQbd9uHXZaGT2cvhRs7reawctIXtX1s3kTqM9YV+/wCp20C7Wj2aiuk5TReAXo+VTVg8QTHjs0UjNMMKCvpzZ+ABAgEBARU=",
            # The transaction recent blockhash will be replaced with the most recent blockhash.
            {"encoding": "base64", "replaceRecentBlockhash": True},
        ]


class HTTPGetRecentBlockhashLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the getLatestBlockhash method.

    Also captures the current slot from the response context for block lag tracking.
    """

    @property
    def method(self) -> str:
        return "getLatestBlockhash"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get empty parameters list for blockhash retrieval."""
        return []

    def _on_json_response(self, json_response: dict[str, Any]) -> None:
        result = json_response.get("result")
        if isinstance(result, dict):
            context = result.get("context")
            if isinstance(context, dict):
                slot = context.get("slot")
                if isinstance(slot, int):
                    self._captured_block_number = slot


class HTTPGetTxLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the getTransaction method."""

    @property
    def method(self) -> str:
        return "getTransaction"

    @staticmethod
    def validate_state(state_data: dict) -> bool:
        """Validate blockchain state contains transaction signature."""
        return bool(state_data and state_data.get("tx"))

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters using transaction signature from state."""
        return [
            state_data["tx"],
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
        ]


class HTTPGetBalanceLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the getBalance method."""

    @property
    def method(self) -> str:
        return "getBalance"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters for balance check of monitoring address."""
        return ["9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"]


class HTTPGetBlockLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the getBlock method."""

    @property
    def method(self) -> str:
        return "getBlock"

    @staticmethod
    def validate_state(state_data: dict) -> bool:
        """Validate blockchain state contains block slot number."""
        return bool(state_data and state_data.get("old_block"))

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters using block slot from state."""
        return [
            int(state_data["old_block"]),
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
                "transactionDetails": "none",  # Reduce response size
                "rewards": False,  # Further reduce response size
            },
        ]


class HTTPGetProgramAccsLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the getProgramAccounts method."""

    @property
    def method(self) -> str:
        return "getProgramAccounts"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters for program accounts query."""
        return [
            "FsJ3A3u2vn5cTVofAjvy6y5kwABJAqYWpe4975bi2epH",
            {"encoding": "jsonParsed"},
        ]
