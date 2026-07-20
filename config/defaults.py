"""Default configuration."""

import os
from typing import ClassVar


class MetricsServiceConfig:
    """Default configuration for metrics collection and processing."""

    IGNORED_HTTP_ERRORS: ClassVar[list[int]] = [
        403,  # Forbidden - usually related to plan restrictions
        429,  # Too Many Requests - rate limit exceeded
        401,  # Unauthorized - if authentication failure is plan-related
        404,  # Not Found - endpoint deprecation or incorrect endpoint
    ]

    # Grafana push settings
    GRAFANA_PUSH_MAX_RETRIES = 3
    GRAFANA_PUSH_RETRY_DELAY = 1
    GRAFANA_PUSH_TIMEOUT = 3

    # Metrics collection settings
    METRIC_REQUEST_TIMEOUT = 55
    METRIC_MAX_LATENCY = 55

    # SOLANA TX SETTINGS
    SOLANA_CONFIRMATION_LEVEL = "confirmed"
    PRIORITY_FEE_MICROLAMPORTS = 200_000
    COMPUTE_LIMIT = 1000

    METRIC_PREFIX = (
        "dev_" if os.getenv("VERCEL_ENV") != "production" else ""
    )  # System env var, standard name

    # Block offset configuration (N blocks back from latest)
    BLOCK_OFFSET_RANGES: ClassVar[dict[str, tuple[int, int]]] = {
        "ethereum": (7200, 10000),
        "base": (7200, 10000),
        "solana": (432000, 648000),
        "arbitrum": (7200, 10000),
        "bnb": (7200, 10000),
        "hyperliquid": (3600, 7200),
        "robinhood": (18000, 25000),
    }

    # Per-chain offset for the v2 verifier (eth_getProof at VERIFY_BLOCK).
    # Sized to fit Chainstack's empirically-measured proof-retention window
    # per chain — proofs are MPT trie nodes which prune ~128 blocks deep on
    # geth-family clients, much shallower than the snapshot-served balance
    # window that BLOCK_OFFSET_RANGES targets. Verified ranges as of 2026-05:
    #   Ethereum max retention ≈ 10,000 blocks, but proof latency scales
    #                            linearly with depth on Chainstack (~6 ms
    #                            per block, ~48 s at 8000-block depth).
    #                            Tightened to (200, 500) for proof times
    #                            of ~4-7s, well within Vercel's 59 s budget.
    #                            200 blocks (~40 min) is way past finality
    #                            (~64 blocks).
    #   Base     max retention ≈   121 blocks (~4 min)
    #   BNB      max retention ≈   117 blocks (~5.8 min)
    #   Arbitrum max retention ≈   107 blocks (~27 s) — tightest; arb head
    #                            moves fast so we keep extra headroom for
    #                            in-cron drift.
    #   Robinhood max retention ≈   128 blocks but only ~12.8 s (~100 ms
    #                            blocks) — shortest wall-clock window of any
    #                            chain. Kept at (30, 70): measured round is
    #                            ~0.1 s with 1-7 block head-drift, so
    #                            effective proof depth stays ~<100, leaving
    #                            ~28 blocks of margin under the 128 prune edge
    #                            for slower/cold prod rounds.
    VERIFY_BLOCK_OFFSET_RANGES: ClassVar[dict[str, tuple[int, int]]] = {
        "ethereum": (200, 500),
        # base deferred — no historical proofs available (see verify_state.py)
        "arbitrum": (50, 70),
        "bnb": (30, 100),
        "robinhood": (30, 70),
    }


class BlobStorageConfig:
    """Default configuration for blob storage."""

    BLOB_BASE_URL = "https://blob.vercel-storage.com"
    BLOB_FILENAME = "blockchain-data.json"
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 1
    FOLDER_PREFIX = "dev-" if os.getenv("VERCEL_ENV") != "production" else "prod-"
    BLOB_FOLDER = f"{FOLDER_PREFIX}rpc-dashboard"
