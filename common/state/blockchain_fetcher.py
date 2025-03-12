"""Fetches latest block and transaction data from blockchain RPC nodes."""

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any, Optional, Union

import aiohttp

from config.defaults import MetricsServiceConfig


@dataclass
class BlockchainData:
    """Container for blockchain state data."""

    block_id: str
    transaction_id: str
    old_block_id: str = ""

    @classmethod
    def empty(cls) -> "BlockchainData":
        return cls(block_id="", transaction_id="", old_block_id="")


class BlockchainDataFetcher:
    """Fetches blockchain data from RPC nodes using JSON-RPC protocol."""

    def __init__(self, http_endpoint: str) -> None:
        self.http_endpoint: str = http_endpoint
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        self._timeout = aiohttp.ClientTimeout(total=15)
        self._max_retries = 3
        self._retry_delay = 5

        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self._logger: logging.Logger = logging.getLogger(__name__)

    async def _make_rpc_request(
        self, method: str, params: Optional[Union[list, dict]] = None
    ) -> Any:
        """Makes a JSON-RPC request with retries."""
        request = {"jsonrpc": "2.0", "method": method, "params": params or [], "id": 1}

        for attempt in range(1, self._max_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=self._timeout) as session:
                    async with session.post(
                        self.http_endpoint, headers=self._headers, json=request
                    ) as response:
                        data = await response.json()

                        if "error" in data:
                            error = data["error"]
                            if error.get("code") == -32004:
                                raise ValueError(f"Block not available: {error}")
                            if attempt < self._max_retries:
                                self._logger.warning(
                                    f"Attempt {attempt} failed: {error}"
                                )
                                await asyncio.sleep(self._retry_delay)
                                continue
                            raise ValueError(f"RPC error after all retries: {error}")

                        return data.get("result")

            except Exception as e:
                if "Block not available" in str(e):
                    raise
                if attempt < self._max_retries:
                    self._logger.warning(f"Attempt {attempt} failed: {e}")
                    await asyncio.sleep(self._retry_delay)
                    continue
                raise

    async def _get_block_in_range(
        self, slot_start: int, slot_end: int
    ) -> tuple[Optional[int], Optional[dict]]:
        """Search for available block in given slot range."""
        current_slot = slot_end
        while current_slot >= slot_start:
            try:
                block = await self._make_rpc_request(
                    "getBlock",
                    [
                        current_slot,
                        {
                            "encoding": "json",
                            "maxSupportedTransactionVersion": 0,
                            "transactionDetails": "signatures",
                            "rewards": False,
                        },
                    ],
                )
                if block:
                    return current_slot, block
                current_slot -= 1

            except ValueError as e:
                if "Block not available" in str(e):
                    current_slot -= 1
                    continue
                raise

        return None, None

    async def _fetch_evm_data(self, blockchain: str) -> BlockchainData:
        """Fetches latest block data from EVM-compatible chains."""
        try:
            latest_block = await self._make_rpc_request(
                "eth_getBlockByNumber", ["latest", False]
            )
            if not isinstance(latest_block, dict):
                return BlockchainData.empty()

            latest_number = int(latest_block["number"], 16)
            offset_range = MetricsServiceConfig.BLOCK_OFFSET_RANGES.get(
                blockchain.lower(), (20, 100)
            )
            offset = random.randint(offset_range[0], offset_range[1])
            old_number = max(0, latest_number - offset)

            transactions = latest_block.get("transactions", [])
            tx_hash = (
                transactions[0].get("hash", "")
                if isinstance(transactions[0], dict)
                else transactions[0] if transactions else ""
            )

            return BlockchainData(
                block_id=latest_block["number"],
                transaction_id=tx_hash,
                old_block_id=hex(old_number),
            )

        except Exception as e:
            self._logger.error(f"EVM fetch failed: {e!s}")
            return BlockchainData.empty()

    async def _fetch_solana_data(self) -> BlockchainData:
        """Fetches latest block data from Solana."""
        try:
            block_info = await self._make_rpc_request(
                "getLatestBlockhash", [{"commitment": "finalized"}]
            )
            if not isinstance(block_info, dict):
                return BlockchainData.empty()

            latest_slot = block_info.get("context", {}).get("slot")
            if not latest_slot:
                return BlockchainData.empty()

            actual_latest_slot, latest_block = await self._get_block_in_range(
                latest_slot - 10, latest_slot
            )
            if not actual_latest_slot or not latest_block:
                return BlockchainData.empty()

            tx_sig = latest_block.get("signatures", [""])[0]

            offset_range = MetricsServiceConfig.BLOCK_OFFSET_RANGES.get(
                "solana", (100, 1000)
            )
            offset = random.randint(offset_range[0], offset_range[1])
            target_slot = max(0, actual_latest_slot - offset)
            old_slot, _ = await self._get_block_in_range(target_slot - 10, target_slot)

            return BlockchainData(
                block_id=str(actual_latest_slot),
                transaction_id=tx_sig,
                old_block_id=str(old_slot or target_slot),
            )

        except Exception as e:
            self._logger.error(f"Solana fetch failed: {e!s}")
            return BlockchainData.empty()

    async def _fetch_ton_data(self) -> BlockchainData:
        """Fetches latest block data from TON."""
        try:
            info = await self._make_rpc_request("getMasterchainInfo")
            if not isinstance(info, dict) or "last" not in info:
                return BlockchainData.empty()

            last_block = info["last"]
            if not isinstance(last_block, dict):
                return BlockchainData.empty()

            offset_range = MetricsServiceConfig.BLOCK_OFFSET_RANGES.get("ton", (10, 50))
            offset = random.randint(offset_range[0], offset_range[1])
            old_seqno = max(0, last_block["seqno"] - offset)

            latest_block_id = (
                f"{last_block['workchain']}:{last_block['shard']}:{last_block['seqno']}"
            )
            old_block_id = (
                f"{last_block['workchain']}:{last_block['shard']}:{old_seqno}"
            )

            block = await self._make_rpc_request(
                "getBlockTransactions",
                {
                    "workchain": last_block["workchain"],
                    "shard": last_block["shard"],
                    "seqno": last_block["seqno"],
                    "count": 1,
                },
            )

            tx_id = (
                block.get("transactions", [{}])[0].get("hash", "")
                if isinstance(block, dict)
                else ""
            )

            return BlockchainData(
                block_id=latest_block_id,
                transaction_id=tx_id,
                old_block_id=old_block_id,
            )

        except Exception as e:
            self._logger.error(f"TON fetch failed: {e!s}")
            return BlockchainData.empty()

    async def fetch_latest_data(self, blockchain: str) -> BlockchainData:
        """Fetches latest block and transaction data for specified blockchain."""
        try:
            if blockchain.lower() in ("ethereum", "base"):
                return await self._fetch_evm_data(blockchain)
            elif blockchain.lower() == "solana":
                return await self._fetch_solana_data()
            elif blockchain.lower() == "ton":
                return await self._fetch_ton_data()
            raise ValueError(f"Unsupported blockchain: {blockchain}")

        except Exception as e:
            self._logger.error(f"Failed to fetch {blockchain} data: {e}")
            return BlockchainData.empty()
