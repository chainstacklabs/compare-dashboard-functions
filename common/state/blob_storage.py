"""Vercel Blob storage handler for blockchain data."""

import json
import time
from dataclasses import dataclass
from typing import Dict, Optional

import aiohttp

from config.defaults import BlobStorageConfig


@dataclass
class BlobConfig:
    """Configuration for Vercel Blob storage."""

    store_id: str
    token: str
    base_url: str = BlobStorageConfig.BLOB_BASE_URL
    blob_filename: str = BlobStorageConfig.BLOB_FILENAME
    retry_attempts: int = BlobStorageConfig.RETRY_ATTEMPTS
    retry_delay: int = BlobStorageConfig.RETRY_DELAY


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
            "PUT", f"{self.config.base_url}/{self.config.blob_filename}", initial_data
        )
        self._blob_url = result.get("url")

    async def update_all(self, blockchain_data: Dict[str, Dict[str, str]]) -> None:
        """Updates data for all blockchains in a single operation."""
        if not self._blob_url:
            await self.initialize()

        try:
            current_data = await self._make_request("GET", self._blob_url)  # type: ignore
            current_data.update(blockchain_data)
            current_data["updated_at"] = int(time.time())
            await self._make_request("PUT", self._blob_url, current_data)  # type: ignore
        except Exception as e:
            raise Exception(f"Bulk update failed: {e}")
