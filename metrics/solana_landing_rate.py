"""Solana landing rate metrics with priority fees."""

import asyncio
import os
import random
import time
from typing import Optional

import base58
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.instruction import Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction

from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels
from common.metric_types import HttpMetric
from common.metrics_handler import MetricsHandler

PRIORITY_FEE_MICROLAMPORTS = 200_000
COMPUTE_LIMIT = 10_000


def generate_fixed_memo(region: str) -> str:
    """Generate fixed-length memo text with region identifier."""
    region_map = {
        "sfo1": "01",
        "fra1": "02",
        "sin1": "03",
        "default": "00",
    }
    region_id = region_map.get(region, "00")
    timestamp = int(time.time() * 1000)
    random_id = random.randint(0, 999)
    return f"{region_id}_{random_id:03d}_{timestamp:013d}"


class SolanaLandingMetric(HttpMetric):
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

        self.private_key = base58.b58decode(os.environ["SOLANA_PRIVATE_KEY"])
        self.keypair = Keypair.from_bytes(self.private_key)
        self._slot_diff = 0

    async def _create_client(self) -> AsyncClient:
        return AsyncClient(self.http_endpoint)

    async def _get_slot(self, client: AsyncClient) -> int:
        response = await client.get_slot("confirmed")
        if not response or response.value is None:
            raise ValueError("Failed to get current slot")
        return response.value

    async def _confirm_transaction(
        self, client: AsyncClient, signature: str, timeout: int
    ) -> None:
        try:
            confirmation_task = asyncio.create_task(
                client.confirm_transaction(
                    signature,
                    commitment=os.getenv("CONFIRMATION_LEVEL", "confirmed"),
                    sleep_seconds=0.3,
                )
            )
            await asyncio.wait_for(confirmation_task, timeout=timeout)
        except asyncio.TimeoutError:
            raise ValueError(f"Transaction confirmation timeout after {timeout}s")

    async def _prepare_memo_transaction(self, client: AsyncClient) -> Transaction:
        memo_text = generate_fixed_memo(os.getenv("REGION", "default"))

        compute_limit_ix = set_compute_unit_limit(COMPUTE_LIMIT)
        compute_price_ix = set_compute_unit_price(PRIORITY_FEE_MICROLAMPORTS)

        memo_ix = Instruction(
            program_id=Pubkey.from_string(
                "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo"
            ),
            accounts=[],
            data=memo_text.encode(),
        )

        blockhash = await client.get_latest_blockhash()
        if not blockhash or not blockhash.value:
            raise ValueError("Failed to get latest blockhash")

        return Transaction.new_signed_with_payer(
            [compute_limit_ix, compute_price_ix, memo_ix],
            self.keypair.pubkey(),
            [self.keypair],
            blockhash.value.blockhash,
        )

    async def _update_slot_diff(
        self, client: AsyncClient, signature: str, start_slot: int
    ) -> None:
        status = await client.get_signature_statuses([signature])
        if not status or not status.value[0] or not status.value[0].slot:
            raise ValueError("Failed to get signature status")
        confirmed_slot = status.value[0].slot
        self._slot_diff = max(confirmed_slot - start_slot, 0)

    async def fetch_data(self) -> Optional[float]:
        client = None
        try:
            client = await self._create_client()
            tx = await self._prepare_memo_transaction(client)

            start_time = time.monotonic()
            start_slot = await self._get_slot(client)

            signature_response = await client.send_transaction(
                tx, TxOpts(skip_preflight=True, max_retries=0)
            )
            if not signature_response or not signature_response.value:
                raise ValueError("Failed to send transaction")

            await self._confirm_transaction(
                client,
                signature_response.value,
                int(os.getenv("CONFIRMATION_TIMEOUT", "30")),
            )

            response_time = time.monotonic() - start_time

            await asyncio.sleep(1)
            await self._update_slot_diff(client, signature_response.value, start_slot)
            self.update_metric_value(self._slot_diff, "slot_latency")

            # It doesn't make sense to measure response/confirmation time
            # since slots in Solana always take 400 ms each. The main
            # metric here is the slot latency/delay.
            return response_time

        finally:
            if client:
                await client.close()

    def process_data(self, value: float) -> float:
        return value
