"""Manages blockchain state data by fetching and processing data from blob storage."""

import asyncio
import logging
import os

import aiohttp

from config.defaults import BlobStorageConfig


class BlockchainState:
    """Manages blockchain state data retrieval from blob storage."""

    _TIMEOUT = aiohttp.ClientTimeout(total=10)
    _RETRIES = 3
    _RETRY_DELAY = 3

    @staticmethod
    def _get_headers() -> dict[str, str]:
        """Get the authorization headers for blob storage requests."""
        return {
            "Authorization": f"Bearer {os.getenv('VERCEL_BLOB_TOKEN')}",
            "x-store-id": os.getenv("STORE_ID"),  # type: ignore
        }

    @staticmethod
    async def _get_blob_url(session: aiohttp.ClientSession) -> str:
        """Get URL of the latest blockchain data blob."""
        list_url = (
            f"{BlobStorageConfig.BLOB_BASE_URL}?prefix={BlobStorageConfig.BLOB_FOLDER}/"
        )
        headers: dict[str, str] = BlockchainState._get_headers()

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
    async def _fetch_state_data(session: aiohttp.ClientSession, blob_url: str) -> dict:
        """Fetch state data from blob storage."""
        headers: dict[str, str] = BlockchainState._get_headers()

        async with session.get(blob_url, headers=headers) as response:
            if response.status != 200:
                raise ValueError(f"Failed to fetch state: {response.status}")
            data = await response.json()

            # Ensure backward compatibility for old state data
            for chain in data:
                if isinstance(data[chain], dict) and "old_block" not in data[chain]:
                    data[chain]["old_block"] = ""

            return data

    @staticmethod
    async def get_data(blockchain: str) -> dict:
        """Get blockchain state data with retries."""
        last_exception = None  # type: ignore

        for attempt in range(1, BlockchainState._RETRIES + 1):
            try:
                async with aiohttp.ClientSession(
                    timeout=BlockchainState._TIMEOUT
                ) as session:
                    blob_url: str = await BlockchainState._get_blob_url(session)
                    state_data = await BlockchainState._fetch_state_data(
                        session, blob_url
                    )
                    return state_data.get(blockchain.lower(), {})
            except Exception as e:
                last_exception: str = str(e) if str(e) else "Unknown error occurred"
                logging.warning(
                    f"Attempt {attempt}: State fetch failed: {last_exception}"
                )
                if attempt < BlockchainState._RETRIES:
                    await asyncio.sleep(BlockchainState._RETRY_DELAY)

        error_msg = (
            f"Max retries reached for fetching state data. Last error: {last_exception}"
        )
        raise ValueError(error_msg)

    @staticmethod
    def clear_cache() -> None:
        """Maintained for API compatibility."""
        pass
