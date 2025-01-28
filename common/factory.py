"""Factory for creating blockchain-specific metric instances."""

from typing import Dict, List, Tuple, Type

from common.base_metric import BaseMetric
from common.metric_config import EndpointConfig, MetricConfig, MetricLabels


class MetricFactory:
    """Creates metric instances for blockchains in serverless environments."""

    _registry: Dict[str, List[Tuple[Type[BaseMetric], str]]] = {}

    @classmethod
    def register(
        cls, blockchain_metrics: Dict[str, List[Tuple[Type[BaseMetric], str]]]
    ):
        """Registers metric classes for blockchains."""
        for blockchain_name, metrics in blockchain_metrics.items():
            if blockchain_name not in cls._registry:
                cls._registry[blockchain_name] = []
            for metric in metrics:
                if isinstance(metric, tuple) and len(metric) == 2:
                    metric_class, metric_name = metric
                    cls._registry[blockchain_name].append((metric_class, metric_name))
                else:
                    raise ValueError(
                        "Each metric must be a tuple (metric_class, metric_name)"
                    )

    @classmethod
    def create_metrics(
        cls,
        blockchain_name: str,
        metrics_handler: "MetricsHandler",  # type: ignore
        config: MetricConfig,
        **kwargs,
    ) -> List[BaseMetric]:
        if blockchain_name not in cls._registry:
            available = list(cls._registry.keys())
            raise ValueError(
                f"No metric classes registered for blockchain '{blockchain_name}'. Available blockchains: {available}"
            )

        source_region = kwargs.get("source_region", "default")
        target_region = kwargs.get("target_region", "default")
        provider = kwargs.get("provider", "default")

        endpoints = EndpointConfig(
            main_endpoint=kwargs.get("http_endpoint"),
            tx_endpoint=kwargs.get("tx_endpoint"),
            ws_endpoint=kwargs.get("ws_endpoint"),
        )

        config.endpoints = endpoints

        metrics = []
        for metric_class, metric_name in cls._registry[blockchain_name]:
            labels = MetricLabels(
                source_region=source_region,
                target_region=target_region,
                blockchain=blockchain_name,
                provider=provider,
            )
            metric_kwargs = kwargs.copy()
            metric_instance = metric_class(
                handler=metrics_handler,
                metric_name=metric_name,
                labels=labels,
                config=config,
                **metric_kwargs,
            )
            metrics.append(metric_instance)
        return metrics
