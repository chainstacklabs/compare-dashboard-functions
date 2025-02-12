import asyncio
import logging
import os
from typing import Dict

import aiohttp

from config.defaults import BlobStorageConfig


class BlockchainState:
    """Manages blockchain state data retrieval from blob storage."""

    _TIMEOUT = aiohttp.ClientTimeout(total=10)
    _RETRIES = 3
    _RETRY_DELAY = 2

    @staticmethod
    async def _get_blob_url(session: aiohttp.ClientSession) -> str:
        """Get URL of the latest blockchain data blob."""
        list_url = (
            f"{BlobStorageConfig.BLOB_BASE_URL}?prefix={BlobStorageConfig.BLOB_FOLDER}/"
        )
        headers = {
            "Authorization": f"Bearer {os.getenv('VERCEL_BLOB_TOKEN')}",
            "x-store-id": os.getenv("STORE_ID"),
        }

        async with session.get(list_url, headers=headers) as response:
            if response.status != 200:
                raise ValueError(f"Failed to list blobs: {response.status}")

            data = await response.json()
            blobs = data.get("blobs", [])

            for blob in blobs:
                if blob["pathname"].endswith(BlobStorageConfig.BLOB_FILENAME):
                    return blob["url"]

            raise ValueError("Blockchain data blob not found")

    @staticmethod
    async def _fetch_state_data(session: aiohttp.ClientSession, blob_url: str) -> Dict:
        """Fetch state data from blob storage."""
        async with session.get(blob_url) as response:
            if response.status != 200:
                raise ValueError(f"Failed to fetch state: {response.status}")
            return await response.json()

    @staticmethod
    async def get_data(blockchain: str) -> dict:
        """Get blockchain state data with retries."""
        for attempt in range(1, BlockchainState._RETRIES + 1):
            try:
                async with aiohttp.ClientSession(
                    timeout=BlockchainState._TIMEOUT
                ) as session:
                    blob_url = await BlockchainState._get_blob_url(session)
                    state_data = await BlockchainState._fetch_state_data(
                        session, blob_url
                    )
                    return state_data.get(blockchain.lower(), {})
            except Exception as e:
                logging.error(f"Attempt {attempt}: State fetch failed: {e}")
                if attempt < BlockchainState._RETRIES:
                    await asyncio.sleep(BlockchainState._RETRY_DELAY)

        raise ValueError("Max retries reached for fetching state data")

    @staticmethod
    def clear_cache() -> None:
        """Maintained for API compatibility."""
        pass
