"""Fetches latest block and transaction data from blockchain RPC nodes."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import aiohttp


@dataclass
class BlockchainData:
    """Container for blockchain state data."""

    block_id: str
    transaction_id: str


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

    async def _fetch_evm_data(self) -> BlockchainData:
        try:
            block = await self._make_rpc_request(
                "eth_getBlockByNumber", ["latest", True]
            )
            if not isinstance(block, dict):
                self._logger.error(f"Invalid block format: {type(block)}")
                return BlockchainData(block_id="", transaction_id="")

            block_hash = block.get("hash", "")
            tx_hash = ""

            transactions = block.get("transactions", [])
            if transactions and isinstance(transactions[0], (dict, str)):
                tx_hash = (
                    transactions[0].get("hash", "")
                    if isinstance(transactions[0], dict)
                    else transactions[0]
                )

            # self._logger.info(f"{block_hash} {tx_hash}")
            return BlockchainData(block_id=block_hash, transaction_id=tx_hash)

        except Exception as e:
            self._logger.error(f"EVM fetch failed: {e!s}")
            return BlockchainData(block_id="", transaction_id="")

    async def _fetch_solana_data(self) -> BlockchainData:
        try:
            block_info = await self._make_rpc_request(
                "getLatestBlockhash", [{"commitment": "finalized"}]
            )
            if not isinstance(block_info, dict):
                return BlockchainData(block_id="", transaction_id="")

            block_slot = block_info.get("context", {}).get("slot", "")
            if not block_slot:
                return BlockchainData(block_id="", transaction_id="")

            block = await self._make_rpc_request(
                "getBlock",
                [
                    block_slot,
                    {
                        "encoding": "json",
                        "maxSupportedTransactionVersion": 0,
                        "transactionDetails": "signatures",
                        "rewards": False,
                    },
                ],
            )

            tx_sig = ""
            if isinstance(block, dict):
                signatures = block.get("signatures", [])
                if signatures:
                    tx_sig = signatures[0]

            # self._logger.info(f"{block_slot} {tx_sig}")
            return BlockchainData(block_id=str(block_slot), transaction_id=tx_sig)

        except Exception as e:
            self._logger.error(f"Solana fetch failed: {e!s}")
            return BlockchainData(block_id="", transaction_id="")

    async def _fetch_ton_data(self) -> BlockchainData:
        try:
            info = await self._make_rpc_request("getMasterchainInfo")
            if not isinstance(info, dict) or "last" not in info:
                raise ValueError("Invalid masterchain info")

            last_block = info["last"]
            if not isinstance(last_block, dict):
                raise ValueError("Invalid last block format")

            block_id = (
                f"{last_block['workchain']}:{last_block['shard']}:{last_block['seqno']}"
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

            # self._logger.info(f"{block_id} {tx_id}")
            return BlockchainData(block_id=block_id, transaction_id=tx_id)

        except Exception as e:
            self._logger.error(f"TON fetch failed: {e!s}")
            return BlockchainData(block_id="", transaction_id="")

    async def fetch_latest_data(self, blockchain: str) -> BlockchainData:
        try:
            if blockchain in ("ethereum", "base"):
                return await self._fetch_evm_data()
            elif blockchain == "solana":
                return await self._fetch_solana_data()
            elif blockchain == "ton":
                return await self._fetch_ton_data()
            raise ValueError(f"Unsupported blockchain: {blockchain}")

        except Exception as e:
            self._logger.error(f"Failed to fetch {blockchain} data: {e}")
            return BlockchainData(block_id="", transaction_id="")
