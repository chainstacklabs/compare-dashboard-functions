"""Solana metrics implementation for HTTP endpoints."""

from typing import Any, Optional

from common.balance_hash import hash_bytes_to_float
from common.metric_types import HttpCallLatencyMetricBase


class HTTPSimulateTxLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the simulateTransaction method."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "simulateTransaction"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters for simulating a token transfer."""
        return [
            "AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAAEDArczbMia1tLmq7zz4DinMNN0pJ1JtLdqIJPUw3YrGCzYAMHBsgN27lcgB6H2WQvFgyZuJYHa46puOQo9yQ8CVQbd9uHXZaGT2cvhRs7reawctIXtX1s3kTqM9YV+/wCp20C7Wj2aiuk5TReAXo+VTVg8QTHjs0UjNMMKCvpzZ+ABAgEBARU=",
            # blockhash is replaced with the latest at send time
            {"encoding": "base64", "replaceRecentBlockhash": True},
        ]


class HTTPGetRecentBlockhashLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the getLatestBlockhash method.

    Also captures the current slot from the response context for block lag tracking.
    """

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "getLatestBlockhash"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get empty parameters list for blockhash retrieval."""
        return []

    def _on_json_response(self, json_response: dict[str, Any]) -> None:
        """Capture slot from result.context.slot for block lag tracking."""
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
        """Return the RPC method name."""
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
        """Return the RPC method name."""
        return "getBalance"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters for balance check of monitoring address."""
        return ["9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"]


class HTTPGetBlockLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the getBlock method."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
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


# USDC mint: an SPL token mint with a moving but deterministic ``supply``
# field embedded in the account ``data`` (changes with mints/burns). Pinning
# ``getAccountInfo`` to a finalized slot via ``minContextSlot`` makes every
# healthy provider return identical bytes, so the canonical hash diverges
# only when a provider serves stale or non-canonical state.
_AGREEMENT_PROBE_ACCOUNT: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


class HTTPAccountAgreementMetric(HttpCallLatencyMetricBase):
    """Cross-provider Data agreement for Solana account state.

    Pins ``getAccountInfo`` to the same historical slot across providers via
    ``minContextSlot`` so each provider returns identical bytes. The slot is
    taken verbatim from ``state_data["old_block"]`` (already populated by the
    state-update cron, same field the v1 balance probes use). The captured
    fields (owner, lamports, executable, rentEpoch, base64 data) are
    canonicalised and hashed to a 52-bit float, then emitted as
    ``metric_type=account_observed`` with ``block_number=<slot_hex>`` so the
    follow-up Grafana panel can join on the slot.
    """

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "getAccountInfo"

    @staticmethod
    def validate_state(state_data: dict[str, Any]) -> bool:
        """Require the historical-slot anchor in state data."""
        return bool(state_data and state_data.get("old_block"))

    @staticmethod
    def get_params_from_state(state_data: dict[str, Any]) -> list[Any]:
        """Build getAccountInfo params pinned to the historical slot."""
        anchor_slot = int(state_data["old_block"])
        return [
            _AGREEMENT_PROBE_ACCOUNT,
            {
                "encoding": "base64",
                "commitment": "finalized",
                "minContextSlot": anchor_slot,
            },
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Stash the anchor slot hex for the account_observed emit step."""
        state_data = kwargs.get("state_data") or {}
        super().__init__(*args, **kwargs)
        anchor_slot = int(state_data["old_block"])
        self._anchor_slot_hex: str = hex(anchor_slot)
        self._captured_account_hash: Optional[float] = None

    def mark_failure(self) -> None:
        """Clear the captured hash on failure to suppress the emit."""
        super().mark_failure()
        self._captured_account_hash = None

    def _on_json_response(self, json_response: dict[str, Any]) -> None:
        """Canonicalise the account value fields and hash them."""
        result = json_response.get("result")
        if not isinstance(result, dict):
            return
        value = result.get("value")
        if not isinstance(value, dict):
            # Account may legitimately be missing at this slot; skip emit.
            return
        owner = str(value.get("owner", ""))
        lamports = int(value.get("lamports", 0))
        executable = bool(value.get("executable", False))
        rent_epoch = int(value.get("rentEpoch", 0))
        data_field = value.get("data", [])
        data_b64 = data_field[0] if isinstance(data_field, list) and data_field else ""
        canonical = (
            f"{owner}|{lamports}|{int(executable)}|{rent_epoch}|{data_b64}"
        ).encode()
        self._captured_account_hash = hash_bytes_to_float(canonical)


class HTTPGetProgramAccsLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for the getProgramAccounts method."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "getProgramAccounts"

    @staticmethod
    def get_params_from_state(state_data: dict) -> list:
        """Get parameters for program accounts query."""
        return [
            "FsJ3A3u2vn5cTVofAjvy6y5kwABJAqYWpe4975bi2epH",
            {"encoding": "jsonParsed"},
        ]
