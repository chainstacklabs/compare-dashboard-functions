"""Solana landing rate metrics with priority fees."""

import asyncio
import logging
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

LOG_TAG = "[solana-landing]"


class RegionCode(str, Enum):
    """Region codes for memo text generation."""

    SFO1 = "01"
    FRA1 = "02"
    SIN1 = "03"
    DEFAULT = "00"


def generate_memo(region: str, provider: str) -> str:
    """Generate memo text encoding region + provider for Solscan correlation.

    Layout: ``{region}_{provider}_{rand}_{ts_ms}``. Provider is the existing
    metric ``provider`` label, which already disambiguates an endpoint's
    ``http_endpoint`` (e.g. ``Chainstack``) from its ``tx_endpoint``
    (``Chainstack_tx``) via the factory in ``common/factory.py``. Length
    varies by provider (10-17 chars); no measurable impact on landing rate
    (tx well under 1232-byte cap, memo CU well under ``COMPUTE_LIMIT``).
    """
    region_id = getattr(RegionCode, region.upper(), RegionCode.DEFAULT).value
    timestamp = int(time.time() * 1000)
    random_id = random.randint(0, 999)
    return f"{region_id}_{provider}_{random_id:03d}_{timestamp:013d}"


class SolanaLandingMetric(HttpMetric):
    """Measures Solana transaction landing rate and slot latency via memo tx."""

    POLL_INTERVAL = 5.0  # seconds for polling getSignatureStatuses
    MEMO_PROGRAM_ID = "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo"

    def __init__(
        self,
        handler: "MetricsHandler",
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs: object,
    ) -> None:
        """Initialize with handler, metric name, labels, config, and endpoint kwargs."""
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
        self._last_status: Optional[TransactionStatus] = None

    def _log_ctx(self) -> str:
        """Return short structured context (provider, region) for log lines."""
        return (
            f"provider={self.labels.get_label(MetricLabelKey.PROVIDER)} "
            f"region={self.labels.get_label(MetricLabelKey.SOURCE_REGION)}"
        )

    def mark_failure(self) -> None:
        """Zero everything except signer_balance — wallet state is its own signal."""
        preserved = self.values.pop("signer_balance", None)
        super().mark_failure()
        if preserved is not None:
            self.values["signer_balance"] = preserved

    async def _create_client(self) -> AsyncClient:
        endpoint: str = self.get_endpoint()
        return AsyncClient(endpoint)

    async def _capture_signer_balance(self, client: AsyncClient) -> None:
        """Fetch signer SOL balance and emit as signer_balance value-type.

        Survives ``mark_failure`` via the override above — wallet health
        is a separate signal from whether this particular send landed, so
        the dashboard can disambiguate "all RPCs failing" from "fee wallet
        drained" at a glance.
        """
        try:
            response = await client.get_balance(self.keypair.pubkey())
            if response and response.value is not None:
                self.update_metric_value(response.value, "signer_balance")
        except Exception as e:
            logging.warning(
                f"{LOG_TAG} signer balance fetch failed {self._log_ctx()}: {e!r}"
            )

    async def _get_slot(self, client: AsyncClient) -> int:
        response: GetSlotResp = await client.get_slot(
            MetricsServiceConfig.SOLANA_CONFIRMATION_LEVEL
        )  # type: ignore
        if not response or response.value is None:
            raise ValueError(f"getSlot returned empty {self._log_ctx()}")
        return response.value

    async def _check_status(self, client: AsyncClient, signature: str) -> int | None:
        """Check single transaction status.

        Returns the confirmation slot if the tx is Confirmed/Finalized, ``None``
        if it has not yet reached that threshold. Raises immediately if the
        status carries an ``err`` (on-chain revert) — that is a distinct
        failure mode from "not landed yet" and we don't want it masked by the
        full polling timeout.
        """
        response: GetSignatureStatusesResp = await client.get_signature_statuses(
            [signature]  # type: ignore
        )
        if not response or not response.value:
            return None

        status: TransactionStatus | None = response.value[0]
        if not status:
            return None

        if status.err is not None:
            logging.error(
                f"{LOG_TAG} on-chain revert sig={signature} slot={status.slot} "
                f"err={status.err!r} {self._log_ctx()}"
            )
            raise ValueError(f"on-chain revert at slot {status.slot}: {status.err!r}")

        self._last_status = status

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
        self._last_status = None
        end_time: float = time.monotonic() + timeout
        polls = 0
        while time.monotonic() < end_time:
            polls += 1
            confirmation_slot: int | None = await self._check_status(client, signature)
            if confirmation_slot is not None:
                return confirmation_slot
            await asyncio.sleep(self.POLL_INTERVAL)

        last = self._last_status
        last_repr = (
            f"status={last.confirmation_status} slot={last.slot}"
            if last is not None
            else "never_seen"
        )
        logging.warning(
            f"{LOG_TAG} confirmation timeout sig={signature} polls={polls} "
            f"last={last_repr} timeout={timeout}s {self._log_ctx()}"
        )
        raise ValueError(
            f"confirmation timeout after {timeout}s sig={signature} last={last_repr}"
        )

    async def _prepare_memo_transaction(self, client: AsyncClient) -> Transaction:
        memo_text: str = generate_memo(
            self.labels.get_label(MetricLabelKey.SOURCE_REGION),  # type: ignore
            self.labels.get_label(MetricLabelKey.PROVIDER),  # type: ignore
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
            raise ValueError(f"getLatestBlockhash returned empty {self._log_ctx()}")

        return Transaction.new_signed_with_payer(
            [compute_limit_ix, compute_price_ix, memo_ix],
            self.keypair.pubkey(),
            [self.keypair],
            blockhash.value.blockhash,
        )

    async def _submit(
        self, client: AsyncClient, tx: Transaction, tag: str = LOG_TAG
    ) -> str:
        """Send the transaction; log RPC errors with context before re-raising.

        Returns the signature as a string. Falsy response is treated as a send
        failure and raises ``ValueError`` with provider context.
        """
        try:
            signature_response: SendTransactionResp = await client.send_transaction(
                tx, TxOpts(skip_preflight=True, max_retries=0)
            )
        except Exception as e:
            logging.error(f"{tag} sendTransaction failed {self._log_ctx()}: {e!r}")
            raise
        if not signature_response or not signature_response.value:
            raise ValueError(
                f"sendTransaction returned empty response {self._log_ctx()}"
            )
        return str(signature_response.value)

    async def fetch_data(self) -> Optional[float]:
        """Send a memo transaction and return elapsed wall-clock time.

        Initializes both response_time and slot_latency metric types, submits
        a signed memo transaction, waits for confirmation, and stores the slot
        difference as slot_latency. Also captures the signer's SOL balance via
        a separate value-type so the dashboard can distinguish fee-wallet
        drain from RPC outages.
        """
        # Since we use here an additional value (metric_type),
        # let's initialize all used metric types.
        self.update_metric_value(0, "response_time")
        self.update_metric_value(0, "slot_latency")

        client: Optional[AsyncClient] = None
        try:
            client = await self._create_client()
            await self._capture_signer_balance(client)
            tx: Transaction = await self._prepare_memo_transaction(client)

            start_slot: int = await self._get_slot(client)
            start_time: float = time.monotonic()

            signature: str = await self._submit(client, tx)
            logging.info(
                f"{LOG_TAG} submitted sig={signature} start_slot={start_slot} "
                f"{self._log_ctx()}"
            )

            confirmation_slot: int = await self._wait_for_confirmation(
                client, signature, self.config.timeout
            )

            # `response_time` is not representative,
            # we don't use it in the visualizations
            response_time: float = time.monotonic() - start_time
            self._slot_diff: int = confirmation_slot - start_slot
            if self._slot_diff < 0:
                logging.warning(
                    f"{LOG_TAG} negative slot diff sig={signature} "
                    f"confirmation_slot={confirmation_slot} "
                    f"start_slot={start_slot} {self._log_ctx()}"
                )
                raise ValueError(
                    f"negative slot diff: {self._slot_diff} "
                    f"(confirmation={confirmation_slot}, start={start_slot})"
                )
            self.update_metric_value(self._slot_diff, "slot_latency")
            return response_time

        finally:
            if client:
                await client.close()

    def process_data(self, value: float) -> float:
        """Return the raw latency value unchanged."""
        return value
