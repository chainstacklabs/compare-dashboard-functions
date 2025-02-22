"""Solana landing rate metrics with priority fees."""

import asyncio
import logging
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
from solders.rpc.responses import GetSignatureStatusesResp
from solders.transaction import Transaction

from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels
from common.metric_types import HttpMetric
from common.metrics_handler import MetricsHandler
from config.defaults import MetricsServiceConfig


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
        endpoint = self.get_endpoint("sendTransaction")
        return AsyncClient(endpoint)

    async def _get_slot(self, client: AsyncClient) -> int:
        response = await client.get_slot(MetricsServiceConfig.SOLANA_CONFIRMATION_LEVEL)
        if not response or response.value is None:
            raise ValueError("Failed to get current slot")
        return response.value

    async def _confirm_transaction(
        self, client: AsyncClient, signature: str, timeout: int
    ) -> GetSignatureStatusesResp:
        try:
            confirmation_task = asyncio.create_task(
                client.confirm_transaction(
                    signature,
                    commitment=MetricsServiceConfig.SOLANA_CONFIRMATION_LEVEL,
                    # We don't use response time in visualizations,
                    # let's decrease number of polling requests.
                    sleep_seconds=5,
                )
            )
            confirmation = await asyncio.wait_for(confirmation_task, timeout=timeout)
            if not confirmation or not confirmation.context:
                raise ValueError("Invalid confirmation response")
            return confirmation
        except asyncio.TimeoutError:
            raise ValueError(f"Transaction confirmation timeout after {timeout}s")

    async def _prepare_memo_transaction(self, client: AsyncClient) -> Transaction:
        memo_text = generate_fixed_memo(
            self.labels.get_label(MetricLabelKey.SOURCE_REGION)
        )

        compute_limit_ix = set_compute_unit_limit(MetricsServiceConfig.COMPUTE_LIMIT)
        compute_price_ix = set_compute_unit_price(
            MetricsServiceConfig.PRIORITY_FEE_MICROLAMPORTS
        )

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

    async def _check_health(self, client: AsyncClient) -> None:
        """Check node health via getHealth RPC."""
        try:
            response = await client.is_connected()
            if not response:
                raise ValueError(response)
        except Exception as e:
            logging.warning(f"Node health check failed: {e!s}")

    async def fetch_data(self) -> Optional[float]:
        # Since we use here an additional value (metric_type),
        # let's initialize all used metric types.
        self.update_metric_value(0, "response_time")
        self.update_metric_value(0, "slot_latency")

        client = None
        try:
            client = await self._create_client()
            # await self._check_health(client)
            tx = await self._prepare_memo_transaction(client)

            start_slot = await self._get_slot(client)
            start_time = time.monotonic()

            signature_response = await client.send_transaction(
                tx, TxOpts(skip_preflight=True, max_retries=0)
            )
            if not signature_response or not signature_response.value:
                raise ValueError("Failed to send transaction")

            confirmation = await self._confirm_transaction(
                client,
                signature_response.value,
                self.config.timeout,
            )

            response_time = time.monotonic() - start_time
            self._slot_diff = max(confirmation.context.slot - start_slot, 0)
            self.update_metric_value(self._slot_diff, "slot_latency")
            return response_time

        finally:
            if client:
                await client.close()

    def process_data(self, value: float) -> float:
        return value
