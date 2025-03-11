"""State update handler for blockchain data collection with provider filtering."""

import asyncio
import json
import logging
import os
from collections.abc import Coroutine
from http.server import BaseHTTPRequestHandler
from typing import Any

from common.state.blob_storage import BlobConfig, BlobStorageHandler
from common.state.blockchain_fetcher import BlockchainData, BlockchainDataFetcher
from common.state.blockchain_state import BlockchainState

SUPPORTED_BLOCKCHAINS: list[str] = ["ethereum", "solana", "ton", "base"]
ALLOWED_PROVIDERS: set[str] = {
    "Chainstack"
}  # To reduce number of RPC calls, use only one provider here
ALLOWED_REGIONS: set[str] = {
    "fra1"
}  # To reduce number of RPC calls, use only one region here


class MissingEndpointsError(Exception):
    """Raised when required blockchain endpoints are not found."""

    def __init__(self, missing_chains: set[str]) -> None:
        self.missing_chains: set[str] = missing_chains
        chains: str = ", ".join(missing_chains)
        super().__init__(f"Missing Chainstack endpoints for: {chains}")


class StateUpdateManager:
    """Manages the collection, processing, and storage of blockchain state data.

    This class orchestrates the retrieval of blockchain state data from configured endpoints,
    handles fallback to previous data in case of errors, and updates the centralized blob storage.
    It enforces provider and region filtering to optimize RPC calls and ensures data consistency.
    """

    def __init__(self) -> None:
        store_id: str | None = os.getenv("STORE_ID")
        token: str | None = os.getenv("VERCEL_BLOB_TOKEN")
        if not all([store_id, token]):
            raise ValueError("Missing required blob storage configuration")

        self.blob_config = BlobConfig(store_id=store_id, token=token)  # type: ignore
        self.logger: logging.Logger = logging.getLogger(__name__)

    async def _get_chainstack_endpoints(self) -> dict[str, str]:
        """Get Chainstack endpoints for supported blockchains."""
        endpoints = json.loads(os.getenv("ENDPOINTS", "{}"))
        chainstack_endpoints: dict[str, str] = {}
        missing_chains: set[str] = set(SUPPORTED_BLOCKCHAINS)

        for provider in endpoints.get("providers", []):
            blockchain = provider["blockchain"].lower()
            if (
                blockchain in SUPPORTED_BLOCKCHAINS
                and provider["name"] in ALLOWED_PROVIDERS
                and blockchain not in chainstack_endpoints
            ):
                chainstack_endpoints[blockchain] = provider["http_endpoint"]
                missing_chains.remove(blockchain)

        if missing_chains:
            raise MissingEndpointsError(missing_chains)

        return chainstack_endpoints

    async def _get_previous_data(self) -> dict[str, Any]:
        """Fetch previous blockchain state data."""
        try:
            state = BlockchainState()
            previous_data = {}
            for blockchain in SUPPORTED_BLOCKCHAINS:
                try:
                    chain_data = await state.get_data(blockchain)
                    if chain_data:
                        previous_data[blockchain] = chain_data
                except Exception as e:
                    self.logger.warning(
                        f"Failed to get previous data for {blockchain}: {e}"
                    )
            return previous_data
        except Exception as e:
            self.logger.error(f"Failed to get previous state data: {e}")
            return {}

    async def _collect_blockchain_data(
        self, providers: dict[str, str], previous_data: dict[str, Any]
    ) -> dict[str, dict]:
        async def fetch_single(
            blockchain: str, endpoint: str
        ) -> tuple[str, dict[str, str]]:
            try:
                fetcher = BlockchainDataFetcher(endpoint)
                data: BlockchainData = await fetcher.fetch_latest_data(blockchain)

                if data.block_id and data.transaction_id:
                    return blockchain, {
                        "block": data.block_id,
                        "tx": data.transaction_id,
                        "old_block": data.old_block_id,
                    }

                if blockchain in previous_data:
                    self.logger.warning(f"Using previous data for {blockchain}")
                    return blockchain, previous_data[blockchain]

                self.logger.warning(f"Returning empty data for {blockchain}")
                return blockchain, {"block": "", "tx": "", "old_block": ""}
            except Exception as e:
                self.logger.error(f"Failed to fetch {blockchain} data: {e}")
                if blockchain in previous_data:
                    self.logger.warning(
                        f"Using previous data for {blockchain} after error"
                    )
                    return blockchain, previous_data[blockchain]
                self.logger.warning(f"Returning empty data for {blockchain}")
                return blockchain, {"block": "", "tx": "", "old_block": ""}

        tasks: list[Coroutine[Any, Any, tuple[str, dict[str, str]]]] = [
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
            previous_data: dict[str, Any] = await self._get_previous_data()

            chainstack_endpoints: dict[str, str] = (
                await self._get_chainstack_endpoints()
            )
            blockchain_data = await self._collect_blockchain_data(
                chainstack_endpoints, previous_data
            )

            # If we didn't get any data, use previous data
            if not blockchain_data:
                if previous_data:
                    self.logger.warning("Using complete previous state as fallback")
                    blockchain_data: dict[str, Any] = previous_data
                else:
                    return "No blockchain data collected and no previous data available"

            blob_handler = BlobStorageHandler(self.blob_config)
            await blob_handler.update_data(blockchain_data)

            return "State updated successfully"

        except MissingEndpointsError as e:
            self.logger.error(f"Configuration error: {e}")
            raise
        except Exception as e:
            self.logger.error(f"State update failed: {e}")
            raise


class handler(BaseHTTPRequestHandler):
    def _check_auth(self) -> bool:
        if os.getenv("SKIP_AUTH", "").lower() == "true":
            return True
        token: str = self.headers.get("Authorization", "")
        return token == f"Bearer {os.getenv('CRON_SECRET', '')}"

    def do_GET(self) -> None:
        if not self._check_auth():
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return

        loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result: str = loop.run_until_complete(StateUpdateManager().update())
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
