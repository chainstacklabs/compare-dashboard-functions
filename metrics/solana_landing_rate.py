"""Solana landing rate metrics with priority fees."""

import asyncio
import base64
import logging
import os
import random
import time
from enum import Enum
from typing import Any

import aiohttp
import base58
from solders.hash import Hash
from solders.instruction import Instruction
from solders.keypair import Keypair
from solders.message import MessageV1, TransactionConfig
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

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


def transaction_config() -> TransactionConfig:
    """Return the inline compute budget for the v1 memo transaction.

    A v1 message (SIMD-0385) carries the compute budget in its header instead
    of ``ComputeBudget`` instructions, and states the priority fee as a total in
    lamports rather than a price per compute unit. The total is
    ``COMPUTE_LIMIT * PRIORITY_FEE_MICROLAMPORTS / 1e6``, rounded up, which is
    the fee the runtime charges for that limit and price. The compute unit limit
    and the loaded accounts data size limit must be set explicitly: both default
    to 0 in v1, and a 0 data size limit fails the transaction on-chain with
    ``MaxLoadedAccountsDataSizeExceeded`` before the memo runs.
    """
    limit = MetricsServiceConfig.COMPUTE_LIMIT
    price = MetricsServiceConfig.PRIORITY_FEE_MICROLAMPORTS
    priority_fee = -(-limit * price // 1_000_000)
    return TransactionConfig(
        priority_fee=priority_fee,
        compute_unit_limit=limit,
        loaded_accounts_data_size_limit=(
            MetricsServiceConfig.LOADED_ACCOUNTS_DATA_SIZE_LIMIT
        ),
    )


class SolanaLandingMetric(HttpMetric):
    """Measures Solana transaction landing rate and slot latency via memo tx.

    Sends a version 1 transaction (SIMD-0385). RPC calls go over aiohttp as
    plain JSON-RPC, like the other metrics, and ``solders`` only builds and
    signs the transaction.

    Exempt from the measurement gate for the same reason as the WebSocket
    block metrics — see ``BaseMetric.serialise_measurement``: the measured
    quantity is on-chain confirmation time (seconds), so ms-scale event-loop
    contention is irrelevant, and one probe holding the gate through a
    confirmation poll would starve the rest of the round.
    """

    serialise_measurement = False

    POLL_INTERVAL = 5.0  # seconds between getTransaction polls
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
        if http_endpoint is not None and not isinstance(http_endpoint, str):
            raise TypeError(f"http_endpoint must be str, got {type(http_endpoint)}")
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
        self._slot_diff: int = 0

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

    async def _rpc(
        self, session: aiohttp.ClientSession, method: str, params: list[Any]
    ) -> Any:
        """Send one JSON-RPC request and return its ``result``.

        A non-2xx response raises ``aiohttp.ClientResponseError``, which
        ``handle_error`` already treats like every other HTTP metric (401/403/
        404/429 are logged as warnings). A JSON-RPC error raises ``ValueError``.
        """
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        async with session.post(self.get_endpoint(), json=body) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)
        if not isinstance(payload, dict):
            raise ValueError(f"{method} returned non-object JSON {self._log_ctx()}")
        if "error" in payload:
            raise ValueError(
                f"{method} JSON-RPC error {payload['error']!r} {self._log_ctx()}"
            )
        return payload.get("result")

    async def _capture_signer_balance(self, session: aiohttp.ClientSession) -> None:
        """Fetch signer SOL balance and emit as signer_balance value-type.

        Survives ``mark_failure`` via the override above — wallet health
        is a separate signal from whether this particular send landed, so
        the dashboard can disambiguate "all RPCs failing" from "fee wallet
        drained" at a glance.
        """
        try:
            result = await self._rpc(
                session,
                "getBalance",
                [str(self.keypair.pubkey()), {"commitment": "finalized"}],
            )
            if isinstance(result, dict) and isinstance(result.get("value"), int):
                self.update_metric_value(result["value"], "signer_balance")
        except Exception as e:
            logging.warning(
                f"{LOG_TAG} signer balance fetch failed {self._log_ctx()}: {e!r}"
            )

    async def _get_slot(self, session: aiohttp.ClientSession) -> int:
        result = await self._rpc(
            session,
            "getSlot",
            [{"commitment": MetricsServiceConfig.SOLANA_CONFIRMATION_LEVEL}],
        )
        if not isinstance(result, int):
            raise ValueError(f"getSlot returned {result!r} {self._log_ctx()}")
        return result

    async def _check_status(
        self, session: aiohttp.ClientSession, signature: str
    ) -> int | None:
        """Return the landing slot once the tx is confirmed, else ``None``.

        Uses ``getTransaction`` at ``confirmed`` commitment instead of
        ``getSignatureStatuses``. The latter reads the validator's in-memory
        status cache, which is unreliable across providers — a freshly-landed
        sig can read back ``null``, or stay pinned at ``processed`` for the
        entire poll window, even though it confirmed on-chain in ~1s.
        ``getTransaction`` reads the ledger, so a non-null result is a
        definitive "landed and confirmed" signal on every provider we tested.
        ``maxSupportedTransactionVersion`` must be at least 1 to read back a
        v1 transaction.

        Raises immediately if the tx carries an on-chain error (revert) — a
        distinct failure mode from "not landed yet" that we don't want masked by
        the polling timeout.
        """
        result = await self._rpc(
            session,
            "getTransaction",
            [
                signature,
                {
                    "commitment": MetricsServiceConfig.SOLANA_CONFIRMATION_LEVEL,
                    "encoding": "json",
                    "maxSupportedTransactionVersion": 1,
                },
            ],
        )
        if result is None:
            return None
        slot = result.get("slot") if isinstance(result, dict) else None
        if not isinstance(slot, int):
            raise ValueError(f"getTransaction returned no slot {self._log_ctx()}")

        meta = result.get("meta") or {}
        if meta.get("err") is not None:
            logging.error(
                f"{LOG_TAG} on-chain revert sig={signature} "
                f"slot={slot} err={meta['err']!r} {self._log_ctx()}"
            )
            raise ValueError(f"on-chain revert at slot {slot}: {meta['err']!r}")

        return slot

    async def _wait_for_confirmation(
        self, session: aiohttp.ClientSession, signature: str, timeout: int
    ) -> int:
        """Poll getTransaction until the tx confirms or the timeout elapses."""
        end_time: float = time.monotonic() + timeout
        polls = 0
        while time.monotonic() < end_time:
            polls += 1
            confirmation_slot: int | None = await self._check_status(session, signature)
            if confirmation_slot is not None:
                return confirmation_slot
            await asyncio.sleep(self.POLL_INTERVAL)

        logging.warning(
            f"{LOG_TAG} confirmation timeout sig={signature} polls={polls} "
            f"timeout={timeout}s {self._log_ctx()}"
        )
        raise ValueError(f"confirmation timeout after {timeout}s sig={signature}")

    async def _prepare_memo_transaction(
        self, session: aiohttp.ClientSession
    ) -> VersionedTransaction:
        memo_text: str = generate_memo(
            self.labels.require_label(MetricLabelKey.SOURCE_REGION),
            self.labels.require_label(MetricLabelKey.PROVIDER),
        )
        memo_ix = Instruction(
            program_id=Pubkey.from_string(self.MEMO_PROGRAM_ID),
            accounts=[],
            data=memo_text.encode(),
        )

        result = await self._rpc(
            session, "getLatestBlockhash", [{"commitment": "finalized"}]
        )
        value = result.get("value") if isinstance(result, dict) else None
        if not isinstance(value, dict) or not value.get("blockhash"):
            raise ValueError(f"getLatestBlockhash returned empty {self._log_ctx()}")

        message = MessageV1.try_compile(
            self.keypair.pubkey(),
            [memo_ix],
            Hash.from_string(value["blockhash"]),
            transaction_config(),
        )
        return VersionedTransaction(message, [self.keypair])

    async def _submit(
        self, session: aiohttp.ClientSession, tx: VersionedTransaction
    ) -> str:
        """Send the transaction; log RPC errors with context before re-raising.

        Rate-limit responses (HTTP 401/403/404/429) are logged at WARNING
        instead of ERROR — an endpoint throttling us is expected intermittent
        noise, not a regression. The exception still propagates so the metric
        framework treats it as a send failure (which it is — we couldn't land
        via this path this scrape).
        """
        try:
            signature = await self._rpc(
                session,
                "sendTransaction",
                [
                    base64.b64encode(bytes(tx)).decode(),
                    {
                        "encoding": "base64",
                        "skipPreflight": True,
                        "preflightCommitment": "finalized",
                        "maxRetries": 0,
                    },
                ],
            )
        except aiohttp.ClientResponseError as e:
            if e.status in MetricsServiceConfig.IGNORED_HTTP_ERRORS:
                logging.warning(
                    f"{LOG_TAG} sendTransaction rate-limited {self._log_ctx()}: "
                    f"HTTP {e.status}"
                )
            else:
                logging.error(
                    f"{LOG_TAG} sendTransaction failed {self._log_ctx()}: {e!r}"
                )
            raise
        except Exception as e:
            logging.error(f"{LOG_TAG} sendTransaction failed {self._log_ctx()}: {e!r}")
            raise
        if not isinstance(signature, str) or not signature:
            raise ValueError(
                f"sendTransaction returned empty response {self._log_ctx()}"
            )
        return signature

    async def fetch_data(self) -> float | None:
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

        async with aiohttp.ClientSession() as session:
            await self._capture_signer_balance(session)
            tx: VersionedTransaction = await self._prepare_memo_transaction(session)

            start_slot: int = await self._get_slot(session)
            start_time: float = time.monotonic()

            signature: str = await self._submit(session, tx)
            logging.info(
                f"{LOG_TAG} submitted sig={signature} start_slot={start_slot} "
                f"{self._log_ctx()}"
            )

            confirmation_slot: int = await self._wait_for_confirmation(
                session, signature, self.config.timeout
            )

            # `response_time` is not representative,
            # we don't use it in the visualizations
            response_time: float = time.monotonic() - start_time
            self._slot_diff = confirmation_slot - start_slot
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

    def process_data(self, value: float) -> float:
        """Return the raw latency value unchanged."""
        return value
