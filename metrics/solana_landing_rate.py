"""Solana landing rate metrics with priority fees."""

import asyncio
import os
import random
import time
from enum import Enum
from typing import Optional

import base58
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.instruction import Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.rpc.responses import (
    GetLatestBlockhashResp,
    GetSignatureStatusesResp,
    GetSlotResp,
    SendTransactionResp,
)
from solders.transaction import Transaction
from solders.transaction_status import TransactionConfirmationStatus, TransactionStatus

from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels
from common.metric_types import HttpMetric
from common.metrics_handler import MetricsHandler
from config.defaults import MetricsServiceConfig


class RegionCode(str, Enum):
    """Region codes for memo text generation."""

    SFO1 = "01"
    FRA1 = "02"
    SIN1 = "03"
    DEFAULT = "00"


def generate_fixed_memo(region: str) -> str:
    """Generate fixed-length memo text with region identifier."""
    region_id = getattr(RegionCode, region.upper(), RegionCode.DEFAULT)
    timestamp = int(time.time() * 1000)
    random_id = random.randint(0, 999)
    return f"{region_id}_{random_id:03d}_{timestamp:013d}"


class SolanaLandingMetric(HttpMetric):
    POLL_INTERVAL = 5.0  # seconds for polling getSignatureStatuses
    MEMO_PROGRAM_ID = "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo"

    def __init__(
        self,
        handler: "MetricsHandler",
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs,
    ) -> None:
        http_endpoint = kwargs.get("http_endpoint")
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            http_endpoint=http_endpoint,
        )
        self.method = "sendTransaction"
        self.labels.update_label(MetricLabelKey.API_METHOD, self.method)

        self.private_key: bytes = base58.b58decode(os.environ["SOLANA_PRIVATE_KEY"])
        self.keypair: Keypair = Keypair.from_bytes(self.private_key)
        self._slot_diff = 0

    async def _create_client(self) -> AsyncClient:
        endpoint: str = self.get_endpoint()
        return AsyncClient(endpoint)

    async def _get_slot(self, client: AsyncClient) -> int:
        response: GetSlotResp = await client.get_slot(
            MetricsServiceConfig.SOLANA_CONFIRMATION_LEVEL
        )  # type: ignore
        if not response or response.value is None:
            raise ValueError("Failed to get current slot")
        return response.value

    async def _check_status(self, client: AsyncClient, signature: str) -> int | None:
        """Check single transaction status."""
        response: GetSignatureStatusesResp = await client.get_signature_statuses(
            [signature]  # type: ignore
        )
        if not response or not response.value:
            return None

        status: TransactionStatus | None = response.value[0]
        if not status:
            return None

        if status.confirmation_status in [
            TransactionConfirmationStatus.Confirmed,
            TransactionConfirmationStatus.Finalized,
        ]:
            return status.slot

        return None

    async def _wait_for_confirmation(
        self, client: AsyncClient, signature: str, timeout: int
    ) -> int:
        """Wait for transaction confirmation using direct status checks."""
        end_time: float = time.monotonic() + timeout
        while time.monotonic() < end_time:
            status: int | None = await self._check_status(client, signature)
            if status:
                return status
            await asyncio.sleep(self.POLL_INTERVAL)

        raise ValueError(f"Transaction confirmation timeout after {timeout}s")

    async def _prepare_memo_transaction(self, client: AsyncClient) -> Transaction:
        memo_text: str = generate_fixed_memo(
            self.labels.get_label(MetricLabelKey.SOURCE_REGION)  # type: ignore
        )

        compute_limit_ix: Instruction = set_compute_unit_limit(
            MetricsServiceConfig.COMPUTE_LIMIT
        )
        compute_price_ix: Instruction = set_compute_unit_price(
            MetricsServiceConfig.PRIORITY_FEE_MICROLAMPORTS
        )

        memo_ix = Instruction(
            program_id=Pubkey.from_string(self.MEMO_PROGRAM_ID),
            accounts=[],
            data=memo_text.encode(),
        )

        blockhash: GetLatestBlockhashResp = await client.get_latest_blockhash()
        if not blockhash or not blockhash.value:
            raise ValueError("Failed to get latest blockhash")

        return Transaction.new_signed_with_payer(
            [compute_limit_ix, compute_price_ix, memo_ix],
            self.keypair.pubkey(),
            [self.keypair],
            blockhash.value.blockhash,
        )

    async def fetch_data(self) -> Optional[float]:
        # Since we use here an additional value (metric_type),
        # let's initialize all used metric types.
        self.update_metric_value(0, "response_time")
        self.update_metric_value(0, "slot_latency")

        client = None  # type: ignore
        try:
            client: AsyncClient = await self._create_client()
            tx: Transaction = await self._prepare_memo_transaction(client)

            start_slot: int = await self._get_slot(client)
            start_time: float = time.monotonic()

            signature_response: SendTransactionResp = await client.send_transaction(
                tx, TxOpts(skip_preflight=True, max_retries=0)
            )
            if not signature_response or not signature_response.value:
                raise ValueError("Failed to send transaction")

            confirmation_slot: int = await self._wait_for_confirmation(
                client,
                signature_response.value,  # type: ignore
                self.config.timeout,
            )

            # `response_time` is not representative,
            # we don't use it in the visualizations
            response_time: float = time.monotonic() - start_time
            self._slot_diff: int = max(confirmation_slot - start_slot, 0)
            self.update_metric_value(self._slot_diff, "slot_latency")
            return response_time

        finally:
            if client:
                await client.close()

    def process_data(self, value: float) -> float:
        return value
