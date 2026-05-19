"""P2P Syncro Sender landing rate metric.

Reuses the memo-probe flow from ``SolanaLandingMetric`` but routes
``sendTransaction`` to the public Syncro Sender endpoint while keeping
reads on a normal Solana RPC. Adds the mandatory tip transfer (>=100k
lamports) to a Syncro tip account so the public endpoint accepts the tx.

Public endpoint is rate-limited to 1 RPS — do not increase send cadence.
"""

import random
import time
from typing import Optional

from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.instruction import Instruction
from solders.pubkey import Pubkey
from solders.rpc.responses import SendTransactionResp
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction

from common.metric_config import MetricLabelKey
from config.defaults import MetricsServiceConfig
from metrics.solana_landing_rate import SolanaLandingMetric, generate_fixed_memo


class P2PSyncroLandingMetric(SolanaLandingMetric):
    """Solana landing-rate probe through P2P.org Syncro Sender public endpoint."""

    SYNCRO_TX_ENDPOINT = "https://sfls-geo-fra.l2.p2p.org/public"
    TIP_LAMPORTS = 100_000
    TIP_ACCOUNTS: tuple[Pubkey, ...] = tuple(
        Pubkey.from_string(addr)
        for addr in (
            "BPZrtYhdoAhiHWV5EgGLoV7bZFbMamBZurGDq4DmST8v",
            "7D5pdbkV75Sr73M1YFNZwXMed6DenwkdfbJwVWrX6drQ",
            "ELpn2NryEW4B3psG36eSjF45YcGMQpGGuu9J2AgAccbV",
            "FnckAPC9PitnRpGZM2M4WLwb3w9odRLJ7EDRZDngjvd6",
            "3ZnDTgvVfwzqwWoqAUmDkgVtXvXqjmeb5t9zxD5pMbmv",
            "3SLDFcdCzMbcFNguZhzmV4zqEAUvcPoKY13akpE4Tq1p",
            "48tT6LJqrsoFrLpzZSHkjGdGTWtsJ1PvjgWZjh8qF1RK",
            "7GM9fpVMHHcrK4cgzfVdzJvjiy1bSyfwSYzhxvgbfVLg",
            "CBd8GE3ffMJKf3iCCcNNBEifMxH1WpgtTzRnXPxxbjGE",
        )
    )

    async def _prepare_memo_transaction(self, client: AsyncClient) -> Transaction:
        """Build the memo transaction with a Syncro tip transfer prepended."""
        memo_text: str = generate_fixed_memo(
            self.labels.get_label(MetricLabelKey.SOURCE_REGION)  # type: ignore[arg-type]
        )

        tip_ix = transfer(
            TransferParams(
                from_pubkey=self.keypair.pubkey(),
                to_pubkey=random.choice(self.TIP_ACCOUNTS),
                lamports=self.TIP_LAMPORTS,
            )
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

        blockhash = await client.get_latest_blockhash()
        if not blockhash or not blockhash.value:
            raise ValueError("Failed to get latest blockhash")

        return Transaction.new_signed_with_payer(
            [tip_ix, compute_limit_ix, compute_price_ix, memo_ix],
            self.keypair.pubkey(),
            [self.keypair],
            blockhash.value.blockhash,
        )

    async def fetch_data(self) -> Optional[float]:
        """Send a tipped memo tx via Syncro; read state via the inherited endpoint."""
        self.update_metric_value(0, "response_time")
        self.update_metric_value(0, "slot_latency")

        read_client: Optional[AsyncClient] = None
        tx_client: Optional[AsyncClient] = None
        try:
            read_client = await self._create_client()
            tx_client = AsyncClient(self.SYNCRO_TX_ENDPOINT)

            tx: Transaction = await self._prepare_memo_transaction(read_client)
            start_slot: int = await self._get_slot(read_client)
            start_time: float = time.monotonic()

            signature_response: SendTransactionResp = await tx_client.send_transaction(
                tx, TxOpts(skip_preflight=True, max_retries=0)
            )
            if not signature_response or not signature_response.value:
                raise ValueError("Failed to send transaction")

            confirmation_slot: int = await self._wait_for_confirmation(
                read_client,
                signature_response.value,  # type: ignore
                self.config.timeout,
            )

            response_time: float = time.monotonic() - start_time
            self._slot_diff = confirmation_slot - start_slot
            if self._slot_diff < 0:
                raise ValueError(
                    f"Negative slot difference: {self._slot_diff} "
                    f"(confirmation_slot={confirmation_slot}, start_slot={start_slot})"
                )
            self.update_metric_value(self._slot_diff, "slot_latency")
            return response_time

        finally:
            if read_client:
                await read_client.close()
            if tx_client:
                await tx_client.close()
