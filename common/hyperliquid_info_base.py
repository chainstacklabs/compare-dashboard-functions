"""Base class for Hyperliquid /info endpoint metrics."""

from abc import abstractmethod
from typing import Any

import aiohttp

from common.http_timing import measure_http_request_timing
from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels
from common.metric_types import HttpMetric
from common.metrics_handler import MetricsHandler


class HyperliquidInfoMetricBase(HttpMetric):
    """Base class for Hyperliquid /info endpoint latency metrics.

    Handles request configuration, state validation, and response time
    measurement for Hyperliquid info API endpoints.
    """

    @property
    @abstractmethod
    def method(self) -> str:
        """Info API method to be implemented by subclasses."""
        pass

    def __init__(
        self,
        handler: "MetricsHandler",
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs: Any,
    ) -> None:
        """Initialize Hyperliquid info metric with state-based parameters."""
        state_data = kwargs.get("state_data", {})
        if not self.validate_state(state_data):
            raise ValueError(f"Invalid state data for {self.method}")

        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
        )

        params = self.get_params_from_state(state_data)
        self.user_address = params["user"]
        self.labels.update_label(MetricLabelKey.API_METHOD, self.method)
        self.request_payload = self._build_request_payload()

    def _build_request_payload(self) -> dict[str, Any]:
        """Build the Hyperliquid info API request payload."""
        return {"type": self.method, "user": self.user_address}

    @staticmethod
    def validate_state(state_data: dict[str, Any]) -> bool:
        """Validate state data. Override in subclasses if needed."""
        return True

    @staticmethod
    def get_params_from_state(state_data: dict[str, Any]) -> dict[str, str]:
        """Get parameters from state data. Override in subclasses if needed."""
        return {}

    def get_info_endpoint(self) -> str:
        """Transform EVM endpoint to info endpoint."""
        base_endpoint = self.get_endpoint()

        if base_endpoint.endswith("/evm"):
            return base_endpoint.replace("/evm", "/info")
        else:
            # Handle cases where endpoint doesn't end with /evm
            if base_endpoint.endswith("/"):
                return base_endpoint + "info"
            else:
                return base_endpoint + "/info"

    async def fetch_data(self) -> float:
        """Measure single request latency for Hyperliquid info API."""
        endpoint = self.get_info_endpoint()

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            response_time, response = await measure_http_request_timing(
                session=session,
                method="POST",
                url=endpoint,
                headers=headers,
                json_data=self.request_payload,
                exclude_connection_time=True,
            )

            try:
                # Validate response
                if response.status != 200:
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=(),
                        status=response.status,
                        message=f"Status code: {response.status}",
                        headers=response.headers,
                    )

                response_data = await response.json()

                return response_time

            finally:
                await response.release()

    def process_data(self, value: float) -> float:
        """Process raw latency measurement."""
        return value
