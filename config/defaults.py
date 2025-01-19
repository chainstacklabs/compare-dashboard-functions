class MetricsServiceConfig:
    """Default configuration for metrics collection and processing."""
    
    # Grafana push settings
    GRAFANA_PUSH_MAX_RETRIES = 3
    GRAFANA_PUSH_RETRY_DELAY = 3
    GRAFANA_PUSH_TIMEOUT = 5
    
    # Metrics collection settings
    METRIC_REQUEST_TIMEOUT = 35
    METRIC_MAX_LATENCY = 35