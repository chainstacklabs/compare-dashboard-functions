"""Fetches latest block and transaction data from blockchain RPC nodes."""

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import aiohttp

from config.defaults import MetricsServiceConfig


@dataclass
class BlockchainData:
    """Container for blockchain state data."""

    block_id: str
    transaction_id: str
    old_block_id: str = ""


class BlockchainDataFetcher:
    """Fetches blockchain data from RPC nodes using JSON-RPC protocol."""

    def __init__(self, http_endpoint: str) -> None:
        self.http_endpoint = http_endpoint
        self._headers = {"Content-Type": "application/json"}
        self._timeout = aiohttp.ClientTimeout(total=15)
        self._max_retries = 3
        self._retry_delay = 5

        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self._logger = logging.getLogger(__name__)

    async def _make_rpc_request(
        self, method: str, params: Optional[Union[List, Dict]] = None
    ) -> Any:
        request = {"jsonrpc": "2.0", "method": method, "params": params or [], "id": 1}

        for attempt in range(1, self._max_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=self._timeout) as session:
                    async with session.post(
                        self.http_endpoint, headers=self._headers, json=request
                    ) as response:
                        data = await response.json()
                        if "error" in data:
                            raise Exception(f"RPC error: {data['error']}")
                        return data.get("result")
            except Exception as e:
                self._logger.warning(f"Attempt {attempt} failed: {e}")
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_delay)
                else:
                    self._logger.error(f"All {self._max_retries} attempts failed")
                    raise

    async def _fetch_evm_data(self, blockchain: str) -> BlockchainData:
        try:
            latest_block = await self._make_rpc_request(
                "eth_getBlockByNumber", ["latest", True]
            )

            latest_number = int(latest_block["number"], 16)
            offset_range = MetricsServiceConfig.BLOCK_OFFSET_RANGES.get(
                blockchain.lower(), (20, 100)
            )
            offset = random.randint(offset_range[0], offset_range[1])
            old_number = max(0, latest_number - offset)

            if not isinstance(latest_block, dict):
                return BlockchainData(block_id="", transaction_id="", old_block_id="")

            tx_hash = ""

            transactions = latest_block.get("transactions", [])
            if transactions and isinstance(transactions[0], (dict, str)):
                tx_hash = (
                    transactions[0].get("hash", "")
                    if isinstance(transactions[0], dict)
                    else transactions[0]
                )

            return BlockchainData(
                block_id=latest_block["number"],
                transaction_id=tx_hash,
                old_block_id=hex(old_number),
            )

        except Exception as e:
            self._logger.error(f"EVM fetch failed: {e!s}")
            return BlockchainData(block_id="", transaction_id="", old_block_id="")

    async def _fetch_solana_data(self) -> BlockchainData:
        try:
            block_info = await self._make_rpc_request(
                "getLatestBlockhash", [{"commitment": "finalized"}]
            )
            if not isinstance(block_info, dict):
                return BlockchainData(block_id="", transaction_id="", old_block_id="")

            latest_slot = block_info.get("context", {}).get("slot", "")
            if not latest_slot:
                return BlockchainData(block_id="", transaction_id="", old_block_id="")

            latest_block = await self._make_rpc_request(
                "getBlock",
                [
                    latest_slot,
                    {
                        "encoding": "json",
                        "maxSupportedTransactionVersion": 0,
                        "transactionDetails": "signatures",
                        "rewards": False,
                    },
                ],
            )

            tx_sig = ""
            if isinstance(latest_block, dict):
                signatures = latest_block.get("signatures", [])
                if signatures:
                    tx_sig = signatures[0]

            offset_range = MetricsServiceConfig.BLOCK_OFFSET_RANGES.get(
                "solana", (100, 1000)
            )
            offset = random.randint(offset_range[0], offset_range[1])
            target_slot = max(0, latest_slot - offset)
            old_slot = None

            for slot in range(target_slot - 100, target_slot):
                try:
                    block_exists = await self._make_rpc_request(
                        "getBlock",
                        [
                            slot,
                            {
                                "encoding": "json",
                                "maxSupportedTransactionVersion": 0,
                                "transactionDetails": "none",
                                "rewards": False,
                            },
                        ],
                    )
                    if block_exists:
                        old_slot = slot
                        break
                except Exception as e:
                    if "Block not available" not in str(e):
                        self._logger.warning(f"Error checking slot {slot}: {e}")
                    continue

            return BlockchainData(
                block_id=str(latest_slot),
                transaction_id=tx_sig,
                old_block_id=str(old_slot) if old_slot is not None else "",
            )

        except Exception as e:
            self._logger.error(f"Solana fetch failed: {e!s}")
            return BlockchainData(block_id="", transaction_id="", old_block_id="")

    async def _fetch_ton_data(self) -> BlockchainData:
        try:
            info = await self._make_rpc_request("getMasterchainInfo")
            if not isinstance(info, dict) or "last" not in info:
                raise ValueError("Invalid masterchain info")

            last_block = info["last"]
            if not isinstance(last_block, dict):
                raise ValueError("Invalid last block format")

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

            tx_id = ""
            if isinstance(block, dict) and block.get("transactions"):
                tx_id = block["transactions"][0].get("hash", "")

            return BlockchainData(
                block_id=latest_block_id,
                transaction_id=tx_id,
                old_block_id=old_block_id,
            )

        except Exception as e:
            self._logger.error(f"TON fetch failed: {e!s}")
            return BlockchainData(block_id="", transaction_id="", old_block_id="")

    async def fetch_latest_data(self, blockchain: str) -> BlockchainData:
        try:
            if blockchain in ("ethereum", "base"):
                return await self._fetch_evm_data(blockchain)
            elif blockchain == "solana":
                return await self._fetch_solana_data()
            elif blockchain == "ton":
                return await self._fetch_ton_data()
            raise ValueError(f"Unsupported blockchain: {blockchain}")

        except Exception as e:
            self._logger.error(f"Failed to fetch {blockchain} data: {e}")
            return BlockchainData(block_id="", transaction_id="")
