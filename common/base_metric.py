"""Metrics collection and processing base class."""

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional, Union

from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels


class BaseMetric(ABC):
    """Base class for collecting and formatting metrics in single-invocation environments."""

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        ws_endpoint: Optional[str] = None,
        http_endpoint: Optional[str] = None,
    ) -> None:
        self.metric_id = str(uuid.uuid4())
        self.metric_name = metric_name
        self.labels = labels
        self.config = config
        self.ws_endpoint = ws_endpoint
        self.http_endpoint = http_endpoint
        self.latest_value = None
        handler._instances.append(self)

    @abstractmethod
    async def collect_metric(self) -> None:
        """Collects metric data."""

    @abstractmethod
    def process_data(self, data: Any) -> Union[int, float]:
        """Processes raw data into metric value."""

    def get_influx_format(self) -> str:
        """Returns metric in Influx line protocol format."""
        if self.latest_value is None:
            raise ValueError("Metric value is not set")
        tag_str = ",".join(
            [f"{label.key.value}={label.value}" for label in self.labels.labels]
        )
        if tag_str:
            return f"{self.metric_name},{tag_str} value={self.latest_value}"
        return f"{self.metric_name} value={self.latest_value}"

    def update_metric_value(self, value: Union[int, float]) -> None:
        """Updates metric value."""
        self.latest_value = value

    def mark_success(self) -> None:
        """Sets response status to success."""
        self.labels.update_label(MetricLabelKey.RESPONSE_STATUS, "success")

    def mark_failure(self) -> None:
        """Sets response status to failed."""
        self.labels.update_label(MetricLabelKey.RESPONSE_STATUS, "failed")

    def handle_error(self, error: Exception) -> None:
        """Logs error and sets default value if none exists."""
        if not self.latest_value:
            self.update_metric_value(0)
        
        error_type = error.__class__.__name__
        error_details = getattr(error, 'error_msg', str(error))
        
        logging.error(
            f"Metric error [{error_type}] {self.labels.get_prometheus_labels()}: {error_details}",
            exc_info=True
        )
