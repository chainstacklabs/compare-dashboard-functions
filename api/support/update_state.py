"""State update handler for blockchain data collection."""

import asyncio
import json
import logging
import os
from http.server import BaseHTTPRequestHandler
from typing import Dict, Tuple

from common.state.blob_storage import BlobConfig, BlobStorageHandler
from common.state.blockchain_fetcher import BlockchainData, BlockchainDataFetcher

SUPPORTED_BLOCKCHAINS = ["ethereum", "solana", "ton", "base"]
ALLOWED_REGIONS = {"fra1"}


class StateUpdateManager:
    def __init__(self):
        store_id = os.getenv("STORE_ID")
        token = os.getenv("VERCEL_BLOB_TOKEN")
        if not all([store_id, token]):
            raise ValueError("Missing required blob storage configuration")

        self.blob_config = BlobConfig(store_id=store_id, token=token)  # type: ignore

    async def _fetch_provider_endpoints(self) -> Dict[str, str]:
        endpoints = json.loads(os.getenv("ENDPOINTS", "{}"))
        return {
            p["blockchain"].lower(): p["http_endpoint"]
            for p in endpoints.get("providers", [])
            if p["blockchain"].lower() in SUPPORTED_BLOCKCHAINS
        }

    async def _collect_blockchain_data(
        self, providers: Dict[str, str]
    ) -> Dict[str, dict]:
        async def fetch_single(
            blockchain: str, endpoint: str
        ) -> Tuple[str, Dict[str, str]]:
            try:
                fetcher = BlockchainDataFetcher(endpoint)
                data: BlockchainData = await fetcher.fetch_latest_data(blockchain)
                return blockchain, {"block": data.block_id, "tx": data.transaction_id}
            except Exception as e:
                logging.error(f"Failed to fetch {blockchain} data: {e}")
                return blockchain, {"block": "", "tx": ""}

        tasks = [
            fetch_single(blockchain, endpoint)
            for blockchain, endpoint in providers.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            blockchain: data
            for blockchain, data in results  # type: ignore
            if not isinstance(blockchain, Exception)
        }

    async def update(self) -> str:
        if os.getenv("VERCEL_REGION") not in ALLOWED_REGIONS:
            return "Region not authorized for state updates"

        try:
            providers = await self._fetch_provider_endpoints()
            if not providers:
                return "No valid providers configured"

            blockchain_data = await self._collect_blockchain_data(providers)
            if not blockchain_data:
                return "No blockchain data collected"

            blob_handler = BlobStorageHandler(self.blob_config)
            await blob_handler.initialize()
            await blob_handler.update_all(blockchain_data)

            return "State updated successfully"

        except Exception as e:
            logging.error(f"State update failed: {e}")
            raise


class handler(BaseHTTPRequestHandler):
    def _check_auth(self) -> bool:
        if os.getenv("SKIP_AUTH", "").lower() == "true":
            return True
        token = self.headers.get("Authorization", "")
        return token == f"Bearer {os.getenv('CRON_SECRET', '')}"

    def do_GET(self):
        if not self._check_auth():
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(StateUpdateManager().update())
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(result.encode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(str(e).encode())
        finally:
            loop.close()
