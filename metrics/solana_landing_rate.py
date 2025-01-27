"""Solana landing rate metrics for measuring transaction confirmation time and slot latency."""

import asyncio
import os
import time
from typing import Optional
import random
import base58

from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair
from solders.instruction import Instruction
from solders.pubkey import Pubkey
from solders.transaction import Transaction

from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels
from common.metric_types import HttpMetric
from common.metrics_handler import MetricsHandler


def generate_fixed_memo(region: str) -> str:
    """Generate fixed-length memo text with region identifier.

    Args:
        region: Deployment region identifier

    Returns:
        A formatted memo string containing region id, random number and timestamp
    """
    region_map = {
        "iad1": "01",
        "sfo1": "02",
        "fra1": "03",
        "hnd1": "04",
        "default": "00",
    }
    region_id = region_map.get(region, "00")
    timestamp = int(time.time() * 1000)
    random_id = random.randint(0, 999)
    return f"{region_id}_{random_id:03d}_{timestamp:013d}"


class SolanaLandingMetric(HttpMetric):
    """Metric for measuring Solana transaction landing time.

    This metric sends a memo transaction and measures the time until confirmation,
    tracking both the elapsed time and slot progression.
    """

    def __init__(
        self,
        handler: "MetricsHandler",
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs,
    ) -> None:
        """Initialize the Solana landing metric.

        Args:
            handler: Metrics collection handler
            metric_name: Name of the metric
            labels: Metric labels
            config: Metric configuration
            **kwargs: Additional arguments including http_endpoint
        """
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
        """Create Solana client instance.

        Returns:
            AsyncClient: Configured Solana RPC client
        """
        return AsyncClient(self.http_endpoint)

    async def _get_slot(self, client: AsyncClient) -> int:
        """Get current slot from the cluster.

        Args:
            client: Solana RPC client

        Returns:
            Current slot number

        Raises:
            ValueError: If slot fetch fails
        """
        response = await client.get_slot()
        if not response or response.value is None:
            raise ValueError("Failed to get current slot")
        return response.value

    async def _confirm_transaction(
        self, client: AsyncClient, signature: str, timeout: int
    ) -> None:
        """Confirm transaction with timeout.

        Args:
            client: Solana RPC client
            signature: Transaction signature to confirm
            timeout: Maximum time to wait for confirmation

        Raises:
            ValueError: If confirmation times out
        """
        try:
            confirmation_task = asyncio.create_task(
                client.confirm_transaction(
                    signature, commitment=os.getenv("CONFIRMATION_LEVEL", "confirmed")
                )
            )
            await asyncio.wait_for(confirmation_task, timeout=timeout)
        except asyncio.TimeoutError:
            raise ValueError(f"Transaction confirmation timeout after {timeout}s")

    async def _prepare_memo_transaction(self, client: AsyncClient) -> Transaction:
        """Prepare memo transaction for sending.

        Args:
            client: Solana RPC client

        Returns:
            Prepared and signed transaction

        Raises:
            ValueError: If blockhash fetch fails
        """
        memo_text = generate_fixed_memo(os.getenv("REGION", "default"))
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
            [memo_ix], self.keypair.pubkey(), [self.keypair], blockhash.value.blockhash
        )

    async def _update_slot_diff(
        self, client: AsyncClient, signature: str, start_slot: int
    ) -> None:
        """Update slot difference measurement.

        Args:
            client: Solana RPC client
            signature: Transaction signature
            start_slot: Starting slot number

        Raises:
            ValueError: If status fetch fails
        """
        status = await client.get_signature_statuses([signature])
        if not status or not status.value[0] or not status.value[0].slot:
            raise ValueError("Failed to get signature status")
        self._slot_diff = max(status.value[0].slot - start_slot, 0)

    async def fetch_data(self) -> Optional[float]:
        """Send transaction and measure confirmation time.

        Returns:
            Time taken for transaction confirmation in seconds

        Raises:
            ValueError: For various RPC or transaction failures
        """
        client = None
        try:
            client = await self._create_client()

            tx = await self._prepare_memo_transaction(client)
            start_time = time.monotonic()
            start_slot = await self._get_slot(client)

            signature_response = await client.send_transaction(tx)
            if not signature_response or not signature_response.value:
                raise ValueError("Failed to send transaction")

            await self._confirm_transaction(
                client,
                signature_response.value,
                int(os.getenv("CONFIRMATION_TIMEOUT", "30")),
            )

            response_time = time.monotonic() - start_time

            """
            await asyncio.sleep(0.4)
            
            await self._update_slot_diff(
                client, 
                signature_response.value, 
                start_slot
            )
            """
            return response_time

        finally:
            if client:
                await client.close()

    def process_data(self, value: float) -> float:
        """Process the measured latency value.

        Args:
            value: Raw latency measurement

        Returns:
            Processed latency value
        """
        return value
