"""Shared HTTP request timing utilities for metric collection."""

import asyncio
import time
from typing import Any, Dict, Optional

import aiohttp

MAX_RETRIES = 2


class HttpTimingCollector:
    """Utility class for measuring HTTP request timing with detailed breakdown."""

    def __init__(self):
        self.timing: Dict[str, float] = {}

    def create_trace_config(self) -> aiohttp.TraceConfig:
        """Create aiohttp trace configuration for detailed timing measurement."""
        trace_config = aiohttp.TraceConfig()

        async def on_request_start(session, context, params):
            self.timing["start"] = time.monotonic()

        async def on_dns_resolvehost_start(session, context, params):
            self.timing["dns_start"] = time.monotonic()

        async def on_dns_resolvehost_end(session, context, params):
            self.timing["dns_end"] = time.monotonic()

        async def on_connection_create_start(session, context, params):
            self.timing["conn_start"] = time.monotonic()

        async def on_connection_create_end(session, context, params):
            self.timing["conn_end"] = time.monotonic()

        async def on_request_end(session, context, params):
            self.timing["end"] = time.monotonic()

        trace_config.on_request_start.append(on_request_start)
        trace_config.on_dns_resolvehost_start.append(on_dns_resolvehost_start)
        trace_config.on_dns_resolvehost_end.append(on_dns_resolvehost_end)
        trace_config.on_connection_create_start.append(on_connection_create_start)
        trace_config.on_connection_create_end.append(on_connection_create_end)
        trace_config.on_request_end.append(on_request_end)

        return trace_config

    def get_connection_time(self) -> float:
        """Get connection establishment time in seconds."""
        if "conn_start" in self.timing and "conn_end" in self.timing:
            return self.timing["conn_end"] - self.timing["conn_start"]
        return 0.0

    def get_dns_time(self) -> float:
        """Get DNS resolution time in seconds."""
        if "dns_start" in self.timing and "dns_end" in self.timing:
            return self.timing["dns_end"] - self.timing["dns_start"]
        return 0.0


async def measure_http_request_timing(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    exclude_connection_time: bool = True,
) -> tuple[float, aiohttp.ClientResponse]:
    """Measure HTTP request timing with retry logic and detailed breakdown.

    Returns:
        tuple: (response_time_seconds, response)
    """
    response_time = 0.0
    response = None

    for retry_count in range(MAX_RETRIES):
        start_time = time.monotonic()

        # Send request
        if method.upper() == "POST":
            response = await session.post(
                url, headers=headers, json=json_data
            )
        else:
            response = await session.get(url, headers=headers)

        response_time = time.monotonic() - start_time

        # Handle rate limiting
        if response.status == 429 and retry_count < MAX_RETRIES - 1:
            wait_time = int(response.headers.get("Retry-After", 3))
            await response.release()
            await asyncio.sleep(wait_time)
            continue

        break

    if not response:
        raise ValueError("No response received")

    return response_time, response
