"""Blob storage handler for managing blobs in Vercel Blob Storage."""

import json
import time
from dataclasses import dataclass
from typing import Optional

import aiohttp

from config.defaults import BlobStorageConfig


@dataclass
class BlobConfig:
    store_id: str
    token: str
    base_url: str = BlobStorageConfig.BLOB_BASE_URL
    retry_attempts: int = BlobStorageConfig.RETRY_ATTEMPTS
    retry_delay: int = BlobStorageConfig.RETRY_DELAY
    filename: str = BlobStorageConfig.BLOB_FILENAME
    folder: str = BlobStorageConfig.BLOB_FOLDER


class BlobStorageHandler:
    def __init__(self, config: BlobConfig) -> None:
        self.config: BlobConfig = config
        self._headers: dict[str, str] = {
            "Authorization": f"Bearer {config.token}",
            "Content-Type": "application/json",
            "x-store-id": config.store_id,
            "x-add-random-suffix": "false",
            "x-access": "private",
            "x-cache-control-max-age": "0",
            "x-mime-type": "application/json",
        }

    async def _make_request(
        self, method: str, url: str, data: Optional[dict] = None
    ) -> dict:
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

    async def list_files(self) -> list[dict[str, str]]:
        list_url: str = f"{self.config.base_url}?prefix={self.config.folder}/"
        response = await self._make_request("GET", list_url)
        return response.get("blobs", [])

    async def delete_blobs(self, urls: list[str]) -> None:
        if not urls:
            return
        delete_url = f"{self.config.base_url}/delete"
        await self._make_request("POST", delete_url, {"urls": urls})

    async def delete_all_files(self) -> None:
        files: list[dict[str, str]] = await self.list_files()
        if files:
            urls: list[str] = [file["url"] for file in files]
            await self.delete_blobs(urls)

    async def update_data(self, blockchain_data: dict[str, dict[str, str]]) -> None:
        await self.delete_all_files()
        data = {**blockchain_data, "updated_at": int(time.time())}
        blob_url: str = (
            f"{self.config.base_url}/{self.config.folder}/{self.config.filename}"
        )
        await self._make_request("PUT", blob_url, data)
