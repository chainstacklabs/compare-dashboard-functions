"""Metrics collection and processing base class."""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Union

from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels

logging.getLogger("httpx").setLevel(logging.WARNING)


@dataclass
class MetricValue:
    """Container for a single metric value and its specific labels."""

    value: Union[int, float]
    labels: Optional[dict[str, str]] = None


class BaseMetric(ABC):
    """Base class for collecting and formatting metrics in single-invocation environments."""

    def __init__(
        self,
        handler: "MetricsHandler",  # type: ignore  # noqa: F821
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        ws_endpoint: Optional[str] = None,
        http_endpoint: Optional[str] = None,
    ) -> None:
        self.metric_id = str(uuid.uuid4())
        self.metric_name: str = metric_name
        self.labels: MetricLabels = labels
        self.config: MetricConfig = config
        self.ws_endpoint: str | None = ws_endpoint
        self.http_endpoint: str | None = http_endpoint
        self.values: dict[str, MetricValue] = {}
        handler._instances.append(self)

    @abstractmethod
    async def collect_metric(self) -> None:
        """Collects metric data."""

    @abstractmethod
    def process_data(self, data: Any) -> Union[int, float]:
        """Processes raw data into metric value."""

    def get_influx_format(self) -> list[str]:
        """Returns metrics in Influx line protocol format."""
        if not self.values:
            raise ValueError("No metric values set")

        metrics = []
        base_tags: str = ",".join(
            [f"{label.key.value}={label.value}" for label in self.labels.labels]
        )

        for value_type, metric_value in self.values.items():
            tags: str = base_tags
            if tags:
                tags = f"{base_tags},metric_type={value_type}"
            else:
                tags = f"metric_type={value_type}"

            metric_line: str = f"{self.metric_name}"
            if tags:
                metric_line += f",{tags}"
            metric_line += f" value={metric_value.value}"

            metrics.append(metric_line)

        return metrics

    def update_metric_value(
        self,
        value: Union[int, float],
        value_type: str = "response_time",
        labels: Optional[dict[str, str]] = None,
    ) -> None:
        """Updates metric value, preserving existing labels if present."""
        if value_type in self.values:
            labels = labels or self.values[value_type].labels
        self.values[value_type] = MetricValue(value=value, labels=labels)

    def mark_success(self) -> None:
        """Sets response status to success."""
        self.labels.update_label(MetricLabelKey.RESPONSE_STATUS, "success")

    def mark_failure(self) -> None:
        """Sets failure status and zeros all existing metric types."""
        self.labels.update_label(MetricLabelKey.RESPONSE_STATUS, "failed")
        value_types = list(self.values.keys())
        for value_type in value_types:
            self.update_metric_value(0, value_type)

    def handle_error(self, error: Exception) -> None:
        """Logs error and sets default value if none exists."""
        if not self.values:
            self.update_metric_value(0)

        error_type: str = error.__class__.__name__
        error_details = getattr(error, "error_msg", str(error))

        logging.error(
            f"Metric error [{error_type}] {self.labels.get_prometheus_labels()}: {error_details}",
            exc_info=True,
        )
