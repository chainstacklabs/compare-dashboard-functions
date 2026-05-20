"""TON (The Open Network) metrics implementation for HTTP endpoints."""

from typing import Any, Optional

from common.balance_hash import hash_bytes_to_float
from common.metric_types import HttpCallLatencyMetricBase


class HTTPGetMasterchainInfoLatencyMetric(HttpCallLatencyMetricBase):
    """getMasterchainInfo latency; captures seqno for lag tracking."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "getMasterchainInfo"

    def _on_json_response(self, json_response: dict[str, Any]) -> None:
        """Capture result.last.seqno for block lag tracking."""
        result = json_response.get("result")
        if isinstance(result, dict):
            last = result.get("last")
            if isinstance(last, dict):
                seqno = last.get("seqno")
                if isinstance(seqno, int):
                    self._captured_block_number = seqno


class HTTPRunGetMethodLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for smart contract method execution."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "runGetMethod"

    @staticmethod
    def get_params_from_state(state_data: dict) -> dict:
        """Returns parameters for TVM smart contract method call."""
        return {
            "address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
            "method": "get_wallet_address",
            "stack": [
                [
                    "tvm.Slice",
                    "te6cckEBAQEAJAAAQ4AbUzrTQYTUv8s/I9ds2TSZgRjyrgl2S2LKcZMEFcxj6PARy3rF",
                ]
            ],
        }


class HTTPGetBlockHeaderLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for masterchain block header retrieval."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "getBlockHeader"

    @staticmethod
    def validate_state(state_data: dict) -> bool:
        """Validates that required block identifier exists in state data."""
        return bool(state_data and state_data.get("old_block"))

    @staticmethod
    def get_params_from_state(state_data: dict) -> dict:
        """Returns parameters using TON block identifier components."""
        workchain, shard, seqno = state_data["old_block"].split(":")
        return {
            "workchain": int(workchain),
            "shard": shard,
            "seqno": int(seqno),
        }


class HTTPGetWalletTxsLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for TON wallet information retrieval."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "getWalletInformation"

    @staticmethod
    def get_params_from_state(state_data: dict) -> dict:
        """Returns parameters for TON wallet query."""
        return {"address": "EQDtFpEwcFAEcRe5mLVh2N6C0x-_hJEM7W61_JLnSF74p4q2"}


class HTTPGetAddressBalanceLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for TON address balance queries."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "getAddressBalance"

    @staticmethod
    def get_params_from_state(state_data: dict) -> dict:
        """Returns parameters for TON address balance check."""
        return {"address": "EQDtFpEwcFAEcRe5mLVh2N6C0x-_hJEM7W61_JLnSF74p4q2"}


# USDT jetton master: ``get_jetton_data`` returns total_supply / admin /
# content / wallet_code on the v2 ``runGetMethod`` surface, which all four
# TON providers (Chainstack, QuickNode, TonCenter, dRPC) accept with a
# ``seqno`` parameter for historical pinning. Empirically verified that the
# seqno param is honoured and all four agree on identical stack output at
# the pinned masterchain seqno. ``total_supply`` moves on Tether mint/burn
# events, giving a moving-but-deterministic target.
_AGREEMENT_PROBE_ADDRESS: str = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"


def _canonicalise_stack(stack: Any) -> str:
    """Render a TVM stack as a deterministic, provider-agnostic string.

    Stack entries come back as ``[type, value]`` pairs where ``value`` is
    either a hex string (``num``) or a dict carrying a base64 BoC plus a
    decoded ``object`` tree (``cell``/``slice``). We pin to the encoded BoC
    bytes only — the decoded ``object`` view varies in shape between
    providers and isn't load-bearing for agreement.
    """
    if not isinstance(stack, list):
        return ""
    parts: list[str] = []
    for entry in stack:
        if not isinstance(entry, list) or len(entry) != 2:
            parts.append(repr(entry))
            continue
        tag, value = entry
        if isinstance(value, dict):
            parts.append(f"{tag}:{value.get('bytes', '')}")
        else:
            parts.append(f"{tag}:{value}")
    return "|".join(parts)


class HTTPAccountAgreementMetric(HttpCallLatencyMetricBase):
    """Cross-provider Data agreement for TON account state.

    Calls v2 ``runGetMethod`` with ``get_jetton_data`` on the USDT jetton
    master, pinned to a settled masterchain seqno via the ``seqno`` param.
    All four TON providers in our pool (Chainstack, QuickNode, TonCenter,
    dRPC) accept the param and return identical stacks at the pinned point.
    The stack (total_supply, mintable flag, admin address, content cell,
    wallet code cell) is canonicalised and hashed to a 52-bit float, then
    emitted as ``metric_type=account_observed`` with the seqno as
    ``block_number=<seqno_hex>`` so the dashboard panel can join per round.
    """

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "runGetMethod"

    @staticmethod
    def validate_state(state_data: dict[str, Any]) -> bool:
        """Require the masterchain block identifier in state data."""
        return bool(state_data and state_data.get("old_block"))

    @staticmethod
    def get_params_from_state(state_data: dict[str, Any]) -> dict[str, Any]:
        """Return runGetMethod params pinned to the masterchain seqno."""
        seqno = int(state_data["old_block"].split(":")[2])
        return {
            "address": _AGREEMENT_PROBE_ADDRESS,
            "method": "get_jetton_data",
            "stack": [],
            "seqno": seqno,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Stash the seqno hex for the account_observed emit step."""
        state_data = kwargs.get("state_data") or {}
        super().__init__(*args, **kwargs)
        seqno = int(state_data["old_block"].split(":")[2])
        self._anchor_seqno_hex: str = hex(seqno)
        self._captured_account_hash: Optional[float] = None

    def mark_failure(self) -> None:
        """Clear the captured hash on failure to suppress the emit."""
        super().mark_failure()
        self._captured_account_hash = None

    def _on_json_response(self, json_response: dict[str, Any]) -> None:
        """Canonicalise the TVM stack and hash it."""
        result = json_response.get("result")
        if not isinstance(result, dict):
            return
        if result.get("exit_code", 0) != 0:
            return
        canonical = _canonicalise_stack(result.get("stack")).encode()
        if not canonical:
            return
        self._captured_account_hash = hash_bytes_to_float(canonical)


class HTTPGetBlockTxsLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for TON block transactions retrieval."""

    @property
    def method(self) -> str:
        """Return the RPC method name."""
        return "getBlockTransactions"

    @staticmethod
    def validate_state(state_data: dict) -> bool:
        """Validates that required block identifier exists in state data."""
        return bool(state_data and state_data.get("block"))

    @staticmethod
    def get_params_from_state(state_data: dict) -> dict:
        """Returns parameters using TON block identifier components."""
        workchain, shard, seqno = state_data["block"].split(":")
        return {
            "workchain": int(workchain),
            "shard": shard,
            "seqno": int(seqno),
            "count": 40,
        }
