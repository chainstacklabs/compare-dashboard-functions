"""Endpoint enumeration for the verifier.

Reads from the same ``ENDPOINTS`` env var that ``api/support/update_state.py``
and ``common/metrics_handler.py`` already use, but exposes two queries that
``update_state`` doesn't need:

- ``all_providers_for(chain)`` — every HTTP endpoint configured for the chain
  (regardless of provider name). Used for the multi-provider stateRoot quorum.
- ``chainstack_endpoint_for(chain)`` — the Chainstack endpoint specifically.
  Used for the proof fetch.
"""

import json
import os
from typing import Any, Optional

CHAINSTACK_PROVIDER_NAME = "Chainstack"


def _load_endpoints_config() -> dict[str, Any]:
    """Parse the ENDPOINTS env var. Returns the raw config dict."""
    raw = os.getenv("ENDPOINTS", "{}")
    try:
        config = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(config, dict):
        return {}
    return config


def all_providers_for(chain: str) -> list[str]:
    """Return every configured HTTP endpoint for the chain (any provider).

    Args:
        chain: Blockchain name (case-insensitive match against ``ENDPOINTS``).

    Returns:
        List of HTTP endpoint URLs. Empty if no providers are configured.
    """
    return [url for _, url in all_provider_entries_for(chain)]


def all_provider_entries_for(chain: str) -> list[tuple[str, str]]:
    """Return (name, http_endpoint) pairs for every provider on the chain.

    Used by v2.1's per-provider balance probe step, which needs the provider
    name as a Grafana tag — ``all_providers_for`` drops the name. Order
    matches the ENDPOINTS config so the per-round emission order is stable.
    """
    config = _load_endpoints_config()
    target = chain.lower()
    out: list[tuple[str, str]] = []
    for provider in config.get("providers", []):
        if not isinstance(provider, dict):
            continue
        if provider.get("blockchain", "").lower() != target:
            continue
        name = provider.get("name")
        endpoint = provider.get("http_endpoint")
        if isinstance(name, str) and name and isinstance(endpoint, str) and endpoint:
            out.append((name, endpoint))
    return out


def chainstack_endpoint_for(chain: str) -> Optional[str]:
    """Return the Chainstack HTTP endpoint for the chain, or None."""
    config = _load_endpoints_config()
    target = chain.lower()
    for provider in config.get("providers", []):
        if not isinstance(provider, dict):
            continue
        if provider.get("blockchain", "").lower() != target:
            continue
        if provider.get("name") != CHAINSTACK_PROVIDER_NAME:
            continue
        endpoint = provider.get("http_endpoint")
        if isinstance(endpoint, str) and endpoint:
            return endpoint
    return None
