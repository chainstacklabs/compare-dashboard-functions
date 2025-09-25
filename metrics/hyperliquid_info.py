"""Hyperliquid Info API metrics implementation for /info endpoints."""

from typing import Any

from common.hyperliquid_info_base import HyperliquidInfoMetricBase


class HTTPClearinghouseStateLatencyMetric(HyperliquidInfoMetricBase):
    """Collects response time for clearinghouseState queries."""

    @property
    def method(self) -> str:
        """Return the API method name for clearinghouse state queries."""
        return "clearinghouseState"

    @staticmethod
    def get_params_from_state(state_data: dict[str, Any]) -> dict[str, str]:
        """Get parameters for clearinghouseState query."""
        return {"user": "0x31ca8395cf837de08b24da3f660e77761dfb974b"}


class HTTPOpenOrdersLatencyMetric(HyperliquidInfoMetricBase):
    """Collects response time for openOrders queries."""

    @property
    def method(self) -> str:
        """Return the API method name for open orders queries."""
        return "openOrders"

    @staticmethod
    def get_params_from_state(state_data: dict[str, Any]) -> dict[str, str]:
        """Get parameters for openOrders query."""
        return {"user": "0x31ca8395cf837de08b24da3f660e77761dfb974b"}
