"""Default configuration."""

import os


class MetricsServiceConfig:
    """Default configuration for metrics collection and processing."""

    IGNORED_HTTP_ERRORS = [
        403,
        429,
    ]  # Define the errors to ignore (data will not be submitted to Grafana)  # noqa: RUF012

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
    BLOCK_OFFSET_RANGES = {  # noqa: RUF012
        "ethereum": (7200, 14400),
        "base": (7200, 14400),
        "solana": (432000, 648000),
        "ton": (1555200, 1572480),
        "arbitrum": (7200, 14400),
        "bnb": (7200, 14400),
    }


class BlobStorageConfig:
    """Default configuration for blob storage."""

    BLOB_BASE_URL = "https://blob.vercel-storage.com"
    BLOB_FILENAME = "blockchain-data.json"
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 1
    FOLDER_PREFIX = "dev-" if os.getenv("VERCEL_ENV") != "production" else "prod-"
    BLOB_FOLDER = f"{FOLDER_PREFIX}rpc-dashboard"
