"""Blockchain data fetching utilities."""

import logging
from typing import Dict, Optional, Tuple

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
    ) -> Dict:
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
        try:
            if blockchain in ("ethereum", "base"):
                return await self._fetch_ethereum_like()
            elif blockchain == "solana":
                return await self._fetch_solana()
            elif blockchain == "ton":
                return await self._fetch_ton()
            raise ValueError(f"Unsupported blockchain: {blockchain}")
        except Exception as e:
            logging.error(f"Failed to fetch {blockchain} data: {e}")
            raise

    async def _fetch_ethereum_like(self) -> Tuple[str, str]:
        block = await self._make_rpc_request("eth_getBlockByNumber", ["latest", True])
        tx_hash = block["transactions"][0]["hash"] if block["transactions"] else None
        return block["hash"], tx_hash  # type: ignore

    async def _fetch_solana(self) -> Tuple[str, str]:
        slot = await self._make_rpc_request("getSlot", [{"commitment": "finalized"}])
        block = await self._make_rpc_request(
            "getBlock",
            [slot, {"maxSupportedTransactionVersion": 0, "encoding": "json"}],
        )
        tx_sig = (
            block["transactions"][0]["transaction"]["signatures"][0]
            if block["transactions"]
            else None
        )
        return str(slot), tx_sig  # type: ignore

    async def _fetch_ton(self) -> Tuple[str, str]:
        info = await self._make_rpc_request("getMasterchainInfo")
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
        tx_id = txs["transactions"][0]["hash"] if txs["transactions"] else None
        return block_id, tx_id  # type: ignore
