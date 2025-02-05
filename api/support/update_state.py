"""Vercel serverless function for updating blockchain state in specific regions."""

import asyncio
import json
import logging
import os
from http.server import BaseHTTPRequestHandler
from typing import Dict, Set

from common.state.blob_storage import BlobConfig, BlobStorageHandler
from common.state.blockchain_fetcher import BlockchainDataFetcher

ALLOWED_REGIONS: Set[str] = {"fra1"}


class handler(BaseHTTPRequestHandler):
    async def _get_first_providers(self) -> Dict[str, Dict]:
        endpoints = json.loads(os.getenv("ENDPOINTS", "{}"))
        providers = endpoints.get("providers", [])

        first_providers: Dict[str, Dict] = {}
        for provider in providers:
            blockchain = provider["blockchain"].lower()
            if blockchain not in first_providers:
                first_providers[blockchain] = provider

        if not first_providers:
            raise ValueError("No valid providers found")

        return first_providers

    async def update_state(self) -> None:
        current_region = os.getenv("VERCEL_REGION")
        if current_region not in ALLOWED_REGIONS:
            logging.info(f"Skipping execution in region {current_region}")
            return

        config = BlobConfig(
            store_id=os.getenv("STORE_ID", ""),
            token=os.getenv("VERCEL_BLOB_TOKEN", ""),
        )

        if not all([config.store_id, config.token]):
            raise ValueError("Missing required blob storage configuration")

        blob_handler = BlobStorageHandler(config)
        await blob_handler.initialize()

        first_providers = await self._get_first_providers()
        fetch_tasks = []

        for blockchain, provider in first_providers.items():
            fetcher = BlockchainDataFetcher(provider["http_endpoint"])
            task = asyncio.create_task(fetcher.fetch_latest_data(blockchain))
            fetch_tasks.append((blockchain, task))

        for blockchain, task in fetch_tasks:
            try:
                block, tx = await task
                await blob_handler.update(blockchain, block, tx)
            except Exception as e:
                logging.error(f"Failed to process {blockchain}: {e}")
                continue

    def validate_token(self):
        auth_token = self.headers.get("Authorization")
        expected_token = os.environ.get("CRON_SECRET")
        return auth_token == f"Bearer {expected_token}"

    def do_GET(self):
        skip_auth = os.environ.get("SKIP_AUTH", "false").lower() == "true"
        if not skip_auth and not self.validate_token():
            self.send_response(401)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self.update_state())
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"State updated successfully")
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))
        finally:
            loop.close()
