"""Vercel Blob storage handler for blockchain data."""

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Dict, Optional

import aiohttp


@dataclass
class BlobConfig:
    """Configuration for Vercel Blob storage."""

    store_id: str
    token: str
    base_url: str = "https://blob.vercel-storage.com"
    retry_attempts: int = 3
    retry_delay: int = 1


class BlobStorageHandler:
    """Manages blockchain data storage in Vercel Blob."""

    def __init__(self, config: BlobConfig):
        self.config = config
        self._blob_url: Optional[str] = None
        self._headers = {
            "Authorization": f"Bearer {config.token}",
            "x-content-type": "application/json",
            "x-access": "public",
            "x-store-id": config.store_id,
            "x-add-random-suffix": "0",
        }

    async def _make_request(
        self, method: str, url: str, data: Optional[Dict] = None
    ) -> Dict:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                url,
                headers=self._headers,
                data=json.dumps(data) if data else None,
            ) as resp:
                if resp.status not in (200, 201):
                    text = await resp.text()
                    raise Exception(f"Blob operation failed: {resp.status} - {text}")
                return await resp.json()

    async def initialize(self) -> None:
        initial_data = {
            "ethereum": {"block": None, "tx": None},
            "solana": {"block": None, "tx": None},
            "ton": {"block": None, "tx": None},
            "base": {"block": None, "tx": None},
            "created_at": int(time.time()),
        }
        result = await self._make_request(
            "PUT", f"{self.config.base_url}/blockchain-data.json", initial_data
        )
        self._blob_url = result.get("url")

    async def update(self, blockchain: str, block: str, tx: str) -> None:
        if not self._blob_url:
            await self.initialize()

        for attempt in range(self.config.retry_attempts):
            try:
                current_data = await self._make_request("GET", self._blob_url)  # type: ignore
                current_data[blockchain] = {"block": block, "tx": tx}
                current_data["updated_at"] = int(time.time())
                await self._make_request("PUT", self._blob_url, current_data)  # type: ignore
                return
            except Exception as e:
                if attempt == self.config.retry_attempts - 1:
                    raise Exception(f"Update failed: {e}")
                await asyncio.sleep(self.config.retry_delay)
