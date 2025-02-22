"""TON (The Open Network) metrics implementation for HTTP endpoints."""

from common.metric_types import HttpCallLatencyMetricBase


class HTTPRunGetMethodLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for smart contract method execution."""

    @property
    def method(self) -> str:
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
        return "getWalletInformation"

    @staticmethod
    def get_params_from_state(state_data: dict) -> dict:
        """Returns parameters for TON wallet query."""
        return {"address": "EQDtFpEwcFAEcRe5mLVh2N6C0x-_hJEM7W61_JLnSF74p4q2"}


class HTTPGetAddressBalanceLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for TON address balance queries."""

    @property
    def method(self) -> str:
        return "getAddressBalance"

    @staticmethod
    def get_params_from_state(state_data: dict) -> dict:
        """Returns parameters for TON address balance check."""
        return {"address": "EQDtFpEwcFAEcRe5mLVh2N6C0x-_hJEM7W61_JLnSF74p4q2"}


class HTTPGetBlockTxsLatencyMetric(HttpCallLatencyMetricBase):
    """Collects call latency for TON block transactions retrieval."""

    @property
    def method(self) -> str:
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
