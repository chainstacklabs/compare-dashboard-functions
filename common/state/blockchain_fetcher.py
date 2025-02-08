"""Blockchain data fetching utilities."""

import logging
from typing import Any, Dict, Optional, Tuple

import aiohttp


class BlockchainDataFetcher:
    """Fetches latest block and transaction data from nodes."""

    def __init__(self, http_endpoint: str):
        self.http_endpoint = http_endpoint
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _make_rpc_request(
        self, method: str, params: Optional[list] = None
    ) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.http_endpoint,
                headers=self._headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params or [],
                },
                timeout=30,  # type: ignore
            ) as response:
                if response.status != 200:
                    raise ValueError(f"RPC request failed: {response.status}")
                data = await response.json()
                if "error" in data:
                    raise ValueError(f"RPC error: {data['error']}")
                return data["result"]

    async def fetch_latest_data(self, blockchain: str) -> Tuple[str, str]:
        """Fetches latest block and transaction data for specified blockchain.

        Args:
            blockchain: Lowercase blockchain identifier (ethereum, base, solana, ton)

        Returns:
            Tuple of (block_identifier, transaction_identifier)

        Raises:
            ValueError: If blockchain is unsupported or data fetch fails
        """
        try:
            if blockchain in ("ethereum", "base"):
                return await self._fetch_evm_data()
            elif blockchain == "solana":
                return await self._fetch_solana_data()
            elif blockchain == "ton":
                return await self._fetch_ton_data()
            raise ValueError(f"Unsupported blockchain: {blockchain}")
        except Exception as e:
            logging.error(f"Failed to fetch {blockchain} data: {e!s}")
            raise

    async def _fetch_evm_data(self) -> Tuple[str, str]:
        """Fetches latest block and first transaction hash for EVM chains."""
        block = await self._make_rpc_request("eth_getBlockByNumber", ["latest", True])
        if not block:
            raise ValueError("Empty block data received")

        tx_hash = block["transactions"][0]["hash"] if block["transactions"] else ""
        return block["hash"], tx_hash

    async def _fetch_solana_data(self) -> Tuple[str, str]:
        """Fetches latest slot and first transaction signature for Solana."""
        slot = await self._make_rpc_request("getSlot", [{"commitment": "finalized"}])
        if slot is None:
            raise ValueError("Failed to fetch latest slot")

        block = await self._make_rpc_request(
            "getBlock",
            [slot, {"maxSupportedTransactionVersion": 0, "encoding": "json"}],
        )
        if not block:
            raise ValueError("Empty block data received")

        tx_sig = (
            block["transactions"][0]["transaction"]["signatures"][0]
            if block["transactions"]
            else ""
        )
        return str(slot), tx_sig

    async def _fetch_ton_data(self) -> Tuple[str, str]:
        """Fetches latest block and first transaction hash for TON."""
        info = await self._make_rpc_request("getMasterchainInfo")
        if not info or "last" not in info:
            raise ValueError("Invalid masterchain info received")

        block_id = f"{info['last']['workchain']}:{info['last']['shard']}:{info['last']['seqno']}"

        txs = await self._make_rpc_request(
            "getBlockTransactions",
            [
                {
                    "workchain": info["last"]["workchain"],
                    "shard": info["last"]["shard"],
                    "seqno": info["last"]["seqno"],
                    "count": 1,
                }
            ],
        )

        tx_id = txs["transactions"][0]["hash"] if txs.get("transactions") else ""
        return block_id, tx_id
