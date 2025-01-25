"""Solana landing rate metrics for measuring transaction confirmation time and slot latency."""

import asyncio
import os
import time
from typing import Tuple

import base58
from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.instruction import Instruction
from solders.transaction import Transaction

from common.metric_config import MetricConfig, MetricLabels
from common.metric_types import HttpCallLatencyMetricBase


class SolanaMetricBase(HttpCallLatencyMetricBase):
    RETRIES = 5
    RETRY_DELAY = 5

    def __init__(self, handler, metric_name, labels, config, **kwargs):
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            method="sendTransaction",
            **kwargs,
        )
        self.private_key = base58.b58decode(os.environ["SOLANA_PRIVATE_KEY"])
        self.keypair = Keypair.from_bytes(self.private_key)


class SolanaLandingMetric(SolanaMetricBase):
    async def send_and_confirm_tx(self, client: Client) -> Tuple[float, int]:
        """Sends memo tx and waits for confirmation, returns time delta and slot diff"""
        start_time = time.monotonic()
        start_slot = (await client.get_slot())["result"]

        memo_ix = Instruction(
            program_id=bytes.fromhex("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"),
            accounts=[],
            data=f"metric_{int(time.time())}_{self.labels.get_label('provider')}".encode(),
        )
        tx = Transaction.new_with_payer([memo_ix], self.keypair.pubkey())

        blockhash = await client.get_latest_blockhash()
        if "error" in blockhash:
            raise ValueError(f"Failed to get blockhash: {blockhash['error']}")

        tx.message.recent_blockhash = bytes.fromhex(blockhash["result"]["value"]["blockhash"])
        tx.sign([self.keypair])

        encoded_tx = base58.b58encode(bytes(tx)).decode("utf-8")
        signature = await client.send_raw_transaction(encoded_tx)

        if "error" in signature:
            raise ValueError(f"Failed to send tx: {signature['error']}")

        for attempt in range(self.RETRIES):
            try:
                status = await client.get_transaction(
                    signature["result"], commitment="confirmed"
                )
                if status and status["result"]:
                    return (
                        time.monotonic() - start_time,
                        status["result"]["slot"] - start_slot,
                    )

                await asyncio.sleep(self.RETRY_DELAY)
            except Exception as e:
                if attempt == self.RETRIES - 1:
                    raise ValueError(f"Failed to confirm tx: {str(e)}")
                await asyncio.sleep(self.RETRY_DELAY)

        raise ValueError("Transaction not confirmed after retries")

    async def collect_metric(self) -> None:
        """Collects landing rate and slot metrics for each provider"""
        try:
            client = Client(self.http_endpoint)
            latency, slot_diff = await self.send_and_confirm_tx(client)

            self.update_metric_value(latency)
            self.mark_success()

            # Create slot latency metric - workaround for having a multivalue metric
            slot_metric = SolanaSlotMetric(
                handler=self.handler,
                metric_name=f"{self.metric_name}_slot_diff",
                labels=self.labels,
                config=self.config,
                http_endpoint=self.http_endpoint,
            )
            slot_metric.update_metric_value(slot_diff)

        except Exception as e:
            self.mark_failure()
            self.handle_error(e)


class SolanaSlotMetric(SolanaMetricBase):
    """Metric for tracking slot difference between tx submission and confirmation"""

    def process_data(self, value: float) -> float:
        return value
